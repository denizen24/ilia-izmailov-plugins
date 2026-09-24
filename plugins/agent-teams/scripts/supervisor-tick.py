#!/usr/bin/env python3
"""supervisor-tick.py — один тик супервизора команды, без LLM.

Читает каталог прогона `.claude/teams/<team>/` и отвечает на один вопрос: есть ли
сейчас что-то, ради чего стоит будить ведущего. Ничего не сочиняет и никому не
пишет — только факты из файлов, которые команда и так ведёт:

  PLAN.md          статусы задач (пишет только ведущий)
  state.md         фаза, движки
  runs/<name>.json карточка участника: роль, задача, статус, время последнего события
                   (создаёт ведущий при спавне, дальше ведёт сам участник)
  mail/<to>/*.md   письма: одно письмо — один файл (`team-mail.sh` или Write)
  pending.log      копии писем, вернувшихся `queued` (строки `| OPEN`)
  ledger.jsonl     события движков (`run-engine.sh`)
  engine/<role>/   маркеры движков: *.out.pid / .done / .taken

Пишет только своё: state/supervisor.json (снимок + память тика) и печатает
действия. Код выхода всегда 0, кроме поломки окружения (нет каталога).

Приоритеты (от срочного к фоновому):
  P0  доставить копию `queued`; участник STUCK / ENGINE_DOWN / прокси мёртв;
      движок упал или досчитал, а результат никто не забрал; участник молчит
      дольше двух интервалов
  P1  DONE участника, которого ведущий ещё не отметил в PLAN.md (accept_needed);
      письмо ведущему без ответа (QUESTION / ESCALATION / SENSITIVE / QUEUED);
      первая минута: участник молчит уже 3 минуты
  P2  первая минута: спавн старше 60 с, а признаков жизни нет
  P3  контрольная точка: с последнего события прошёл интервал участника
  P4  всё тихо

Использование:
  supervisor-tick.py <run-dir> [--root <корень репозитория>] [--json] [--now ISO]
  supervisor-tick.py ack <run-dir> <имя файла письма>   — ведущий ответил на письмо
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

FIRST_MINUTE_SEC = 60          # после этого ждём признаков жизни
FIRST_MINUTE_LOUD_SEC = 180    # молчание дольше — уже P1
DEFAULT_CHECK_SEC = 900        # контрольная точка по умолчанию, 15 мин
PENDING_STALE_SEC = 120        # OPEN в pending.log старше двух минут — P0
ENGINE_UNREAD_SEC = 900        # движок досчитал, а результат не забрали 15 мин
LIVE = ("running", "in_review", "fixing", "reviewing")
NEEDS_ANSWER = ("QUESTION", "ESCALATION", "SENSITIVE", "QUEUED", "REVIEW_LOOP")
PRIORITY = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}


def parse_ts(value):
    """ISO-время в aware datetime; пустое или кривое — None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def plan_tasks(run_dir):
    """{id: status} из PLAN.md: `## Task 3: …` и следующая за ним строка `Status: X`."""
    text = (run_dir / "PLAN.md").read_text(encoding="utf-8") if (run_dir / "PLAN.md").exists() else ""
    tasks = {}
    current = None
    for line in text.splitlines():
        head = re.match(r"^## Task\s+([^:\s]+)\s*:", line)
        if head:
            current = head.group(1)
            tasks[current] = {"status": "", "files": []}
            continue
        if current is None:
            continue
        m = re.match(r"^Status:\s*(\S+)", line)
        if m:
            tasks[current]["status"] = m.group(1)
        m = re.match(r"^Files to (?:create/edit|edit|create):\s*(.+)$", line)
        if m:
            tasks[current]["files"] = [f.strip() for f in m.group(1).split(",") if f.strip()]
    return tasks


def state_phase(run_dir):
    text = (run_dir / "state.md").read_text(encoding="utf-8") if (run_dir / "state.md").exists() else ""
    m = re.search(r"^## Phase:\s*(\S+)", text, re.M)
    return m.group(1) if m else ""


def read_runs(run_dir):
    runs = {}
    for f in sorted((run_dir / "runs").glob("*.json")) if (run_dir / "runs").is_dir() else []:
        data = read_json(f, None)
        if isinstance(data, dict):
            data.setdefault("name", f.stem)
            runs[data["name"]] = data
    return runs


def read_mail(run_dir, box):
    """Письма в mail/<box>/: [{file, from, kind, task, ts, first}] по времени файла."""
    folder = run_dir / "mail" / box
    if not folder.is_dir():
        return []
    letters = []
    for f in sorted(folder.glob("*.md")):
        head = {}
        body_first = ""
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        i = 0
        for i, line in enumerate(lines):
            m = re.match(r"^(from|kind|task|ts):\s*(.*)$", line)
            if not m:
                break
            head[m.group(1)] = m.group(2).strip()
        for line in lines[i:]:
            if line.strip():
                body_first = line.strip()
                break
        letters.append({"file": f.name, "from": head.get("from", ""), "kind": head.get("kind", "").upper(),
                        "task": head.get("task", ""), "ts": head.get("ts", ""), "first": body_first})
    return letters


def acked(run_dir):
    f = run_dir / "state" / "acked.log"
    return set(f.read_text(encoding="utf-8").split()) if f.exists() else set()


def pending_open(run_dir, now):
    """Строки pending.log со статусом OPEN: [(строка, возраст в секундах или None)]."""
    f = run_dir / "pending.log"
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip() or not re.search(r"\|\s*OPEN\s*$", line):
            continue
        age = None
        m = re.match(r"^(\d{2}):(\d{2})\s", line)
        if m:
            stamp = now.astimezone().replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
            if stamp > now:
                stamp -= timedelta(days=1)
            age = int((now - stamp).total_seconds())
        out.append((line.strip(), age))
    return out


def engine_calls(run_dir, now):
    """Маркеры движков, как их видит `run-engine.sh --status`: [{role, base, state, age}]."""
    calls = []
    root = run_dir / "engine"
    if not root.is_dir():
        return calls
    for pid_file in sorted(root.glob("*/*.out.pid")):
        base = pid_file.with_suffix("")          # …/NNN.out
        role = pid_file.parent.name
        done = Path(str(base) + ".done")
        taken = Path(str(base) + ".taken")
        try:
            pid = int(pid_file.read_text().strip() or 0)
        except (OSError, ValueError):
            pid = 0
        if done.exists():
            state = "taken" if taken.exists() else "done-unread"
            failed = "status=failed" in done.read_text(encoding="utf-8", errors="replace")
            age = int(now.timestamp() - done.stat().st_mtime)
            calls.append({"role": role, "base": str(base), "state": state, "failed": failed, "age": age})
        else:
            alive = False
            if pid:
                try:
                    os.kill(pid, 0)
                    alive = True
                except ProcessLookupError:
                    alive = False
                except PermissionError:
                    alive = True
            calls.append({"role": role, "base": str(base), "state": "running" if alive else "dead",
                          "failed": False, "age": int(now.timestamp() - pid_file.stat().st_mtime)})
    return calls


def changed_files(root, files):
    """Есть ли среди файлов задачи изменённые в рабочем дереве (git status)."""
    if not root or not files:
        return False
    try:
        out = subprocess.run(["git", "-C", str(root), "status", "--short", "--", *files],
                             capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(out.strip())


def tick(run_dir, root=None, now=None):
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise SystemExit(f"supervisor-tick: нет каталога прогона {run_dir}")
    now = now or datetime.now(timezone.utc).astimezone()
    root = Path(root) if root else run_dir.resolve().parents[1]
    memory_file = run_dir / "state" / "supervisor.json"
    memory = read_json(memory_file, {})
    firsts = memory.get("firstMinute", {})          # name -> "ok" | "silent"
    checkpoints = memory.get("checkpoints", {})     # name -> ISO последней контрольной точки

    tasks = plan_tasks(run_dir)
    runs = read_runs(run_dir)
    lead_mail = read_mail(run_dir, "lead")
    done_ack = acked(run_dir)
    actions = []

    def add(priority, kind, run="", detail="", ref=""):
        actions.append({"priority": priority, "kind": kind, "run": run, "detail": detail, "ref": ref})

    # ---- P0: копии `queued`, застрявшие у ведущего
    for line, age in pending_open(run_dir, now):
        add("P0" if age is None or age >= PENDING_STALE_SEC else "P1", "deliver_pending", detail=line, ref="pending.log")

    # ---- письма ведущему
    mailed_done = {}   # task -> letter
    for letter in lead_mail:
        if letter["file"] in done_ack:
            continue
        kind = letter["kind"]
        if kind == "DONE":
            mailed_done[letter["task"]] = letter
        elif kind in ("STUCK", "ENGINE_DOWN"):
            add("P0", kind.lower(), run=letter["from"], detail=letter["first"], ref=f"mail/lead/{letter['file']}")
        elif kind in NEEDS_ANSWER:
            add("P1", "answer_needed", run=letter["from"], detail=f"{kind}: {letter['first']}", ref=f"mail/lead/{letter['file']}")
    for task, letter in mailed_done.items():
        status = tasks.get(task, {}).get("status", "")
        if status != "DONE":
            add("P1", "accept_needed", run=letter["from"], detail=f"task {task}: {letter['first']} (PLAN: {status or 'нет задачи'})",
                ref=f"mail/lead/{letter['file']}")

    # ---- движки
    for call in engine_calls(run_dir, now):
        if call["state"] == "dead":
            add("P0", "engine_dead", run=call["role"], detail=f"процесс исчез без маркера .done", ref=call["base"])
        elif call["state"] == "done-unread" and call["failed"]:
            add("P0", "engine_failed_unread", run=call["role"], detail="движок упал, отчёт не забран", ref=call["base"] + ".done")
        elif call["state"] == "done-unread" and call["age"] >= ENGINE_UNREAD_SEC:
            add("P0", "engine_result_unread", run=call["role"],
                detail=f"результат готов {call['age'] // 60} мин, никто не забрал", ref=call["base"] + ".result.md")

    # ---- участники: первая минута, контрольные точки, молчание
    signals_from = {l["from"] for l in lead_mail}
    for name, run in runs.items():
        status = str(run.get("status", "running"))
        if status in ("done", "stopped", "idle"):
            continue
        if status == "stuck":
            add("P0", "stuck", run=name, detail=run.get("note", ""), ref=f"runs/{name}.json")
            continue
        spawned = parse_ts(run.get("spawnedAt"))
        last = parse_ts(run.get("lastEventAt")) or spawned
        age = int((now - spawned).total_seconds()) if spawned else None
        since = int((now - last).total_seconds()) if last else None
        interval = int(run.get("checkAfterSec") or DEFAULT_CHECK_SEC)
        task = str(run.get("task", ""))
        files = run.get("files") or tasks.get(task, {}).get("files", [])

        # первая минута
        if age is not None and firsts.get(name) != "ok":
            alive = (last and spawned and last > spawned) or name in signals_from or changed_files(root, files) \
                or any(c["role"] == name for c in engine_calls(run_dir, now))
            if alive:
                firsts[name] = "ok"
            elif age >= FIRST_MINUTE_LOUD_SEC:
                firsts[name] = "silent"
                add("P1", "first_minute_silent", run=name, detail=f"{age} с после спавна — ни письма, ни правок, ни движка",
                    ref=f"runs/{name}.json")
            elif age >= FIRST_MINUTE_SEC:
                firsts[name] = "silent"
                add("P2", "first_minute_silent", run=name, detail=f"{age} с после спавна без признаков жизни", ref=f"runs/{name}.json")

        # молчание и контрольные точки
        if since is not None and firsts.get(name) == "ok":
            if since >= 2 * interval and not changed_files(root, files):
                add("P0", "silent_too_long", run=name, detail=f"{since // 60} мин без событий и без правок в файлах задачи",
                    ref=f"runs/{name}.json")
            elif since >= interval:
                fired = parse_ts(checkpoints.get(name))
                if not fired or fired < last or (now - fired).total_seconds() >= interval:
                    checkpoints[name] = now.isoformat(timespec="seconds")
                    add("P3", "checkpoint", run=name, detail=f"{since // 60} мин с последнего события, статус {status}",
                        ref=f"runs/{name}.json")

    if not actions:
        add("P4", "ok", detail="тихо: событий, требующих ведущего, нет")
    actions.sort(key=lambda a: PRIORITY[a["priority"]])

    snapshot = {
        "ts": now.isoformat(timespec="seconds"),
        "runDir": str(run_dir),
        "phase": state_phase(run_dir),
        "tasks": {k: v["status"] for k, v in tasks.items()},
        "runs": {n: {"status": r.get("status", ""), "task": r.get("task", "")} for n, r in runs.items()},
        "actions": actions,
        "firstMinute": firsts,
        "checkpoints": checkpoints,
    }
    (run_dir / "state").mkdir(exist_ok=True)
    tmp = memory_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, memory_file)
    return snapshot


def ack(run_dir, name):
    run_dir = Path(run_dir)
    (run_dir / "state").mkdir(exist_ok=True)
    with (run_dir / "state" / "acked.log").open("a", encoding="utf-8") as f:
        f.write(name + "\n")


def main(argv):
    if argv and argv[0] == "ack":
        if len(argv) != 3:
            raise SystemExit("использование: supervisor-tick.py ack <run-dir> <файл письма>")
        ack(argv[1], argv[2])
        return 0
    if not argv:
        raise SystemExit(__doc__)
    run_dir, root, as_json, now = argv[0], None, False, None
    rest = argv[1:]
    while rest:
        a = rest.pop(0)
        if a == "--root":
            root = rest.pop(0)
        elif a == "--json":
            as_json = True
        elif a == "--now":
            now = parse_ts(rest.pop(0))
        else:
            raise SystemExit(f"supervisor-tick: неизвестный аргумент {a}")
    snap = tick(run_dir, root, now)
    if as_json:
        print(json.dumps(snap, ensure_ascii=False))
    else:
        for a in snap["actions"]:
            who = f" {a['run']}" if a["run"] else ""
            ref = f"  [{a['ref']}]" if a["ref"] else ""
            print(f"{a['priority']} {a['kind']}{who}: {a['detail']}{ref}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
