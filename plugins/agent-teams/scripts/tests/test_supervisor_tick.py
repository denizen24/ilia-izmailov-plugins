"""Тик супервизора проверяется на каталогах-фикстурах: каждое правило — свой случай.

Запуск: python3 -m unittest discover -s scripts/tests   (из plugins/agent-teams)
"""
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("supervisor_tick", HERE.parent / "supervisor-tick.py")
st = importlib.util.module_from_spec(spec)
spec.loader.exec_module(st)

NOW = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat(timespec="seconds")


class Fixture:
    def __init__(self, case=None):
        self.tmp = tempfile.TemporaryDirectory()
        if case is not None:
            case.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = self.root / ".claude" / "teams" / "feature-x"
        (self.run / "runs").mkdir(parents=True)
        (self.run / "mail" / "lead").mkdir(parents=True)
        subprocess.run(["git", "-C", str(self.root), "init", "-q"], check=True)
        self.plan({"3": "IN_PROGRESS(coder-3)"})

    def plan(self, statuses, files=None):
        text = "# Plan\n\n"
        for tid, status in statuses.items():
            text += f"## Task {tid}: something\nStatus: {status}\nBlocked by: none\n"
            text += f"Files to create/edit: {', '.join((files or {}).get(tid, ['src/t' + tid + '.py']))}\n\n"
        (self.run / "PLAN.md").write_text(text, encoding="utf-8")

    def run_card(self, name, **fields):
        data = {"name": name, "role": "coder", "task": "3", "spawnedAt": iso(NOW - timedelta(minutes=5)),
                "lastEventAt": iso(NOW - timedelta(minutes=4)), "status": "running", "files": [], "checkAfterSec": 900}
        data.update(fields)
        (self.run / "runs" / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")

    def touch(self, rel, when):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")
        os.utime(path, (when.timestamp(), when.timestamp()))

    def mail(self, box, frm, kind, task, body, name=None):
        (self.run / "mail" / box).mkdir(parents=True, exist_ok=True)
        name = name or f"20260924T115900_{frm}_{kind}_task{task}.md"
        (self.run / "mail" / box / name).write_text(
            f"from: {frm}\nkind: {kind}\ntask: {task}\nts: {iso(NOW - timedelta(minutes=1))}\n\n{body}\n", encoding="utf-8")
        return name

    def tick(self):
        return st.tick(self.run, self.root, NOW)

    def kinds(self):
        return [(a["priority"], a["kind"], a["run"]) for a in self.tick()["actions"]]


class QuietRun(unittest.TestCase):
    def test_a_healthy_run_yields_only_ok(self):
        f = Fixture(self)
        f.run_card("coder-3")
        self.assertEqual(f.kinds(), [("P4", "ok", "")])
        snap = json.loads((f.run / "state" / "supervisor.json").read_text(encoding="utf-8"))
        self.assertEqual(snap["tasks"], {"3": "IN_PROGRESS(coder-3)"})
        self.assertEqual(snap["firstMinute"], {"coder-3": "ok"})


class DoneWithoutAccept(unittest.TestCase):
    def test_done_letter_with_task_not_done_in_plan_is_p1(self):
        f = Fixture(self)
        f.run_card("coder-3", status="done")
        f.mail("lead", "coder-3", "DONE", "3", "DONE: task 3\nSUMMARY: works")
        self.assertIn(("P1", "accept_needed", "coder-3"), f.kinds())

    def test_once_lead_marked_done_the_action_disappears(self):
        f = Fixture(self)
        f.run_card("coder-3", status="done")
        f.mail("lead", "coder-3", "DONE", "3", "DONE: task 3")
        f.plan({"3": "DONE"})
        self.assertEqual(f.kinds(), [("P4", "ok", "")])


class Acceptance(unittest.TestCase):
    def test_accepting_status_silences_accept_needed(self):
        f = Fixture(self)
        f.run_card("coder-3", status="done")
        f.mail("lead", "coder-3", "DONE", "3", "DONE: task 3")
        f.plan({"3": "ACCEPTING(coder-3)"})
        self.assertEqual(f.kinds(), [("P4", "ok", "")])

    def test_a_ready_acceptance_report_is_p1(self):
        f = Fixture(self)
        f.run_card("coder-3", status="done")
        f.plan({"3": "ACCEPTING(coder-3)"})
        (f.run / "reports").mkdir()
        (f.run / "reports" / "accept-task3.md").write_text("ACCEPT: task 3 — PASS\n- criterion 1: PASS\n", encoding="utf-8")
        acts = f.tick()["actions"]
        self.assertEqual([(a["priority"], a["kind"]) for a in acts], [("P1", "accept_result")])
        self.assertIn("PASS", acts[0]["detail"])

    def test_a_reopened_task_is_the_coders_again(self):
        f = Fixture(self)
        f.run_card("coder-3", status="done")
        f.mail("lead", "coder-3", "DONE", "3", "DONE: task 3")
        f.plan({"3": "REOPENED(coder-6)"})
        self.assertEqual(f.kinds(), [("P4", "ok", "")])


class Escalations(unittest.TestCase):
    def test_stuck_letter_is_p0_and_ack_clears_it(self):
        f = Fixture(self)
        f.run_card("coder-3")
        name = f.mail("lead", "coder-3", "STUCK", "3", "STUCK: task 3. Commit failed")
        self.assertEqual(f.kinds()[0], ("P0", "stuck", "coder-3"))
        st.ack(f.run, name)
        self.assertEqual(f.kinds(), [("P4", "ok", "")])

    def test_ack_accepts_the_full_path_of_the_letter(self):
        f = Fixture(self)
        f.run_card("coder-3")
        name = f.mail("lead", "coder-3", "QUESTION", "3", "QUESTION: task 3. Which endpoint?")
        st.ack(f.run, str(f.run / "mail" / "lead" / name))
        self.assertEqual(f.kinds(), [("P4", "ok", "")])

    def test_question_is_p1_answer_needed(self):
        f = Fixture(self)
        f.run_card("coder-3")
        f.mail("lead", "coder-3", "QUESTION", "3", "QUESTION: task 3. Which endpoint?")
        self.assertIn(("P1", "answer_needed", "coder-3"), f.kinds())

    def test_stuck_status_in_run_card_is_p0(self):
        f = Fixture(self)
        f.run_card("coder-3", status="stuck", note="commit hook")
        self.assertEqual(f.kinds()[0], ("P0", "stuck", "coder-3"))


class PendingCopies(unittest.TestCase):
    def test_open_pending_line_older_than_two_minutes_is_p0(self):
        f = Fixture(self)
        f.run_card("coder-3")
        stamp = (NOW - timedelta(minutes=10)).astimezone().strftime("%H:%M")
        (f.run / "pending.log").write_text(f"{stamp} coder-3 -> unified-reviewer | REVIEW: task 3 | OPEN\n", encoding="utf-8")
        self.assertEqual(f.kinds()[0], ("P0", "deliver_pending", ""))

    def test_delivered_lines_are_ignored(self):
        f = Fixture(self)
        f.run_card("coder-3")
        (f.run / "pending.log").write_text("11:50 coder-3 -> unified-reviewer | REVIEW: task 3 | DELIVERED\n", encoding="utf-8")
        self.assertEqual(f.kinds(), [("P4", "ok", "")])


class FirstMinute(unittest.TestCase):
    def test_fresh_spawn_is_quiet_before_sixty_seconds(self):
        f = Fixture(self)
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(seconds=30)), lastEventAt=iso(NOW - timedelta(seconds=30)))
        self.assertEqual(f.kinds(), [("P4", "ok", "")])

    def test_silence_after_a_minute_is_p2_and_after_three_is_p1(self):
        f = Fixture(self)
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(seconds=90)), lastEventAt=iso(NOW - timedelta(seconds=90)))
        self.assertIn(("P2", "first_minute_silent", "coder-3"), f.kinds())
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(seconds=200)), lastEventAt=iso(NOW - timedelta(seconds=200)))
        self.assertIn(("P1", "first_minute_silent", "coder-3"), f.kinds())

    def test_a_task_file_touched_after_the_start_counts_as_life(self):
        f = Fixture(self)
        f.touch("src/t3.py", NOW - timedelta(seconds=100))
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(seconds=200)), lastEventAt=iso(NOW - timedelta(seconds=200)),
                   files=["src/t3.py"])
        self.assertEqual(f.kinds(), [("P4", "ok", "")])

    def test_a_task_file_touched_before_the_start_is_not_life(self):
        f = Fixture(self)
        f.touch("src/t3.py", NOW - timedelta(seconds=400))
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(seconds=200)), lastEventAt=iso(NOW - timedelta(seconds=200)),
                   files=["src/t3.py"])
        self.assertIn(("P1", "first_minute_silent", "coder-3"), f.kinds())

    def test_each_first_minute_alarm_sounds_once(self):
        f = Fixture(self)
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(seconds=90)), lastEventAt=iso(NOW - timedelta(seconds=90)))
        self.assertIn(("P2", "first_minute_silent", "coder-3"), f.kinds())
        self.assertEqual(f.kinds(), [("P4", "ok", "")], "та же P2 второй раз")
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(seconds=200)), lastEventAt=iso(NOW - timedelta(seconds=200)))
        self.assertIn(("P1", "first_minute_silent", "coder-3"), f.kinds())
        self.assertEqual(f.kinds(), [("P4", "ok", "")], "та же P1 второй раз")

    def test_a_participant_that_never_woke_becomes_silent_too_long_after_two_intervals(self):
        f = Fixture(self)
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(seconds=200)), lastEventAt=iso(NOW - timedelta(seconds=200)),
                   checkAfterSec=300)
        self.assertIn(("P1", "first_minute_silent", "coder-3"), f.kinds())
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(seconds=700)), lastEventAt=iso(NOW - timedelta(seconds=700)),
                   checkAfterSec=300)
        self.assertEqual(f.kinds()[0], ("P0", "silent_too_long", "coder-3"))

    def test_the_clock_starts_at_started_at_not_at_the_card(self):
        f = Fixture(self)
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(minutes=10)), startedAt=iso(NOW - timedelta(seconds=30)),
                   lastEventAt=iso(NOW - timedelta(seconds=30)))
        self.assertEqual(f.kinds(), [("P4", "ok", "")])

    def test_a_role_without_a_task_is_waiting_not_silent(self):
        f = Fixture(self)
        f.run_card("unified-reviewer", role="reviewer", task="", status="running",
                   spawnedAt=iso(NOW - timedelta(seconds=400)), lastEventAt=iso(NOW - timedelta(seconds=400)))
        self.assertEqual(f.kinds(), [("P4", "ok", "")])

    def test_an_own_event_after_spawn_counts_as_life(self):
        f = Fixture(self)
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(seconds=200)), lastEventAt=iso(NOW - timedelta(seconds=100)))
        self.assertEqual(f.kinds(), [("P4", "ok", "")])


class Checkpoints(unittest.TestCase):
    def test_checkpoint_fires_once_per_interval(self):
        f = Fixture(self)
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(minutes=40)), lastEventAt=iso(NOW - timedelta(minutes=20)))
        self.assertIn(("P3", "checkpoint", "coder-3"), f.kinds())
        self.assertEqual(f.kinds(), [("P4", "ok", "")], "вторая контрольная точка в тот же интервал")

    def test_silence_beyond_two_intervals_without_edits_is_p0(self):
        f = Fixture(self)
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(minutes=60)), lastEventAt=iso(NOW - timedelta(minutes=31)))
        self.assertEqual(f.kinds()[0], ("P0", "silent_too_long", "coder-3"))

    def test_an_old_uncommitted_edit_does_not_keep_a_silent_coder_alive(self):
        f = Fixture(self)
        f.touch("src/t3.py", NOW - timedelta(minutes=45))
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(minutes=60)), lastEventAt=iso(NOW - timedelta(minutes=31)),
                   files=["src/t3.py"])
        self.assertEqual(f.kinds()[0], ("P0", "silent_too_long", "coder-3"))

    def test_a_recent_edit_keeps_a_silent_coder_alive(self):
        f = Fixture(self)
        f.touch("src/t3.py", NOW - timedelta(minutes=5))
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(minutes=60)), lastEventAt=iso(NOW - timedelta(minutes=31)),
                   files=["src/t3.py"])
        self.assertNotIn("silent_too_long", [k for _, k, _ in f.kinds()])

    def test_shorter_interval_for_a_sensitive_task(self):
        f = Fixture(self)
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(minutes=20)), lastEventAt=iso(NOW - timedelta(minutes=6)),
                   checkAfterSec=300)
        self.assertIn(("P3", "checkpoint", "coder-3"), f.kinds())


class Engines(unittest.TestCase):
    def _call(self, f, role, label="001", done=False, taken=False, failed=False, alive_pid=None):
        d = f.run / "engine" / role
        d.mkdir(parents=True, exist_ok=True)
        base = d / f"{label}.out"
        (d / f"{label}.out.pid").write_text(str(alive_pid or 999999999))
        if done:
            base.with_name(base.name + ".done").write_text("status=failed\n" if failed else "status=done\n")
            os.utime(base.with_name(base.name + ".done"), (NOW.timestamp() - 1000, NOW.timestamp() - 1000))
        if taken:
            base.with_name(base.name + ".taken").write_text("")

    def test_dead_engine_worker_is_p0(self):
        f = Fixture(self)
        f.run_card("coder-3")
        self._call(f, "coder-3")
        self.assertEqual(f.kinds()[0], ("P0", "engine_dead", "coder-3"))

    def test_finished_but_unread_result_is_p0_after_fifteen_minutes(self):
        f = Fixture(self)
        f.run_card("coder-3")
        self._call(f, "coder-3", done=True)
        self.assertEqual(f.kinds()[0], ("P0", "engine_result_unread", "coder-3"))

    def test_taken_result_is_quiet(self):
        f = Fixture(self)
        f.run_card("coder-3")
        self._call(f, "coder-3", done=True, taken=True)
        self.assertEqual(f.kinds(), [("P4", "ok", "")])

    def test_failed_unread_is_p0_at_once(self):
        f = Fixture(self)
        f.run_card("coder-3")
        self._call(f, "coder-3", done=True, failed=True)
        self.assertEqual(f.kinds()[0], ("P0", "engine_failed_unread", "coder-3"))

    def test_running_engine_is_life_for_the_first_minute(self):
        f = Fixture(self)
        f.run_card("coder-3", spawnedAt=iso(NOW - timedelta(seconds=200)), lastEventAt=iso(NOW - timedelta(seconds=200)))
        self._call(f, "coder-3", alive_pid=os.getpid())
        self.assertEqual(f.kinds(), [("P4", "ok", "")])


class Ordering(unittest.TestCase):
    def test_actions_are_sorted_by_priority(self):
        f = Fixture(self)
        f.run_card("coder-3", status="done")
        f.mail("lead", "coder-3", "DONE", "3", "DONE: task 3")
        f.run_card("coder-4", task="4", status="stuck")
        self.assertEqual([a[0] for a in f.kinds()], ["P0", "P1"])


if __name__ == "__main__":
    unittest.main()
