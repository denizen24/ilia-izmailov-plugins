# Engines — Pluggable Backends per Role

Every role in the pipeline is backed by an **engine**. The default engine for every role is
`claude` (a normal Claude Code subagent / teammate) — **with no config file everything runs on
Claude, exactly as before**. This file only matters when `~/.claude/agent-teams.json` exists and
assigns a role to an external CLI agent (Codex, Kimi, Grok, Cursor).

**Why offload:** external CLIs bill against a different subscription (ChatGPT / Moonshot / xAI / Cursor),
so work moved there consumes neither Claude context nor rate limit.

---

## Role Registry

Canonical role IDs. These are the keys usable in the config `roles` block.

| Role ID | Kind | Spawned at | Engine options |
|---------|------|-----------|----------------|
| `lead` | orchestrator | skill entry | **claude only** (owns team, tasks, user dialogue) |
| `codebase-researcher` | one-shot | Phase 1 Step 2 | claude, codex, kimi, grok, cursor |
| `reference-researcher` | one-shot | Phase 1 Step 2 | claude, codex, kimi, grok, cursor |
| `web-researcher` | one-shot | Phase 1 Step 2 | claude, grok (live search) |
| `risk-tester` | one-shot | Phase 1 Step 4b | claude, codex, cursor |
| `ci-verifier` | one-shot | Phase 3 Step 5c | claude, codex, cursor |
| `spec-verifier` | one-shot | Phase 3 Step 5c | claude, codex, cursor |
| `browser-verifier` | one-shot | Phase 3 Step 5c | **claude only** (needs Chrome MCP) |
| `legacy-scanner` | one-shot | Phase 3 Step 6 | claude, codex, cursor |
| `tech-lead` | teammate | Phase 1 Step 4b (MEDIUM) | claude, codex, kimi, grok, cursor |
| `architect` | teammate | Phase 1 Step 4c (COMPLEX) | claude, codex, kimi, grok, cursor |
| `architect-frontend` / `architect-backend` / `architect-systems` | teammate | Phase 1 Step 4c | per-persona override of `architect` |
| `unified-reviewer` | teammate | Phase 1 Step 5 (every level) | claude, codex, kimi, cursor |
| `second-reviewer` | teammate, per task (`second-reviewer-{task id}`) | Phase 2, on demand (SENSITIVE task) | claude, codex, kimi, cursor — **absent = off** |
| `coder` | teammate | Phase 1 Step 5, Phase 2 | claude, codex **(experimental)** |

`second-reviewer` is the one exception: it is off unless you list it. It gives a second *opinion*,
never a second verdict — the coder still hears one verdict, from `unified-reviewer`. It is also the
only role spawned per task rather than per run: Lead spawns a fresh `second-reviewer-{task id}` when
`unified-reviewer` marks a task SENSITIVE, it sends its findings to that reviewer and stands down.
Otherwise it is a teammate like any other and follows the mechanic below — including `engine: claude`,
which is the useful assignment when `unified-reviewer` itself runs on an external engine.

**Kind determines the mechanic:**

- **one-shot** → engine `claude` spawns a `Task()` subagent; a non-claude engine means **no Claude
  agent is created at all** — the spawner runs the CLI via Bash and reads the report.
- **teammate** → engine `claude` spawns the normal teammate; a non-claude engine spawns
  `agent-teams:proxy-teammate` under the same role name, which joins the team, speaks the team
  protocol, and delegates the thinking to the external CLI session.
  **`second-reviewer` matches neither half as written:** there is no normal teammate behind it (no
  `agents/second-reviewer.md` exists) and the name is never the role id — it is
  `second-reviewer-{task id}` on both engines. What is spawned, and out of what, is in
  "`second-reviewer` — a brief with no agent file behind it" below, which covers `claude` and the
  external engines alike. Read it before you spawn this role.

`lead` and `browser-verifier` ignore any assignment other than `claude` — warn once and continue.

**Retired role IDs:** `security-reviewer`, `logic-reviewer`, `quality-reviewer` no longer exist —
every task is reviewed by `unified-reviewer` alone. If a config still lists them, warn once
(`⚙️ Роли security/logic/quality-reviewer больше нет — ревью делает unified-reviewer; назначь движок
ему.`) and ignore those keys. Do NOT carry their engine over to `unified-reviewer` silently.

---

## Config File

Single user-level file: **`~/.claude/agent-teams.json`**. There is no project-level file.
If it does not exist, is unreadable, or is invalid JSON → all roles = `claude`, print nothing
except (on invalid JSON) one warning line.

### Minimal form

```json
{
  "roles": {
    "unified-reviewer": "codex",
    "risk-tester": "codex"
  }
}
```

Any role not listed = `claude`. `second-reviewer` is the one exception: it is off unless you list it —
a config that never mentions it gets no second opinion at all, not a Claude one.

### Full form

```json
{
  "enabled": true,
  "fallback": "claude",
  "roles": {
    "unified-reviewer": "codex",
    "risk-tester": { "engine": "codex", "effort": "xhigh" },
    "architect-backend": "codex",
    "web-researcher": "grok"
  },
  "engines": {
    "codex": { "model": "gpt-5.6-sol", "effort": "xhigh" }
  }
}
```

| Key | Meaning | Default |
|-----|---------|---------|
| `enabled` | Global kill switch. `false` → everything on Claude regardless of `roles`. | `true` |
| `fallback` | What happens when an assigned CLI is missing or fails: `"claude"` (silent fallback) or `"fail"` (stop the run). `second-reviewer` is exempt from both values: under `"claude"` it is skipped rather than substituted, under `"fail"` it is skipped rather than fatal — a missing optional CLI must not stop a run. | `"claude"` |
| `roles.<id>` | Engine name string, or object `{ engine, model?, effort?, sandbox? }`. `sandbox` is the role's access (`read-only` / `workspace-write`); engines without a sandbox flag map it through their preset — `cursor` turns it into its `mode` flags. | `"claude"` |
| `engines.<name>` | Override the built-in preset (model, effort, or the full `cmd`/`resume` templates). | built-in presets below |

**CLI flag `--engines=off`** on the skill invocation forces every role to `claude` for that run
(same as `enabled: false`). Use it to reproduce a bug without external variables.

---

## Built-in Engine Presets

These ship with the plugin. Users only override them when a CLI changes its flags.

Flags, models and session mechanics below were smoke-tested against codex-cli 0.146.0, kimi-code/k3
and grok-4.6 (2026-08-17) and Cursor Agent CLI 2026.09.02 (2026-09-08, re-run against 2026.09.10 on
2026-09-17): each engine answered a prompt and correctly recalled it after a resume.

**Placeholders.** `{prompt}` = `"$(cat <prompt file>)"`; `{prompt_file}` = the path itself, for
presets that interpolate the file on their own (`cursor`); `{sandbox}` = `read-only` or
`workspace-write` by the role's need (`coder`, `risk-tester` write, everything else reads);
`{mode_flags}` = the `mode` line of the preset for that same need; `{model}`, `{effort}` = the role
override or the preset default; `{session}` = the saved session id.
The templates below are written as shell strings; `scripts/run-engine.sh` takes the same command as
argv with `'{prompt}'` left for it to fill — the translation is in "Launching an Engine" below.
**Re-verify after CLI upgrades** — model names and resume flags do change.

**Judging success:** use the process exit code and whether a model reply is present. Do NOT treat
stderr noise as failure — Codex routinely prints
`ERROR codex_models_manager::cache: failed to load models cache: missing field base_instructions`
on a completely successful run.

### codex

```
cmd:     codex exec --skip-git-repo-check --sandbox {sandbox} -m {model} -c model_reasoning_effort="{effort}" "{prompt}" < /dev/null
resume:  codex exec resume {session} "{prompt}" < /dev/null
model:   gpt-5.6-sol
effort:  xhigh
sandbox: read → read-only, write → workspace-write
session: extract from output line matching `session id: <uuid>`
```

`< /dev/null` is MANDATORY — without it `codex exec` can hang on "Reading additional input from
stdin". Only `gpt-5.6-sol` works on a ChatGPT subscription; plain `gpt-5.6` requires a paid API key.

### kimi

```
cmd:     kimi -m {model} -p "{prompt}"
resume:  kimi -r {session} -p "{prompt}"
model:   kimi-code/k3
session: extract from the trailing line `To resume this session: kimi -r (session_[0-9a-f-]+)`
```

`--auto` / `--yolo` are incompatible with `-p`. Kimi has no sandbox flag — do not assign it
write-capable roles (`coder`, `risk-tester`). `-S` is accepted as an alias for `-r`, but `-r` is
what Kimi itself prints, so use `-r`.

### grok

```
cmd:     grok --sandbox {sandbox} --always-approve -m {model} --effort {effort} --session-id {session} -p "{prompt}"
resume:  grok --sandbox {sandbox} --always-approve --effort {effort} -r {session} -p "{prompt}"
model:   grok-4.6
effort:  high
sandbox: read → read-only, write → workspace-write
session: NOT printed by Grok — you mint it yourself. MUST be a real UUID (`uuidgen`)
```

`--always-approve` is MANDATORY — without it Grok silently exits in batch mode waiting for tool
approval.

**Sessions:** Grok prints no session id in `-p` mode, and a bare `grok -r` resumes *the most recent
session in the current directory* — two Grok-backed roles in the same project would silently share
one conversation. So mint one id per role (`uuidgen`) before the first call, reuse it on every
resume, and save it to the role's `session.txt` immediately — regenerating it later loses the
conversation. It MUST be a real UUID: a readable name like `grok-myteam-coder` is rejected — Grok
fails to start (observed in a live run on 2026-08-17).

### cursor

```
cmd:     cursor-agent -p --trust --output-format json --model {model} {mode_flags} -- "$(cat {prompt_file})"
resume:  cursor-agent -p --trust --output-format json --model {model} {mode_flags} --resume {session} -- "$(cat {prompt_file})"
model:   cursor-grok-4.6-xhigh
mode:    read-only → --mode ask, workspace-write → --sandbox enabled -f
session: extract from the JSON reply, field `"session_id": "<uuid>"` — it arrives with the reply, at the end
result:  the `result` field of the same JSON
```

Cursor Agent CLI, called as **`cursor-agent`**. It also installs an `agent` alias, but do not use
it: the Grok installer symlinks `agent` to Grok's own binary, so on a machine with both CLIs
`command -v agent` succeeds and the run launches Grok with Cursor's flags — failing on `--trust` with
an error that has nothing to do with Cursor. Runs on a Cursor subscription — no separate token bill.

`--trust` is MANDATORY — without it the CLI stops on the "do you trust this folder?" question in
non-interactive mode and does nothing.

**Read mode is real.** `--mode ask` was verified by instructing it to create a file: it refused and
no file appeared. That makes `cursor` safe for read-only roles without relying on a sandbox flag.
For write-capable roles (`risk-tester`) use `--sandbox enabled -f`.

**Sessions:** Cursor prints the id itself, in the `session_id` field of the JSON reply — read it
from there rather than minting your own (unlike Grok). `--output-format json` prints one object when
the run ends, so the id is known only when the call returns — `scripts/run-engine.sh` extracts it
into `session.txt` and the ledger `done` line at that moment. Verified: a second call with `--resume` recalled a word from the first
(354 input tokens against 17 536 from cache; re-verified 2026-09-17 against 2026.09.10).

**Prompt through a file.** Role briefs contain quotes, backticks and newlines; passing them inline
loses to shell quoting. Write the brief to a file and interpolate `"$(cat {prompt_file})"`.

**`--` before the prompt is MANDATORY** — without it a prompt that begins with `-` is parsed as an
option. Role briefs start with `---` (the agent file's frontmatter fence, or a `--- ROLE BRIEF ---`
header), so this is not an edge case: in a live run on 2026-09-17 both researchers died instantly
with `error: unknown option '--- ROLE BRIEF ---…'`, exit 1, empty session, and the only clue was in
the out file.

**Read mode cannot write files — the caller writes them.** Several roles are told by their own agent
file to *write* something (an architect writes `reports/debate-rN-{name}.md`, a reviewer writes
`reports/review-task{id}-…md`). Under `--mode ask` the engine cannot do that. Translate it: ask the
engine to return the full text in its reply, and the proxy (or Lead, for a one-shot) saves it to the
file the role would have written. State this in the brief, or the engine burns a turn failing.

**Binary path.** Installs to `~/.local/bin` (a symlink into `~/.local/share/cursor-agent/versions/`).
If the shell cannot find `cursor-agent`, prefix the call with `PATH="$HOME/.local/bin:$PATH"`.

**Model choice.** `cursor-agent --list-models` lists what the subscription allows. Do NOT route roles to
Claude models through Cursor — you already have that subscription, and the point of offloading is a
*different* blind spot, not the same model twice. Useful picks: `cursor-grok-4.6-xhigh` for
adversarial reading (security review, "what if"), `gpt-5.3-codex-xhigh` where the role must write
and run a script (risk-tester, verifiers), `gpt-5.6-sol-xhigh` for long diffs, `gemini-3.7-flash-high`
for cheap wide tree-walking (codebase-researcher).

**Grok on the critical path: take `grok-4.7-xhigh-fast`.** For `second-reviewer` and an architect
on Cursor — roles the team waits on — `grok-4.7-xhigh-fast` is the recommended model. Measured on
2026-09-23: a short task took 10.4 s against 16 s on plain `grok-4.7-xhigh`, with the same answer;
on real reviews plain xhigh spent 7–16 minutes a call, because it writes 50–60 thousand reasoning
tokens for a reply of a few thousand characters. Background critics that nobody waits on can keep
plain xhigh.

---

## Step 0b: Resolve Engines (Lead, once per run)

Run this before Phase 1 Step 1. It is cheap and must not be skipped when the config exists.

1. **Read config.** `Read ~/.claude/agent-teams.json`. Missing → engine table is all-`claude`,
   **skip the rest of Step 0b entirely** (zero cost for default users). Invalid JSON → all-`claude`
   plus one warning line to the user.
2. **Honor kill switches.** `--engines=off` or `"enabled": false` → all-`claude`, skip the rest.
3. **Probe the CLIs actually referenced.** One Bash call:
   `command -v codex kimi grok cursor-agent` — only the binaries of engines that appear in
   `roles` (the `cursor` engine's binary is `cursor-agent`, never `agent`; see its preset).
   Any missing binary → those roles fall back per `fallback`. **`second-reviewer` is exempt from
   both `"claude"` and `"fail"`**: a missing binary resolves it to `none` — it is skipped, never
   substituted, never fatal. A missing optional CLI must not stop a run.
4. **Build the engine table** — role ID → engine — and keep it for the whole run. Write it into
   `.claude/teams/{team-name}/state.md` under `## Engines` so it survives compaction, together with
   one line `- launcher: {absolute path of scripts/run-engine.sh}` — the plugin root is two levels
   above this skill's base directory (`{skill dir}/../../scripts/run-engine.sh`); if that is not at
   hand, `ls ~/.claude/plugins/cache/*/agent-teams/*/scripts/run-engine.sh | sort -V | tail -1`.
   `{plugin}/scripts/run-engine.sh` everywhere below means that path, and every proxy gets it in its
   spawn prompt (`LAUNCHER:` line, `phase1-planning.md` Step 5).
   Role IDs that are not in the Role Registry belong to other plugins sharing this file
   (`team-research`, `zero-downtime-deploy`) — leave them out of the table and the 📢 line.

   **Resolve `second-reviewer` here, once.** It becomes `none` when the key is absent, when its
   binary is missing, or when its engine is the one `unified-reviewer` resolved to; otherwise it
   becomes that engine. Record the outcome in the table like any other role
   (`second-reviewer → codex`, or `second-reviewer → none`). `none` is not an engine assignment: it
   is never printed, never appears in the 📢 line of step 5, and never makes that line print on a run
   that would otherwise print nothing. Steps 1 and 2 short-circuit before this point, so a run with
   no config, with `"enabled": false` or with `--engines=off` writes nothing and gets no second
   opinion — which is the same thing, said with no output. `none` is what Phase 1 reads when it
   decides whether `unified-reviewer`'s spawn prompt carries the `SECOND REVIEWER AVAILABLE: <engine>`
   line (`phase1-planning.md`); without that line nothing else in the run changes.

   The engine comparison is on the **resolved** engines in this table, and it happens here and
   nowhere else — never re-evaluated mid-run. When the two are equal, warn once (a second opinion
   from the same model as the first buys nothing) and treat the role as `none`:
   `⚙️ second-reviewer на том же движке, что и unified-reviewer — второго мнения не будет; укажите
   другой движок.`
5. 📢 **Print one line** only if at least one role is non-claude:
   `⚙️ Движки: {role} → {engine}, {role} → {engine} (остальные — Claude)`
   And if anything fell back: `⚙️ {engine} не найден — {role} работает на Claude.`

---

## Launching an Engine: `scripts/run-engine.sh` — the only way

Every external engine call — Lead's one-shot (Mechanic A) and every proxy call (Mechanic B) — goes
through `{plugin}/scripts/run-engine.sh`. Never call a CLI directly from Bash, in the foreground or
the background.

**Why a script, measured on 2026-09-23.** A foreground call "with `timeout: 600000`" does not bound
anything any more: Claude Code moves the command to the background by itself when the timeout runs
out (five cases out of five in two runs, at 120 s by default or at 600 s). In one task a proxy then
waited on the background task's output file — which only ever held `EXIT:0` — instead of the engine's
out file, copied that file over the finished engine reply, and relaunched the same prompt: about 24
minutes lost directly, and the reply of the first call, which lived only in the proxy's context, was
gone when the session restarted. Ledger times were typed in by hand and did not match the engine's.
The script removes each of those steps from the caller's hands.

**What it does.** It detaches itself from the caller (`setsid nohup`) and returns within a second,
printing the worker `pid`, the `out` path and the `done` marker path. The worker then:

- runs the command with stdin from `/dev/null` under `timeout --timeout` (default 3600 s), writing
  stdout+stderr to `<out>.part` and renaming it to `<out>` atomically when the engine exits;
- extracts the session id (`session_id` from the JSON reply for `cursor`; the preset's pattern for
  `codex` / `kimi`; `--session` for Grok, which you mint) into `session.txt`, and the reply — the
  JSON `result` field, or the whole output for engines that print plain text — into
  `<out>.result.md`;
- copies the reply to `reports/<name>` when `--report <name>` is given and the call succeeded;
- appends `launch` (at once, with the pid) and `done` / `failed` (with exit code, `wall_s`, session,
  paths) to `ledger.jsonl`, stamped with the real `date -Is`;
- writes `<out>.done` **last** — `status`, `exit`, `reason`, `started`, `ended`, `wall_s`, `session`
  and the paths. Its presence means everything above is already on disk.

It **never overwrites**: a label that already has an `out` (or a running `.part`) is skipped for the
next number (`001` → `002`) or the next suffix (`r1` → `r1-2`), and a report name that exists gets a
`-<label>` suffix. The prompt is copied next to its output as `<label>.prompt.md` if it lived
elsewhere. Files for one role live in `<run>/engine/<role>/`: `NNN.prompt.md`, `NNN.out`,
`NNN.out.pid`, `NNN.out.result.md`, `NNN.out.done`, `session.txt`, and `NNN.out.taken`, which the
caller writes (below).

**The engine command is argv after `--`, not a string** — no `eval`, no nested quoting. Write
`'{prompt}'` where the preset has `"{prompt}"` or `"$(cat {prompt_file})"`: the worker substitutes
the prompt file's text itself (and `{prompt_file}` with its path). Drop `< /dev/null` — the worker
already gives the engine no stdin. One argument is capped by the kernel at 128 KiB; a larger prompt
fails with exit 126, reported as `failed`.

```bash
S={plugin}/scripts/run-engine.sh; R=.claude/teams/{team}
# cursor, read-only role
PATH="$HOME/.local/bin:$PATH" $S --role {role} --run-dir $R --prompt $R/engine/{role}/draft.prompt.md \
  --engine cursor --task {id} [--report {file}.md] --timeout 1800 \
  -- cursor-agent -p --trust --output-format json --model {model} --mode ask [--resume {session}] -- '{prompt}'
# codex
$S ... --engine codex -- codex exec --skip-git-repo-check --sandbox {sandbox} -m {model} \
  -c model_reasoning_effort="{effort}" '{prompt}'          # resume: -- codex exec resume {session} '{prompt}'
# kimi
$S ... --engine kimi -- kimi -m {model} -p '{prompt}'      # resume: -- kimi -r {session} -p '{prompt}'
# grok: mint the id first, pass it both ways
$S ... --engine grok --session {uuid} -- grok --sandbox {sandbox} --always-approve -m {model} \
  --effort {effort} --session-id {uuid} -p '{prompt}'
```

A user override of a preset's `cmd` / `resume` template translates the same way. Give `--timeout` by
role: about 1800 for reviewers, `second-reviewer` and architects, 3600 or more for `coder` and
`risk-tester`. The timeout is the real ceiling now — the Bash tool's is not.

**Waiting is a separate call, on the marker only:**

```bash
until [ -f <out>.done ]; do sleep 5; done; cat <out>.done
```

Run it with `run_in_background: true`; its completion notification resumes you (verified
2026-09-18: a background `until` wakes a teammate with nobody else involved). Wait on nothing else —
not on the background task's own output file, not on `<out>` (it appears a moment before the
result is extracted), not on a timer.

**Read the reply from `<out>.result.md`**, and the outcome from the marker: `status=failed` with a
`reason` (`timeout …`, `exit N`, `no reply in output`, `engine reported is_error`, `no JSON reply`)
is a failed call. **Never copy anything over an `engine/` file** — every one of them is written once
and read many times. After you have read and relayed a reply, `touch <out>.taken`.

**Before any launch, check what is already there:**

```bash
{plugin}/scripts/run-engine.sh --status .claude/teams/{team} {role}
```

It prints one line per call: `RUNNING … pid=…` (process alive), `DONE-UNREAD …` (marker present,
no `.taken`), `taken …`, or `DEAD …` (no marker, process gone). **Never launch while the role has a
`RUNNING` or a `DONE-UNREAD` call** — wait on the running one, or read the unread one first. This is
what survives a session restart: the reply of a call made before the restart is on disk, with its
marker, and the next turn picks it up instead of paying for the same prompt again.

## Mechanic A: Delegated One-Shot

Replaces a `Task()` spawn for one-shot roles. The spawner (usually Lead) does this instead:

1. **Write the prompt to a file BEFORE launching** — never inline a long prompt in the shell
   command; quoting breaks. Path: `.claude/teams/{team-name}/engine/{role}/draft.prompt.md` — the
   launcher files it as `001.prompt.md` (or the next free number) next to the call's output.
   Content: the exact same prompt the Claude agent would have received, plus the Output Contract
   below. Writing it first is not bookkeeping — it is the only thing that survives a hang.

   **Pass paths, not contents.** The engine runs in the project directory and reads files itself.
   Pasting diffs or file bodies into the prompt means paying, in the caller's context, for bytes the
   engine could have read for free.
   The one exception is the gold standard block for a coder — those snippets may live outside the
   repository (in `.conventions/`), so name the path when there is one and inline only when there is
   not.

   **A role that reads a change gets the diff as a file, prepared by you** — see "The diff goes in a
   file" below. Never tell the engine to run `git` with `sudo` or with any other elevation.
2. **Launch it with `scripts/run-engine.sh`** (section above) — fill the placeholders as described
   under "Built-in Engine Presets": `{prompt}` / `{prompt_file}` are substituted by the script,
   `{sandbox}` / `{mode_flags}` come from the role's need (`risk-tester` → write, everything else →
   read). Pass `--report research-{role}.md` / `risk-{n}.md` / `verify-{role}.md` — the names
   `phase1-planning.md` "Save every report you receive" gives — so the reply is on disk under
   `reports/` without a step of yours.
3. **Wait on the `.done` marker** with the background `until` above. The ledger lines are written by
   the script; you add nothing.
4. **Read the report** from `<out>.result.md`, never from the terminal buffer, then `touch
   <out>.taken`. Treat it exactly as the Claude agent's return value.
5. **On failure** (`status=failed` in the marker, auth error, CLI missing) → apply `fallback`:
   `claude` = spawn the normal Claude agent for this role and print
   `⚙️ {engine} не ответил на {role} — переключаю на Claude.`; `fail` = stop and report.

### Output Contract (append to every external one-shot prompt)

```
Ты работаешь как модуль пайплайна, а не как ассистент в чате. Твой ответ — это данные для
оркестратора, а не сообщение человеку.

- Не изменяй файлы. {для risk-tester: временные скрипты складывай только в .claude/teams/<team>/tmp/}
- Отвечай строго в формате, заданном выше. Без вступлений, без "надеюсь, это поможет".
- Каждое утверждение подкрепляй ссылкой файл:строка. Без ссылки — помечай как предположение.
- Прежде чем сообщить о проблеме, проверь, нет ли уже защиты (middleware, обёртка, валидация
  фреймворка) — теоретические проблемы без конкретного кода не сообщай.
- Не хватает контекста — не выдумывай, заверши ответ строкой `ВОПРОС ОРКЕСТРАТОРУ: <вопрос>`.
- Не запускай `sudo` и ничего, что требует прав выше песочницы: в режиме только-чтение он не
  сработает. Дифф, если он нужен, уже лежит в файле — путь дан выше; git для него не запускай.
```

If the report ends with `ВОПРОС ОРКЕСТРАТОРУ:`, answer it from Lead's context and resume the
session with the engine's `resume` command (through `run-engine.sh`, next label) rather than
starting over.

---

## Mechanic B: Proxy Teammate

For conversational roles. The team keeps its shape: the coder still messages `unified-reviewer`
directly (`team-runtime.md` §3) and gets a normal review back.

Spawn `agent-teams:proxy-teammate` with the same `name` the Claude teammate would have had, and a
prompt containing:

- `ROLE: <role id>` and the **full role brief** — see "Preparing the Role Brief" below
  (`agents/unified-reviewer.md` etc.) so the external engine inherits identical instructions.
  `second-reviewer` has no agent file of its own; its brief is composed there, from the reviewer's.
- `ENGINE: <name>` plus the resolved `cmd` / `resume` / `sandbox` / session-extraction pattern.
- The same context block the Claude teammate would receive (feature summary, DoD, gold standards,
  confirmed risks, team roster).

The proxy's contract is defined in `agents/proxy-teammate.md`. Two rules matter most:

- **Session continuity** — the proxy opens ONE external session per role and `resume`s it for every
  later message, so round 2 of a review remembers round 1.
- **Triage before relay** — external engines over-report. The proxy verifies each finding against
  the cited lines and relays only what it can confirm. Details in the agent file.

Every call the proxy makes goes through `scripts/run-engine.sh` and is awaited on its `.done`
marker, exactly as in "Launching an Engine" above — including `resume` rounds. The proxy's answer
lives on disk from the moment the engine exits, so a proxy that dies, or a session that restarts,
loses nothing but the relay.

### When the proxy cannot start

If the proxy reports `ENGINE_DOWN: <role>. <reason>` to Lead, Lead applies `fallback` exactly as the
`ENGINE_DOWN` row in `phase2-monitoring.md` says: `TaskStop` the proxy if still running, spawn the
normal Claude teammate under the same name, let it reply READY (a coder successor gets its task
instead), then deliver that name's `OPEN` lines from `pending.log`,
and send a ROSTER UPDATE to coders still waiting on it (phase2-monitoring.md, `ENGINE_DOWN`). Print `⚙️ {engine} недоступен — {role} работает на Claude.`

`second-reviewer` has no successor: nothing is respawned, no ROSTER UPDATE is sent, Lead tells
`unified-reviewer` `SECOND REVIEWER: none` with `task #N` on the second line — several reviews can be
parked at once, so the task id is what releases one — and the run goes on with the one reviewer it
always had. The exact message and the full recovery are in `phase2-monitoring.md`.

---

## Preparing the Role Brief

An external engine must receive **the same instructions the Claude agent would have received** —
never a summary, never a rewritten "short version". The role brief is the agent file itself, with
three mechanical adjustments for things that only exist inside Claude Code. One role has no agent
file — `second-reviewer`; its brief is composed from the reviewer's, below, and that composition is
what its `claude` instance is given too, so that subsection is not external-engine-only.

**Keep, verbatim:**

- The entire body of `agents/{role}.md` — role definition, methodology, boundaries, checklists,
  output formats, rules. This is the whole point; a paraphrase loses the calibration.
- The `<example>` / `<example type="negative">` blocks from the frontmatter `description`. They are
  the role's few-shot examples and matter *more* for an external engine than for Claude, because the
  engine has no other calibration for what counts as in-scope.

**Drop:**

- The YAML keys `name`, `model`, `color`, `tools` — meaningless outside Claude Code. The engine has
  its own toolset, and its permission boundary is the `--sandbox` flag, not a tools list.

**Translate — the only place where wording changes:**

| Agent file says | Rewrite as |
|-----------------|------------|
| "send findings to the coder via SendMessage" | "return findings as your reply — the orchestrator passes them on" |
| "message tech-lead / Lead / another teammate" | "end your reply with `ESCALATE TO {recipient}: <message>`" |
| "you are READ-ONLY, never use Write or Edit" | keep the sentence AND enforce it with `--sandbox read-only` — instructions alone are not a boundary |
| messaging mechanics: `SendMessage`, `QUEUED:` / `RESEND:`, "end your turn while waiting" | "return it as your reply" — the proxy does the messaging |
| references to PLAN.md status updates / team roster mechanics | drop; Lead owns task state (PLAN.md), the proxy owns the conversation |

State this translation explicitly at the top of the brief so the engine knows why messaging verbs
are absent:

```
Ты работаешь через оркестратор: у тебя нет прямой связи с другими участниками команды.
Всё, что роль предписывает "отправить" кому-либо, ты возвращаешь в своём ответе —
оркестратор доставит это адресату.
```

**Same rule applies to Mechanic A.** A one-shot external role gets the same prompt text the Claude
one-shot agent would have received (the prompt printed in the phase document), plus the Output
Contract.

### The diff goes in a file, prepared by whoever launches the engine

Any role that reads a change — `unified-reviewer`, `second-reviewer`, a verifier — gets the diff as a
**file**, written before the launch by the one who launches the engine (Lead for a one-shot, the proxy
for a teammate), and the prompt names its path. The engine is never asked to produce the diff itself.

Measured on 2026-09-23: Lead's brief said `sudo -u admin git …`, the proxy carried it into the
prompt, and Cursor's read-only sandbox (`--mode ask`) does not let `sudo` run. The engine got no diff,
read the files as they stood, and returned "no findings" after 483 s; the rerun with the diff found
the real ones. Eight minutes lost to one word of a prompt.

```bash
R=.claude/teams/{team}; D=$R/engine/{role}-{n}.diff
git diff {base} -- {files} > "$D"
# new files that are not tracked yet: diff them against /dev/null — this reads, it never touches the index
git ls-files --others --exclude-standard -- {files} | while IFS= read -r f; do
  git diff --no-index -- /dev/null "$f" >> "$D"; done
```

`git diff --no-index` exits 1 when the files differ — that is its success. Do not use `git add -N`
or anything else that writes to the index: parallel coders share it. If git refuses the repository
as `dubious ownership`, add `-c safe.directory="$PWD"` to the `git` call — never `sudo`. You write
the file, you do not read it; the path goes into the prompt as `Дифф задачи: <path>`.

In every prompt to an engine: no `sudo`, and nothing else that needs more rights than its sandbox —
the Output Contract carries that line.

### `second-reviewer` — a brief with no agent file behind it

There is no `agents/second-reviewer.md` and none is planned. The brief is **composed**, the same way
on every engine, out of two parts:

1. **The body of `agents/unified-reviewer.md`**, kept and translated exactly as above. It is the same
   job — read this task's code and find what is wrong — and it carries the depth rule, the four
   priorities, the severity scale and the confidence signals, which is what makes the findings
   comparable with the first reviewer's.
2. **The findings-only contract**, which **replaces** that file's verdict and messaging sections
   (`Output Format`, `Write Your Findings to a File First`, `SendMessage Protocol`, and the whole
   `Second Opinion on a SENSITIVE Task` section — that one describes the first reviewer's side of
   this protocol, not yours) **and every line that tells the reviewer it is the only one and the last
   one**:

   | Overridden, named explicitly | Why it cannot stand |
   |---|---|
   | `<role>`: "the only code reviewer on this feature team … reviewed by you and nobody else before it is committed" | False for an instance that is by construction a second opinion on that task |
   | `<role>`: "Nobody reviews after you on a per-task basis. … they do not repeat your work, so what you miss here stays missed until then" | The reverse of this instance's place in the run: `unified-reviewer` re-checks every finding it sends against the code, and decides what reaches the coder |
   | `<role>`, HARD BOUNDARY: "Your ONLY output is review findings sent to the coder via SendMessage" | Names the wrong addressee — the findings go to `unified-reviewer` and to the findings file |
   | frontmatter `description`: "The one per-task code reviewer on every feature team, at every complexity level." | The first claim again, in the line a `claude` spawn loads along with the rest of the file |

   Everything else in that block stays as written: the one priority-ordered pass over security,
   logic, quality and fit, and the boundary's READ-ONLY, never Write or Edit on source, never fix it
   yourself. Leave any of the four standing and it beats the contract: the instance sends its
   findings straight to a coder, untriaged and next to a verdict the coder was going to get anyway,
   or treats a list nobody has checked yet as the last word on the task.

   The `description` row is a `claude`-path concern only. The keep list above takes the `<example>`
   blocks out of that frontmatter and nothing else, so on an external engine the sentence never
   enters the brief; a `claude` spawn gets the file whole, frontmatter included, and the contract has
   to name it like the rest. The `<example>` blocks themselves stay on both paths — they calibrate
   depth and what a CRITICAL has to carry, which is exactly what this instance needs. One of them
   shows a coder addressing the reviewer directly; the contract's "`unified-reviewer` is the only
   recipient you ever have" is what answers it, and that is why the line is written as an absolute.

```
You give a second opinion on task #N. You do not give a verdict.

Where this contract and the role file above disagree, this contract wins — it is written for the
second opinion, that file is written for the reviewer who owns the verdict. You are READ-ONLY on
source code exactly as it says; the only file you write is the findings file named below.

- Your output is findings only, each with its file:line. No approval, no "nothing to fix", no other
  line that can be read as a verdict — the coder hears exactly one verdict and it is not yours.
- Nothing you send is final. `unified-reviewer` opens every line you cite, checks the finding against
  the code as written, and only then decides what reaches the coder; what it cannot confirm is
  recorded as unconfirmed. Cite precisely and say where you are unsure — that is what makes a finding
  checkable, and an uncheckable one goes nowhere.
- Write your findings to .claude/teams/{team-name}/reports/review-task{id}-second-r{round}.md first,
  then send `SECOND OPINION: task #N` to `unified-reviewer`. That file is your record of this task.
- `unified-reviewer` is the only recipient you ever have. You never message a coder.
- **Do not open `.claude/teams/*/reports/` — ever, for any task.** `unified-reviewer` has already
  written its own review of this task there, and reading it is what this instance exists not to do:
  an opinion that has seen the first one agrees with it, and the run then credits you for a
  conclusion that was never yours. Read the changed files and the diff file named in your task
  (it lives under `.claude/teams/{team-name}/engine/`), nothing else under `.claude/`. Do not run
  `git` to rebuild the diff, and never `sudo`. If you have already opened a report, say so in your
  findings instead of hiding it.
- Then you are done — this instance lives for one task.
```

On an external engine the write line is translated like every other one: the engine returns the
findings in its reply and the proxy saves them to that path, because a `read-only` engine cannot
write it (`agents/proxy-teammate.md`).

**The brief is also defined by what it leaves out.** It carries the task, the list of changed files,
the diff range and the path of the diff file, and **nothing `unified-reviewer` produced**: no findings, no severities, no report
file, no hint of what the first reviewer already suspects. Reading the reports directory is forbidden,
and **the contract block above says so in its own words — that bullet is not optional and is not a
summary of this paragraph, it is the only place the instruction actually reaches the reader.** A
`read-only` sandbox does not enforce it: the engine can open those files perfectly well, and on the
`claude` path the instance is an ordinary subagent with `Read`. An engine shown someone else's framing
agrees with it; that is the whole reason for the rule.

**The findings file is part of the contract, not bookkeeping.** `review-task{id}-second-r{round}.md`
is where `unified-reviewer` expects the findings to be recorded, and Phase 3 counts those files to
report how many SENSITIVE tasks actually got a second opinion (`phase3-verification.md`). A round that
sends the message without writing the file is invisible in the summary.

**What is spawned, on either engine** — the teammate is named `second-reviewer-{task id}` both times:

| Resolved engine | Spawn |
|-----------------|-------|
| external | `Task(subagent_type="agent-teams:proxy-teammate", name="second-reviewer-{task id}", ...)` per Mechanic B, with the composed brief as its role brief. The proxy writes the findings file — a read-only engine cannot (`agents/proxy-teammate.md`). |
| `claude` | `Task(subagent_type="agent-teams:unified-reviewer", name="second-reviewer-{task id}", ...)` — the agent file the composition starts from — with the findings-only contract at the top of the prompt, stating that it overrides that file's verdict and messaging sections **and the four lines named above**. That spawn loads the file whole, frontmatter included; nothing translates for this instance and nothing stands between it and a coder, so the override has to be explicit. There is no `agent-teams:second-reviewer` subagent type. |

**The diff file for this role is Lead's.** Lead writes it at the spawn, as
`.claude/teams/{team-name}/engine/second-reviewer-{task id}-1.diff`, with the commands in "The diff
goes in a file" above, and puts its path in the brief — on both engines, since a `claude` instance
spawned from `unified-reviewer` has no Bash at all. Writing it costs Lead one Bash call and no
reading. A proxy that finds the file missing or empty writes it itself from the range in the brief.

**The ceiling is the script's `--timeout`, not the Bash tool.** On an external engine the proxy
launches through `scripts/run-engine.sh` with `--timeout 1800` and waits on the `.done` marker: the
engine cannot outlive that, and its reply is on disk the moment it exits, whatever happens to the
proxy (`agents/proxy-teammate.md`). The old rule — "foreground with `timeout: 600000` bounds the call"
— no longer holds: Claude Code moves such a call to the background when the timeout runs out instead
of ending it. On `claude` there is no proxy and no such ceiling: **the bound is the subagent's own
turn, and nothing states another one** — a Claude subagent carries no timer this plugin can set. When
that turn ends the parked reviewer is released either way — by `SECOND OPINION: task #N` if findings
came, otherwise at Lead's next end-of-turn idle check, which finds the task still `IN_REVIEW` with a
line in `## Second opinions` and handles it per "When a Second Opinion Does Not Come"
(`phase2-monitoring.md`). Until it ends, that check cannot fire
at all: it runs only when nothing is running (`team-runtime.md` §3), so a turn that never ends is
noticed by nothing. Lead's remedy is then the same two actions as on every other path, taken from any
turn it is already in: `TaskStop second-reviewer-{task id}`, then `SECOND REVIEWER: none` with
`task #N` on the second line.

### Which roles transfer well

Prefer to offload *read → produce a list* roles — reviewers, researchers, verifiers, `risk-tester`:
self-contained work with citable, checkable output. `second-reviewer` is the clearest case of all:
its whole value is being a *different* model from the one `unified-reviewer` runs on, reading the
same diff with a different blind spot. On the same engine as the first reviewer it adds nothing, and
Step 0b resolves it to `none` for exactly that reason. Keep `tech-lead`, `architect`
and `coder` on Claude — their value is judgment, cross-task memory,
project-convention knowledge, and team protocol, the parts that do not survive a CLI boundary.
This is guidance, not enforcement — the config allows any assignment in the registry — but when a
run produces confusing results, check the assignment against this list first.

---

## The Ledger — Record Addresses, Not Copies

**Every engine already records itself.** Codex writes the full conversation to
`~/.codex/sessions/YYYY/MM/DD/rollout-<time>-<id>.jsonl`, Kimi to `~/.kimi-code/sessions/` with an
index at `session_index.jsonl`, Grok to `~/.grok/sessions/<url-encoded-cwd>/<session-uuid>/`, Cursor to
`~/.cursor/chats/<md5 of cwd>/<session-uuid>/` (with `meta.json` naming the `cwd`) and a readable
transcript in `~/.cursor/projects/<cwd, slashes as dashes>/agent-transcripts/<session-uuid>/`. Claude
Code likewise records every agent and every message it sends. None of this needs an agent's
cooperation, and none of it can be forgotten.

So do not duplicate content for safekeeping. **What actually goes missing is the address** — which
recording belongs to which role, task and round. That is all the ledger stores.

### Format

One append-only file per run: `.claude/teams/{team-name}/ledger.jsonl`. One JSON object per line,
appended with `>>` — never rewritten, so concurrent writers cannot clobber each other.

```json
{"ts":"2026-09-23T10:19:13+02:00","event":"launch","role":"coder-6","engine":"cursor","task":"7","label":"001","pid":2558942,"prompt":"/…/engine/coder-6/001.prompt.md","out":"/…/engine/coder-6/001.out"}
{"ts":"2026-09-23T10:23:44+02:00","event":"done","role":"coder-6","engine":"cursor","task":"7","label":"001","pid":2558942,"exit":0,"wall_s":271,"session":"a7ced0f3-…","out":"/…/001.out","result":"/…/001.out.result.md"}
{"ts":"2026-09-23T10:26:02+02:00","event":"checks_done","role":"coder-6","task":"7","result":"pass"}
{"ts":"2026-09-23T10:27:15+02:00","event":"committed","role":"coder-6","task":"7","commit":"fcf0373"}
```

`event` is one of:

| Event | Written by | Meaning |
|-------|-----------|---------|
| `launch` | `run-engine.sh`, at once | The engine process started; `pid` is the worker to check with `kill -0` |
| `done` / `failed` | `run-engine.sh`, when the engine exits | The reply is on disk (`result`), or why not (`reason`); `wall_s` is measured, not estimated |
| `relayed` | the proxy | It triaged the reply and sent it on (it also `touch`es `<out>.taken`) |
| `checks_done` / `committed` | a coder proxy | Self-checks finished / the commit landed |

`engine_done` appears only in ledgers written before 0.13.1; read it as `done`.

The later events are what make silence diagnosable: a ledger whose last line for a role is `done`
from forty minutes ago tells Lead that the engine finished and the proxy stopped reporting — the
difference between "still thinking" and "dead", established without asking anyone. See
`phase2-monitoring.md` "When a Teammate Goes Quiet".

### Who writes it

**`scripts/run-engine.sh` writes `launch` and `done` / `failed`** for every engine call, with the
real time from `date -Is` — nobody types a time into the ledger by hand any more (on 2026-09-22 two
hand-written `engine_done` times were 17 and 26 minutes later than the engine actually finished). The caller — a proxy teammate, or
Lead for a one-shot role — adds only the events the script cannot know: `relayed`, and for a coder
`checks_done` and `committed`, each with `date -Is` for `ts`. One `>>` append each, no reading, no
coordination.

### When the ledger is missing

An agent that dies before writing its line loses nothing that matters: run

```bash
python3 {plugin}/scripts/engine-sessions.py <project-dir> --since HH:MM
```

It scans all four engines' own session stores, filters by working directory, and prints each
session's id, start time, record path and a ready `resume` command. This is the mechanical fallback
that makes ledger discipline non-critical — the map can always be rebuilt from disk.

### What the ledger replaces

Nothing else changes. `engine/{role}/NNN.prompt.md`, `NNN.out`, `NNN.out.result.md` and
`NNN.out.done` stay: the prompt file is how a long prompt is passed to the CLI at all, the reply file
is how the caller reads the result, and the marker is how it knows the result is complete. They are
mechanism, not backup. The ledger is what makes the engine's own recording findable afterwards.

---

## Rules

- **Never route a decision to an external engine.** Engines produce findings, reports, and drafts.
  Approving a deviation, resolving a review loop, choosing between design options, and deleting
  legacy stay with Claude roles (`lead`, and whichever of `tech-lead` / `architect` is on Claude).
  If `tech-lead` is external, its `DECISION:` lines still go through the proxy, which is
  responsible for sanity-checking them against DECISIONS.md before writing.
- **Never assign a write-capable role to an engine without a write sandbox** (`kimi`). Warn and
  fall back.
- **Everything an external engine says is unverified until checked.** This applies to reports too,
  not just review findings — a risk-tester report claiming "the API caps at 3 QPS" must cite the
  script and its output.
