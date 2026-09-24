# Phase 2: Execution — Monitor Mode (Detailed Protocol)

## Lead's Role: Coordinate Minimally, Narrate Continuously

Coders drive the review loop with the reviewer (and, on MEDIUM, tech-lead for escalations); they message each other directly. Lead steps in only for a message whose send came back `queued` — the sender hands Lead a copy and Lead delivers it once the recipient is idle (`team-runtime.md` §3). Lead also handles progress tracking and exceptional events — and **prints a live feed line for every meaningful event** (📢 column below). This is the user's only window into the work; without it Phase 2 is a black box.

Feed rules: user's language, product terms, one entry per event, always include the progress counter `{done}/{total}` on task events. See "Progress Feed" in SKILL.md.

## Sleep and Wake — the Supervisor Loop

Full protocol: `references/supervisor.md`. In short: Lead never waits in its own turn. After the
spawn and after every handled wake it starts `scripts/supervisor-wait.sh` in the background and ends
the turn; the script runs `scripts/supervisor-tick.py` every 20 s over the run files — teammates'
cards in `runs/`, their letter copies in `mail/lead/`, `pending.log`, the engine markers — and
returns, waking Lead, only when something of priority P1 or higher is waiting: a DONE not yet
accepted in PLAN.md, a question, a STUCK, a dead or unread engine, an undelivered `QUEUED` copy, a
teammate silent since its spawn. The printed action list is what Lead reads; the event table
below says what to do with each event, `supervisor.md` maps every action kind onto it.

On a wake that came from a letter or a completion notification rather than from the loop, run the
tick once first (`python3 {plugin}/scripts/supervisor-tick.py .claude/teams/{team-name}`) — it lists
everything that accumulated, not just the one message. Letters closed by an answer get
`supervisor-tick.py ack …`; a DONE is closed by its status in PLAN.md.

## Event Handling

| Event from team member | Action | 📢 Print to chat |
|------------------------|--------|------------------|
| Any teammate: `QUEUED: <name>` + a message | The sender's direct message may be lost. Log it in `pending.log` and deliver it as `RESEND: from <sender>` once `<name>` is idle (`team-runtime.md` §3). Do not read the files it mentions. | Nothing. |
| Any teammate: `ALREADY ANSWERED: …` | The original got through after all. Mark the pending.log line `DELIVERED`. | Nothing. |
| Coder: `IN_REVIEW: task #N` | Set the task to `IN_REVIEW(coder-N)` in PLAN.md. | `🔎 Task #N in review: {short title}` |
| Coder: `DONE: task #N` | **A DONE is a candidate, not a result.** Set the task to `ACCEPTING(coder-N)` in PLAN.md and spawn the acceptance checker — "Accepting a DONE" below. Only its `ACCEPT: task #N — PASS` makes the task DONE. Docs-only tasks (the conventions task, a cleanup that touches no code path) skip the checker: mark DONE at once. | `🔎 Задача #N сдана — принимаю по диффу.` |
| Acceptance checker: `ACCEPT: task #N — PASS` (its return value, or the loop's `accept_result` on the report file) | Write the report to `reports/accept-task{id}.md` if the checker was a Claude agent (an engine's `--report` already did). Set the task to DONE in PLAN.md. **If Phase is already VERIFICATION** (a Phase 3 fix task): return to the Phase 3 step that was waiting on it — do not restart Phase 3. Otherwise spawn a coder for every task that just became available (TODO, all blockers DONE) while active coders < max. If every coding task is DONE (the conventions task does not count) → **change Phase in state.md to VERIFICATION and follow Phase 3 Instructions in state.md step by step.** | Task-done digest — see "Task-Done Digest" below. If transitioning: `🏁 All {N} tasks done — moving to verification.` |
| Acceptance checker: `ACCEPT: task #N — FAIL` + the failed criteria | Once per task: set the task to `REOPENED(coder-M)` and spawn a **fresh** coder with the task section, the failed criteria quoted from the report and the handover note — the coder that sent DONE has stood down. Its DONE goes through acceptance again. A second FAIL is not retried: the task stays `REOPENED`, goes to Human Checks as unresolved with both reports, and the run continues. | `🔨 Задача #N не принята: {failed criteria in product terms} — поднял свежего кодера доделать.` Second time: `⏸️ Задача #N не прошла приёмку дважды — оставляю на ручную проверку.` |
| Coder: `QUESTION: task #N. [question]` | Answer from Phase 1 context if possible. If not — dispatch a researcher (Explore or general-purpose with WebSearch), then SendMessage the answer to coder. | Only if a researcher was dispatched: `🔍 Task #N raised a question ({what, in product terms}) — researching.` Answered-from-context questions are noise, don't print. |
| Coder: `STUCK: task #N` | First, try to answer from Phase 1 context. Only dispatch a researcher if the problem requires reading code not yet seen. Then: adjust the task, split it, or reassign to a different coder. | `⏸️ Task #N stuck: {problem in product terms} — {what Lead is doing about it}` |
| Coder: `LEGACY_FOUND: task #N` | Note it (entries are in LEGACY_REPORT.md; handled in Phase 3). | `🧹 Task #N left old code behind ({N} item(s)) — I'll ask you what to do with it at the end.` |
| Coder: `REVIEW_LOOP: task #N` | MEDIUM: the coder sends it to tech-lead directly — no action unless it reaches you as `QUEUED:`; no ruling from you. SIMPLE and COMPLEX: **you rule on it yourself** — ask both sides for their position in three lines each (you do not need to read the code to see which one matches the plan), decide, and write it to DECISIONS.md. If the disagreement is genuinely technical and you lack the knowledge, dispatch a researcher. | `⏸️ Task #N: review going in circles ({topic}) — {tech lead ruling / my ruling}: {outcome}.` |
| Unified Reviewer: `SENSITIVE: task #N — <why>. Files: <list>.` | The reviewer is parked waiting — **answer in this turn**, before anything else. Look up `second-reviewer` in `## Engines` of state.md — Step 0b resolved it once and it is never re-evaluated: an engine there → `SendMessage(to="unified-reviewer", message="SECOND REVIEWER: {engine}\ntask #N")`; `none`, or no such section at all → the same message with `SECOND REVIEWER: none`. On the engine answer, spawn the second opinion for this task — `second-reviewer-{task id}`, a second *opinion*, not a second verdict, by whichever spawn `engines.md` gives this role for the resolved engine (Mechanic B for an external one, the Claude teammate it names for `claude`), brief = the task, its changed files and the diff range, and **nothing the first reviewer produced** — and **in that same step** add `second-reviewer-{id}: task #N, spawned {HH:MM}` to `## Second opinions` in state.md (create the section on the first one). Both halves of that brief are already in front of you: the changed files are the `Files:` list of this message, and the diff range is `git diff {## Base Commit from state.md} -- {those files}`. **Before the spawn, write that diff to a file** — `.claude/teams/{team-name}/engine/second-reviewer-{id}-1.diff`, with the commands in `engines.md` "The diff goes in a file" (untracked new files included, index untouched, **never `sudo`**) — and put its path in the brief. You redirect it, you never read it. Do not open the files named in `<why>` or `Files:` — you do not review, you answer and spawn. **The reviewer gives no verdict on that task until your answer reaches it**, so make sure it does: a `queued` result → pending.log line and resend on its next completion notification (`team-runtime.md` §3); and **any completion notification from `unified-reviewer` whose text carries `PARKED: task #N — waiting for SECOND REVIEWER`**, or a bare `SENSITIVE: task #N …` line (its own send came back `queued` and it ended its turn with the line instead), is this same event — answer it again now. A `SENSITIVE:` that reaches you only that way is still the event of this row. **Idempotent:** the answer is a lookup in a table resolved once at Step 0b, so a `RESEND:`-ed or repeated `SENSITIVE: task #N` (or a `PARKED … waiting for SECOND REVIEWER`) gets the same answer again; the spawn is not — if `## Second opinions` already lists that task, send the answer and **spawn nothing**. | Engine answer: `🔬 Задача #N — тема чувствительная ({тема в двух словах}), беру второе мнение у {engine}.` — never the `Files:` list, never the raw `<why>`. On `none`: nothing at all. |
| `second-reviewer-{id}`: task #N reached DONE, or you cancelled the instance | Remove that task's line from `## Second opinions` in state.md. **Those two events are the only ones that clear it** — never the instance merely finishing: it sends its findings to `unified-reviewer` and stands down, and the only messages you ever get from it are its proxy's `ENGINE RUNNING` and `ENGINE_DOWN`, so its turn ending is not an event you can see. A run in which it died, produced nothing, or never reached the reviewer looks exactly the same from here. While the line is there, the idle check (`team-runtime.md` §3) and "When a Second Opinion Does Not Come" can still release the parked reviewer; remove it early and nothing can. The instance is never respawned and never rotated. | Nothing — on DONE the task's own `✅` digest closes its `🔬` line, on a cancel the `🔬 …недоступно` line does. |
| Tech Lead: `DECISION: [one-liner]` (MEDIUM only) | No action — decision is already logged in DECISIONS.md by its author. On SIMPLE/COMPLEX you write these yourself. | `📋 Decision: {the one-liner, in product terms — what was decided and why}` |
| Proxy teammate: `ENGINE RUNNING: {role} on {engine}, started {HH:MM}` + pid, output path and done marker | Record the start time, pid and done-marker path in state.md. No other action. **Exception — `second-reviewer-{id}`:** record it and print nothing. The `🔬` line for that task already told the user a second opinion is running; a second line for the same event would open something the feed never closes. | `⚙️ {role} работает на {engine}, запущен в {HH:MM}.` For `second-reviewer-{id}`, nothing. |
| Proxy teammate: `ENGINE_DOWN: {role}. {reason}` | `TaskStop` the proxy if it is still running. Apply `fallback` from the engine config (default `claude`): spawn the normal Claude teammate under the **same name** (latest wins). A reviewer or tech-lead successor gets its normal Step 5 prompt and replies READY — and for `unified-reviewer` that prompt carries its `SECOND REVIEWER AVAILABLE:` line on the same condition as every other spawn of it (`phase1-planning.md`), **with the engine comparison redone for this successor and for nothing else**: the successor now runs on `claude`, so if `second-reviewer` in the Step 0b table also resolved to `claude`, set it to `none` for the rest of the run, drop the line, and say so once — `⚙️ unified-reviewer перешёл на Claude, второе мнение было тоже на Claude — отключаю его: одна и та же модель второго мнения не даёт.` Otherwise carry the line unchanged. This is the one exception to "resolved once at Step 0b, never re-evaluated": the comparison exists so the two reviewers are never the same model, and a fallback is the one event that can make them the same. Dropping the line without this check silently ends second opinions for the run; carrying it without this check silently pairs Claude with Claude and tags its findings `[second:claude]`; a coder successor gets the normal coder prompt with its task and starts working. After READY, deliver any `OPEN` pending.log line for that name, and SendMessage every coder whose task is `IN_REVIEW` (reviewer) or who escalated (tech-lead): "ROSTER UPDATE: {role} was replaced — if you are still waiting for an answer, re-send your request to {role}." If `fallback: "fail"`, stop the run and report. **Exception — `second-reviewer-{id}`: it has no successor.** `TaskStop` it, send `SendMessage(to="unified-reviewer", message="SECOND REVIEWER: none\ntask #N")` — the task id on the second line, since the reviewer may be parked on more than one task — clear that task's line from `## Second opinions`, and continue the run — full text in "When a Second Opinion Does Not Come". No fallback spawn: a Claude second opinion next to a Claude reviewer is not an independent one, it just costs twice and tags its findings `[second:claude]`. No ROSTER UPDATE either — coders do not know this name and must not learn it. | `⚙️ {engine} отвалился на роли «{role}» ({reason}) — переключил на Claude, работа продолжается.` For `second-reviewer-{id}`, that line instead, and only while that task's `🔬` is still open — not DONE, no close printed yet: `🔬 Второе мнение недоступно ({reason}) — ревьюер продолжает один.` |

## Accepting a DONE — the parent verifies the diff, not the summary

The coder's digest says what it believes it did; the reviewer approved what it read. Neither is the
acceptance: a task is DONE when a **one-shot checker that has read nothing but the task and its diff**
confirms every acceptance criterion in PLAN.md. That is the porch rule "the parent owns the
acceptance", and it is why the criteria in PLAN.md have to be checkable (`phase1-planning.md`).

The checker is the `acceptance-checker` role (`engines.md`): on `claude` it is a
`Task(subagent_type="agent-teams:spec-verifier", ...)` with the prompt below; on an external engine
the same prompt goes through `scripts/run-engine.sh` with `--report accept-task{id}.md` and the diff
in a file (Mechanic A, no `sudo`, no `git` in the prompt). Lead spawns it and goes back to sleep on
the loop: the loop wakes Lead with `accept_result` the moment `reports/accept-task{id}.md` exists.

Before the spawn, one Bash call writes the diff — the task's commits, which the DONE digest names:

```bash
R=.claude/teams/{team}; git show {sha1} {sha2} -- {task files} > $R/engine/accept-task{id}.diff
```

```
Task(subagent_type="agent-teams:spec-verifier",
  prompt="ACCEPTANCE of task #{id}, team {team-name}. You verify the diff against the task's own
acceptance criteria — nothing else. You have not seen the coder's report or the review, and you do
not need them.

--- TASK (verbatim from PLAN.md) ---
{the whole ## Task {id} section}
--- END TASK ---
Diff of the task's commit(s): {path of accept-task{id}.diff}   (commits {shas}; do not rebuild it)
Deviation journal, if the task ran on an external engine: .claude/teams/{team-name}/reports/deviations-*-task{id}.md — read it if it exists; a deviation the coder did not resolve is a FAIL on the criterion it touches.
Out of scope (from the contract): {nonGoals}

For every acceptance criterion: run the command or check the fact, quote the output, verdict
PASS / FAIL / UNCLEAR. Then three global checks: (1) the diff touches only the task's files;
(2) the task's own test command from Tooling is green (run it — it is the one command you run
that changes nothing); (3) nothing in Out of scope changed.
Reply with exactly this shape, first line first:
ACCEPT: task #{id} — PASS            (or FAIL)
- {criterion}: PASS — {evidence}
- ...
Global: files PASS/FAIL, tests PASS/FAIL, scope PASS/FAIL
FAIL means at least one FAIL; UNCLEAR counts as FAIL and says what was unclear.")
```

Lead writes the return value to `reports/accept-task{id}.md` verbatim (one Write, no reading
beyond the first line), then acts on the first line per the event table. The report is the
task's acceptance record: Phase 3 counts `accept-task*.md` against the tasks and reports the
tasks that reached DONE without one.

**What this costs and buys.** One narrow one-shot per coding task — a spec-verifier starts small,
reads a diff and runs one test command, and dies. What it buys is the rule "no DONE is accepted on
the worker's summary alone": on 2026-09-17 a task passed three reviewers and the test suites while
quietly dropping a notice users rely on, and only a reader of the combined diff caught it later.

## First Minute and Adaptive Checkpoints

The tick (`supervisor.md`) watches every card from its `startedAt` — the coder's first
`run-state.py set … status=running` — and sounds each alarm once: `first_minute_silent` P2 at
60 s, P1 at 180 s with no letter, no touched task file and no engine; then the ordinary
checkpoints at the card's `checkAfterSec` (900 by default, 300 for a task the plan marks
RISK/SENSITIVE), and `silent_too_long` P0 after two intervals with no event and no task file
touched inside that window.

On the P1: `STATUS?` to the teammate. It answers what it is doing or waiting for; if it never
got its task (a lost spawn prompt, a wrong name), clarify and respawn. **Never respawn over a
live writer**: `TaskStop` the silent one, confirm, and only then spawn the replacement under a new
name — two coders on the same files destroy each other's uncommitted work. On `silent_too_long`
the same `STATUS?` first — a teammate asleep on its own background job wakes on it at once
(24.09.2026: 45 minutes of silence ended with one message) — and the dead-proxy remedy only when
that goes unanswered.

## Task-Done Digest

Coders' DONE messages carry a SUMMARY / REVIEW / EDGE CASES block (see coder.md Step 8). Print it as a compact digest:

```
✅ {done}/{total} done: {what now works, product language} ({N} review round(s))
   Review caught: {notable findings — only behavior/security-level, in product terms}
   Edge cases: {handled edge cases}
```

- Omit the "Review caught" line if there were no notable findings, and "Edge cases" if none — a clean task is a single ✅ line.
- If a coder's DONE arrives without the digest block (older format), print the single ✅ line from the task title — don't chase the coder for details.

## Noise Filter — What NOT to Print

The "Signal over noise" rules in SKILL.md apply. In addition: **never repeat anything already printed** — a decision that was already fed goes out once.

## What Lead Does NOT Do

Full list in SKILL.md and state.md — in short: no reading or reviewing code, no running checks, no picking reviewers, no editing or judging the messages you deliver. Delivering `QUEUED` copies is your job: an undelivered copy is a review that never happens.

## State File Updates

After every event, update the run files:
- `PLAN.md` — task status: TODO → IN_PROGRESS(coder-N) → IN_REVIEW(coder-N) → ACCEPTING(coder-N) → DONE (REOPENED(coder-M) once, on a failed acceptance). You are its only writer.
- `state.md` — coder spawns/shutdowns, reviewer rotations, escalations, and `## Second opinions`:
  one line per live `second-reviewer-{id}`, written at the spawn and cleared when its task is DONE
  or when you cancel that instance — never when the instance itself finishes
  (see "When a Second Opinion Does Not Come")

## Compaction Recovery

If context feels incomplete or current state is unclear: run one supervisor tick (`python3 {plugin}/scripts/supervisor-tick.py .claude/teams/{team-name}` — it rebuilds "who is where" from the run cards and letter copies), then read `.claude/teams/{team-name}/state.md`, `PLAN.md` and `pending.log` (deliver every `OPEN` line) — together they are self-describing (the **Phase** field in state.md tells which phase instructions to follow step by step; roster and exact commands are in state.md, task statuses in PLAN.md). Honor its `## Engines` section for later spawns — do NOT re-read `~/.claude/agent-teams.json` and do NOT re-probe the CLIs; if the section is absent, every role is Claude. A `## Second opinions` section, if there is one, lists the second opinions that were in flight: nothing in a restored context tells you whether those findings already reached the reviewer, so treat each line per "When a Second Opinion Does Not Come" at once — including a line stamped `spawned` two minutes ago. Its marker check is what tells a still-running engine (wait on its `.done`) from a finished one nobody relayed (deliver it) and from a dead one (cancel); a `claude` instance has no marker and counts as expired, because an unseen park costs the run while a cancel costs one optional opinion. Every other engine role: run `{launcher} --status` for it before relaunching anything — a `DONE-UNREAD` call is a reply that survived the compaction or restart and is read, not paid for again.

## When a Teammate Goes Quiet — Bounded Wait

A proxy that finishes its engine run and then stalls is the observed failure mode, seen twice. In
the worst case Lead waited **two hours**, then committed the coder's work itself — breaking its own
rule about never touching code, and paying for it in the most expensive context in the team.

**For a healthy task this section costs nothing.** The coder's DONE wakes you; you never check. What
follows runs only on suspicion.

**Never poll on a timer — with the model.** Do not schedule wakeups to ask "is it done yet" — each one is a full turn
at your context size, and in a real run forty of them bought nothing. You are woken by messages;
suspicion is what a check needs, not a clock. The supervisor loop (`supervisor.md`) is not the
model polling: it is `sleep` and a file scan, and it wakes you with the facts below already
established (`engine_dead`, `engine_result_unread`, `silent_too_long`).

### The check (one Bash call, at most three times, ≥15 minutes apart)

```bash
grep '"role": *"{name}"' .claude/teams/{team}/ledger.jsonl | tail -3
{launcher} --status .claude/teams/{team} {name}
```

`{launcher}` is the `launcher:` line of `## Engines` in state.md. `--status` reads the markers `scripts/run-engine.sh` leaves and checks the recorded pid with
`kill -0` — it covers every engine, `cursor-agent` included, which a `ps | grep` for engine names
does not. Read the two together:

| Ledger tail for that name | `--status` | Verdict |
|-------------|----------------|---------|
| `launch`, nothing since | `RUNNING … pid=…` | **Working.** Engine runs vary from minutes to over an hour, and the script's `--timeout` bounds them. Wait — if you want to be woken, start `until [ -f {out}.done ]; do sleep 5; done` in the background. |
| `launch`, nothing since | `DEAD` | Engine worker died without writing a marker → treat as dead proxy |
| `done` (or `engine_done` in an old ledger) / `checks_done`, nothing since ≥15 min | `DONE-UNREAD` | **Dead proxy.** The work exists, the reporter does not |
| `failed` | `DONE-UNREAD` with `status=failed` | The engine failed and the proxy never reported it → handle as `ENGINE_DOWN` |
| `committed` but no DONE message | `taken` | Work is finished — just the message was lost. Handle it exactly like a DONE event: mark the task DONE in PLAN.md and spawn coders for what it unblocks |

### When the verdict is "dead proxy"

**Do not read the code and do not commit anything yourself.** Instead:

1. `TaskStop` the silent teammate. Confirm it stopped.
2. Spawn a **fresh coder** under a new name with a finishing brief, and set the task to `IN_PROGRESS({new name})` in PLAN.md:
   ```
   The engine already did the implementation for task {id}. Its report:
   .claude/teams/{team}/engine/{role}/{NNN}.out.result.md — read it.
   Files it was allowed to touch: {list}.
   Your job is the tail only: verify with `git status` that nothing outside that list changed,
   run the self-checks, fix what fails by resuming the engine session {session id} — not by hand —
   and commit. Do not redo the implementation.
   ```
3. 📢 `⏸️ Кодер по задаче {id} перестал отвечать. Работа движка цела — поднял свежего кодера доделать проверки и коммит.`

A fresh finisher starts near 90k and does a handful of turns. That is strictly cheaper than you
reading the diff at 380k, and it keeps you out of the code.

## When a Second Opinion Does Not Come

`second-reviewer-{id}` is optional by construction, so there is one remedy and it is cheap. Two
actions, always the same two, keyed on the **task id** — never on "the second reviewer", because
several instances can be alive at once:

1. `TaskStop second-reviewer-{id}` (skip it if the instance already stopped), and remove that task's
   line from `## Second opinions` in state.md.
2. `SendMessage(to="unified-reviewer", message="SECOND REVIEWER: none\ntask #N")` — the canonical
   string on the first line, the task id on the second, since the reviewer may be parked on more than
   one task. It stops waiting, sends that coder its own verdict, and the task finishes normally.

**Three paths lead here, and none of them changes those two actions:**

| Path | How you notice |
|------|----------------|
| `ENGINE_DOWN: second-reviewer-{id}` | The proxy reported it — see the `ENGINE_DOWN` row above. This role's proxy launches through `scripts/run-engine.sh` with `--timeout 1800`, so an engine that outlives that ceiling ends with `status=failed` in its marker; the proxy reports that as `ENGINE_DOWN` like any other failure. The ceiling is not a path of its own — if the proxy never gets to report it, the idle check below is what catches the task |
| Your own end-of-turn idle check | `team-runtime.md` §3 — nobody running, a task still `IN_REVIEW`, and a line for it in `## Second opinions` |
| `ROTATION` of `unified-reviewer` | The successor was never parked on that task — nothing is handed over to it and no findings arrive for it later |

**First read the engine's marker — it decides whether the wait is over.** On an external engine the
second opinion runs through `scripts/run-engine.sh`, so there is a fact to check instead of a guess:

```bash
{launcher} --status .claude/teams/{team} second-reviewer-{id}
ls .claude/teams/{team}/reports/review-task{id}-second-r1*.md 2>/dev/null
```

| What you see | Action |
|---|---|
| `RUNNING … pid=…` | **Not a hang — do not cancel.** The engine is inside its `--timeout` (1800 s), so this ends on its own. Start `until [ -f {out}.done ]; do sleep 5; done` with `run_in_background: true` and end your turn: that notification is your next look at this task. The reviewer stays parked — its verdict waits for the opinion, which is the point of the park. |
| `DONE-UNREAD`, `status=done`, and the findings file exists | The findings exist and the relay did not happen — the proxy died or the session restarted (on 2026-09-23 this is how a finished Grok review sat unseen for most of an hour). Deliver it without reading it: `SendMessage(to="unified-reviewer", message="SECOND OPINION: task #N\nFindings: {that file} — relayed by Lead from the engine's reply; the proxy did not triage it.")`, then `touch {out}.taken`, `TaskStop second-reviewer-{id}` and remove the task's line from `## Second opinions`. The reviewer verifies every finding against the code anyway. No feed line: the `✅` digest closes the `🔬`. |
| `DEAD`, `status=failed`, `taken`, no calls at all — or the instance runs on `claude` | The wait is over: the two actions above, cancel with `SECOND REVIEWER: none`. A `taken` call was already relayed, and the `none` then only nudges a reviewer that is no longer parked. |

**Once the marker says the engine is over, one decision — no second period.** Do not respawn the
instance, do not relaunch its engine, do not ask it for a status. On `claude` there is no marker and
no timeout this plugin can set, so the first check that fires for that task cancels it, as before:
cancelling a second opinion costs the run one optional opinion on one task, and a hang costs the run.
The ledger line for the instance (`grep '"role": *"second-reviewer-{id}"' …/ledger.jsonl | tail -1`)
only fills `{reason}` in the feed line.

**The "dead proxy" remedy above does not apply here.** No fresh finisher coder, no replacement under
any name: there is no half-done work to rescue. A second opinion that did not arrive simply did not
happen, and the verdict the coder gets is unchanged.

**The state.md slot is a list.** One line per live instance, under `## Second opinions`:

```
## Second opinions
- second-reviewer-4: task #4, spawned 14:02
- second-reviewer-7: task #7, spawned 14:19
```

Written when you spawn the instance, removed when that task reaches DONE or when you cancel it —
**never when the instance finishes.** An instance that sent its findings and one that died in silence
look identical from your side, and in the second case the reviewer is still parked: the line is how
this section finds it. The idle check iterates every line and treats each task on its own — stopping
task #4's instance says nothing about task #7's. A run in which no task was ever marked SENSITIVE
has no such section at all.

**Every `🔬` line you print is closed, and closed once.** On the happy path the task's own `✅`
digest closes it. On every failure branch — engine down, wait expired, rotation, no answer — the
closing line is `🔬 Второе мнение недоступно ({reason}) — ревьюер продолжает один.`, printed **only
while that task's `🔬` is still open**: its status in PLAN.md is not DONE, no `…недоступно`
line has gone out for it yet, **and that task's second opinion did not in fact arrive** — one check,
`ls .claude/teams/{team-name}/reports/review-task{id}-second-r*.md`: a file there means the findings
reached the reviewer and the claim would be false. That third gate is what a compaction needs: the
recovery in this file treats every `## Second opinions` line as expired, and the line outlives the
park — it is cleared at DONE, while the park ends the moment the findings arrive. Without the check,
a task whose opinion arrived, was confirmed and folded in, and is merely still `IN_REVIEW` while its
coder fixes, gets told the opinion was unavailable while Phase 3 counts it as covered with confirmed
findings. Cancelling the instance in that state is still right; saying the opinion never came is not.
Check all three before printing — a cancel can fire long after that task's
second opinion arrived and was folded in, since the state line is cleared at DONE and not when the
instance finished, and closing a `🔬` the `✅` digest already closed contradicts the feed. What the
close claims is only what is true from here on: the rest of that task's review runs without a second
opinion. A branch that never printed a `🔬` line (`SECOND REVIEWER: none`, including the same-engine
skip) needs no close: silence is the whole output there. An opened line with no close is a bug in the
feed even when the run finishes fine.

## Rotating the Reviewer

The reviewer lives for the whole run, so it accumulates every review of every task — the same disease
the architects had. Measured on a real run with three reviewers: they took **55%** of the whole run,
and the heaviest one reached a 346k context and cost more than all eleven coders combined. With one
reviewer doing all the reviews, it fills up three times as fast.

**Rotate the reviewer every 3 completed tasks.** Do not wait for a moment with no review in
flight — with several coders in parallel that moment may never come. The reviewer finishes the
review it is on and reports what else it received; everything else is re-sent to the successor.

1. SendMessage to unified-reviewer:
   ```
   ROTATION. Finish the review you are on and send it to its coder. Then write a standing-findings note to
   .claude/teams/{team-name}/reports/standing-unified-reviewer-{n}.md — at most 15 lines:
   - issues you saw repeat across more than one task
   - decisions already settled, so your successor does not reopen them
   - what deserves extra suspicion in the remaining tasks
   Do NOT summarise your individual reviews — they are all in reports/. Then send DONE to Lead,
   listing any REVIEW request you received but did not review: "UNANSWERED: coder-N task #M".
   ```
2. Wait for DONE — its turn ends with it, there is no process to shut down. The reviewer is usually
   mid-review when ROTATION arrives, so the send may come back `queued`: then send ROTATION again on
   its next completion notification, until DONE arrives.
3. Spawn a fresh reviewer under **the same name** (so coders' rosters stay valid), with the normal
   Step 5 prompt plus:
   ```
   --- STANDING FINDINGS FROM YOUR PREDECESSORS ---
   {contents of reports/standing-unified-reviewer-*.md — all of them, 15 lines each}
   --- END ---
   ```
   "The normal Step 5 prompt" includes its `SECOND REVIEWER AVAILABLE:` line, on the same condition
   (`phase1-planning.md` Step 5 §1). Drop it here and the successor loses the second opinion for the
   rest of the run, silently — nothing checks for it.
   Wait for its READY. Then SendMessage every coder listed as UNANSWERED, and every other coder whose
   task is `IN_REVIEW` in PLAN.md: "ROSTER UPDATE: unified-reviewer was replaced — if you are still
   waiting for a verdict, re-send your REVIEW request to unified-reviewer." Deliver any `OPEN`
   pending.log line addressed to unified-reviewer to the successor.
4. 📢 `🔄 Ревьюер сменился — новый принял смену, накопленные наблюдения переданы.`

The successor starts near 100k instead of 350k. What is lost is the memory of individual past
reviews; what mattered — the cross-task patterns — is in the note, and every review itself is in
`reports/`.

**Do not rotate on a timer or on turn count** — only on the completed-task counter.

**This whole section is about `unified-reviewer`. `second-reviewer-{id}` never rotates.** It lives
for one task, sends its findings and stands down, so it never accumulates anything worth handing
over: no standing-findings note, no successor, no ROSTER UPDATE — no coder has ever heard its name.
When you rotate, cancel every instance listed in `## Second opinions` first — the ROTATION path in
"When a Second Opinion Does Not Come" above. Finish each cancellation whole — the `TaskStop`, the
`SECOND REVIEWER: none` with its task id, and the state.md line — **before you spawn the successor
in step 3**: the successor answers to the same name, so a `none` that lands after it starts releases
a park it never had. The instance is stopped, not handed over, and nothing arrives for the successor later.

## Spawning New Coders

When the acceptance checker reports PASS for a task (a coder's DONE alone sets `ACCEPTING`):
1. Set its task to DONE in PLAN.md.
2. Find the tasks that are now available — Status TODO and every "Blocked by" task DONE.
3. For each, while active coders < max: set it to `IN_PROGRESS(coder-N)` in PLAN.md, then spawn a
   fresh coder with the **same prompt as Phase 1 Step 5** — roster from state.md, the task section copied verbatim from PLAN.md, the handover notes of its blockers,
   the gold standard block. If foreign changes were present at Step 5,
   re-run `git status --short` and repeat the FOREIGN CHANGES block, since the list may have grown.
   If the `coder` role is on an external engine per the `## Engines` section of state.md, spawn
   `agent-teams:proxy-teammate` with the same name and the coder role brief instead — see
   `engines.md` Mechanic B.
4. Record the new coder in state.md.

## Stuck Protocol

When things go wrong, handle without involving the user:

| Situation | Action |
|-----------|--------|
| Tech Lead and a coder deadlock on an escalation (MEDIUM) | Review the disagreement. Only dispatch a web researcher if genuinely lacking domain knowledge. Make the final call, document in DECISIONS.md. |
| Coder escalates "pattern doesn't fit" | MEDIUM: forward to Tech Lead. SIMPLE and COMPLEX: decide yourself — this is a scope question and you own the plan. Check the architect review briefs in `reports/` first, they often already answer it. If unsure, dispatch a web researcher. Document in DECISIONS.md. |
| Build/tests fail after all tasks | Add targeted fix tasks to PLAN.md and spawn a coder per task. Only fix what's broken, don't redo completed work. |
| A coder goes idle unexpectedly | **Never conclude an agent is dead from files not changing** — an external engine can work for a long time without touching anything. **First check the fallback:** a coder waiting on a review ends its turn, so silence usually means a lost message. Deliver any `OPEN` line in `pending.log` for or from that coder (it survives compaction), then run the idle check (`team-runtime.md` §3, "When an answer does not come") — its `STATUS?` tells you what the coder is waiting for. Only after an explicit no-response — a second unanswered `STATUS?` well past any `ENGINE RUNNING` estimate — shut the coder down, confirm the shutdown, and only then spawn a replacement. **Never run two coders on the same files**; a duplicate destroys the first one's uncommitted work. |
| A proxy teammate has been quiet for a long time | **Never guess from elapsed time — there is no expected duration, engine runs vary from two minutes to over an hour.** Establish the facts instead: `{launcher} --status .claude/teams/{team} {name}` — it reads the markers `scripts/run-engine.sh` leaves and checks the recorded pid, for every engine including `cursor-agent`. `RUNNING` → it is working (bounded by the script's `--timeout`), wait. `DONE-UNREAD` → the run has ended and the reply is in `{out}.result.md`: ask the proxy to report it. `DEAD` → the engine is gone without a result: ask the proxy to report. Only if the proxy itself does not answer twice do you shut it down and replace it. **`second-reviewer-{id}` is the exception** — no replacement: handle it per "When a Second Opinion Does Not Come". |
| Need best practices mid-session | Dispatch a web researcher (general-purpose with WebSearch). Don't research yourself — protect context. |
| Risk analysis reveals a CRITICAL confirmed risk requiring architectural change | Adjust PLAN.md based on Tech Lead's recommendations. If the risk requires a fundamentally different approach — re-plan affected tasks and re-validate with Tech Lead. |
| Risk tester and Tech Lead disagree on risk severity | Tech Lead's judgment takes priority — broader architectural context. Document the disagreement in DECISIONS.md. (Risk analysis happens in Phase 1, while architects are still present on COMPLEX.) |
| Convention violations keep recurring | This is a signal: missing or unclear gold standard. Note it for Phase 3 conventions update. |
