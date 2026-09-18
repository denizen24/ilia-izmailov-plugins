# Phase 2: Execution — Monitor Mode (Detailed Protocol)

## Lead's Role: Coordinate Minimally, Narrate Continuously

Coders drive the review loop with the reviewer (and, on MEDIUM, tech-lead for escalations); they message each other directly. Lead steps in only for a message whose send came back `queued` — the sender hands Lead a copy and Lead delivers it once the recipient is idle (`team-runtime.md` §3). Lead also handles progress tracking and exceptional events — and **prints a live feed line for every meaningful event** (📢 column below). This is the user's only window into the work; without it Phase 2 is a black box.

Feed rules: user's language, product terms, one entry per event, always include the progress counter `{done}/{total}` on task events. See "Progress Feed" in SKILL.md.

## Event Handling

| Event from team member | Action | 📢 Print to chat |
|------------------------|--------|------------------|
| Any teammate: `QUEUED: <name>` + a message | The sender's direct message may be lost. Log it in `pending.log` and deliver it as `RESEND: from <sender>` once `<name>` is idle (`team-runtime.md` §3). Do not read the files it mentions. | Nothing. |
| Any teammate: `ALREADY ANSWERED: …` | The original got through after all. Mark the pending.log line `DELIVERED`. | Nothing. |
| Coder: `IN_REVIEW: task #N` | Set the task to `IN_REVIEW(coder-N)` in PLAN.md. | `🔎 Task #N in review: {short title}` |
| Coder: `DONE: task #N` | Set the task to DONE in PLAN.md. **If Phase is already VERIFICATION** (a Phase 3 conventions, fix or cleanup task): return to the Phase 3 step that was waiting on it — do not restart Phase 3. Otherwise spawn a coder for every task that just became available (TODO, all blockers DONE) while active coders < max. If every coding task is DONE (the conventions task does not count) → **change Phase in state.md to VERIFICATION and follow Phase 3 Instructions in state.md step by step.** | Task-done digest — see "Task-Done Digest" below. If transitioning: `🏁 All {N} tasks done — moving to verification.` |
| Coder: `QUESTION: task #N. [question]` | Answer from Phase 1 context if possible. If not — dispatch a researcher (Explore or general-purpose with WebSearch), then SendMessage the answer to coder. | Only if a researcher was dispatched: `🔍 Task #N raised a question ({what, in product terms}) — researching.` Answered-from-context questions are noise, don't print. |
| Coder: `STUCK: task #N` | First, try to answer from Phase 1 context. Only dispatch a researcher if the problem requires reading code not yet seen. Then: adjust the task, split it, or reassign to a different coder. | `⏸️ Task #N stuck: {problem in product terms} — {what Lead is doing about it}` |
| Coder: `LEGACY_FOUND: task #N` | Note it (entries are in LEGACY_REPORT.md; handled in Phase 3). | `🧹 Task #N left old code behind ({N} item(s)) — I'll ask you what to do with it at the end.` |
| Coder: `REVIEW_LOOP: task #N` | MEDIUM: the coder sends it to tech-lead directly — no action unless it reaches you as `QUEUED:`; no ruling from you. SIMPLE and COMPLEX: **you rule on it yourself** — ask both sides for their position in three lines each (you do not need to read the code to see which one matches the plan), decide, and write it to DECISIONS.md. If the disagreement is genuinely technical and you lack the knowledge, dispatch a researcher. | `⏸️ Task #N: review going in circles ({topic}) — {tech lead ruling / my ruling}: {outcome}.` |
| Unified Reviewer: `SENSITIVE: task #N — <why>. Files: <list>.` | The reviewer is parked waiting — **answer in this turn**, before anything else. Look up `second-reviewer` in `## Engines` of state.md — Step 0b resolved it once and it is never re-evaluated: an engine there → `SendMessage(to="unified-reviewer", message="SECOND REVIEWER: {engine}\ntask #N")`; `none`, or no such section at all → the same message with `SECOND REVIEWER: none`. On the engine answer, spawn the second opinion for this task — `second-reviewer-{task id}`, a second *opinion*, not a second verdict, by whichever spawn `engines.md` gives this role for the resolved engine (Mechanic B for an external one, the Claude teammate it names for `claude`), brief = the task, its changed files and the diff range, and **nothing the first reviewer produced** — and **in that same step** add `second-reviewer-{id}: task #N, spawned {HH:MM}` to `## Second opinions` in state.md (create the section on the first one). Both halves of that brief are already in front of you: the changed files are the `Files:` list of this message, and the diff range is `git diff {## Base Commit from state.md} -- {those files}` — you compose the range, you never run it. Do not open the files named in `<why>` or `Files:` — you do not review, you answer and spawn. **Idempotent:** the answer is a lookup in a table resolved once at Step 0b, so a `RESEND:`-ed `SENSITIVE: task #N` gets the same answer again; the spawn is not — if `## Second opinions` already lists that task, send the answer and **spawn nothing**. | Engine answer: `🔬 Задача #N — тема чувствительная ({тема в двух словах}), беру второе мнение у {engine}.` — never the `Files:` list, never the raw `<why>`. On `none`: nothing at all. |
| `second-reviewer-{id}`: task #N reached DONE, or you cancelled the instance | Remove that task's line from `## Second opinions` in state.md. **Those two events are the only ones that clear it** — never the instance merely finishing: it sends its findings to `unified-reviewer` and stands down, and the only messages you ever get from it are its proxy's `ENGINE RUNNING` and `ENGINE_DOWN`, so its turn ending is not an event you can see. A run in which it died, produced nothing, or never reached the reviewer looks exactly the same from here. While the line is there, the idle check (`team-runtime.md` §3) and "When a Second Opinion Does Not Come" can still release the parked reviewer; remove it early and nothing can. The instance is never respawned and never rotated. | Nothing — on DONE the task's own `✅` digest closes its `🔬` line, on a cancel the `🔬 …недоступно` line does. |
| Tech Lead: `DECISION: [one-liner]` (MEDIUM only) | No action — decision is already logged in DECISIONS.md by its author. On SIMPLE/COMPLEX you write these yourself. | `📋 Decision: {the one-liner, in product terms — what was decided and why}` |
| Proxy teammate: `ENGINE RUNNING: {role} on {engine}, started {HH:MM}` + output path | Record the start time and output path in state.md. No other action. **Exception — `second-reviewer-{id}`:** record it and print nothing. The `🔬` line for that task already told the user a second opinion is running; a second line for the same event would open something the feed never closes. | `⚙️ {role} работает на {engine}, запущен в {HH:MM}.` For `second-reviewer-{id}`, nothing. |
| Proxy teammate: `ENGINE_DOWN: {role}. {reason}` | `TaskStop` the proxy if it is still running. Apply `fallback` from the engine config (default `claude`): spawn the normal Claude teammate under the **same name** (latest wins). A reviewer or tech-lead successor gets its normal Step 5 prompt and replies READY; a coder successor gets the normal coder prompt with its task and starts working. After READY, deliver any `OPEN` pending.log line for that name, and SendMessage every coder whose task is `IN_REVIEW` (reviewer) or who escalated (tech-lead): "ROSTER UPDATE: {role} was replaced — if you are still waiting for an answer, re-send your request to {role}." If `fallback: "fail"`, stop the run and report. **Exception — `second-reviewer-{id}`: it has no successor.** `TaskStop` it, send `SendMessage(to="unified-reviewer", message="SECOND REVIEWER: none\ntask #N")` — the task id on the second line, since the reviewer may be parked on more than one task — clear that task's line from `## Second opinions`, and continue the run — full text in "When a Second Opinion Does Not Come". No fallback spawn: a Claude second opinion next to a Claude reviewer is not an independent one, it just costs twice and tags its findings `[second:claude]`. No ROSTER UPDATE either — coders do not know this name and must not learn it. | `⚙️ {engine} отвалился на роли «{role}» ({reason}) — переключил на Claude, работа продолжается.` For `second-reviewer-{id}`, that line instead, and only while that task's `🔬` is still open — not DONE, no close printed yet: `🔬 Второе мнение недоступно ({reason}) — ревьюер продолжает один.` |

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
- `PLAN.md` — task status: TODO → IN_PROGRESS(coder-N) → IN_REVIEW(coder-N) → DONE. You are its only writer.
- `state.md` — coder spawns/shutdowns, reviewer rotations, escalations, and `## Second opinions`:
  one line per live `second-reviewer-{id}`, written at the spawn and cleared when its task is DONE
  or when you cancel that instance — never when the instance itself finishes
  (see "When a Second Opinion Does Not Come")

## Compaction Recovery

If context feels incomplete or current state is unclear: read `.claude/teams/{team-name}/state.md`, `PLAN.md` and `pending.log` (deliver every `OPEN` line) — together they are self-describing (the **Phase** field in state.md tells which phase instructions to follow step by step; roster and exact commands are in state.md, task statuses in PLAN.md). Honor its `## Engines` section for later spawns — do NOT re-read `~/.claude/agent-teams.json` and do NOT re-probe the CLIs; if the section is absent, every role is Claude. A `## Second opinions` section, if there is one, lists the second opinions that were in flight: a compaction is one of the cases where the wait counts as expired, because nothing in a restored context tells you whether those findings already reached the reviewer, and an unseen park costs the run while a cancel costs one optional opinion. Treat each line per "When a Second Opinion Does Not Come" — including a line stamped `spawned` two minutes ago.

## When a Teammate Goes Quiet — Bounded Wait

A proxy that finishes its engine run and then stalls is the observed failure mode, seen twice. In
the worst case Lead waited **two hours**, then committed the coder's work itself — breaking its own
rule about never touching code, and paying for it in the most expensive context in the team.

**For a healthy task this section costs nothing.** The coder's DONE wakes you; you never check. What
follows runs only on suspicion.

**Never poll on a timer.** Do not schedule wakeups to ask "is it done yet" — each one is a full turn
at your context size, and in a real run forty of them bought nothing. You are woken by messages;
suspicion is what a check needs, not a clock.

### The check (one Bash call, at most three times, ≥15 minutes apart)

```bash
tail -3 .claude/teams/{team}/ledger.jsonl
ps -eo pid,etime,command | grep -E 'codex (exec|resume)|grok|kimi' | grep -v grep
```

Read the two together:

| Ledger tail | Engine process | Verdict |
|-------------|----------------|---------|
| `launch`, nothing since | alive | **Working.** Engine runs vary from minutes to over an hour. Wait. |
| `launch`, nothing since | gone | Engine died without the proxy noticing → treat as dead proxy |
| `engine_done` / `checks_done`, nothing since ≥15 min | gone | **Dead proxy.** The work exists, the reporter does not |
| `committed` but no DONE message | gone | Work is finished — just the message was lost. Handle it exactly like a DONE event: mark the task DONE in PLAN.md and spawn coders for what it unblocks |

### When the verdict is "dead proxy"

**Do not read the code and do not commit anything yourself.** Instead:

1. `TaskStop` the silent teammate. Confirm it stopped.
2. Spawn a **fresh coder** under a new name with a finishing brief, and set the task to `IN_PROGRESS({new name})` in PLAN.md:
   ```
   The engine already did the implementation for task {id}. Its report:
   .claude/teams/{team}/engine/{role}/{NNN}.out.md — read it.
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
| `ENGINE_DOWN: second-reviewer-{id}` | The proxy reported it — see the `ENGINE_DOWN` row above. This role's proxy runs its CLI in the foreground with `timeout: 600000`, so an engine that outlives that ceiling comes back empty even if it finished its work; the proxy reports that as `ENGINE_DOWN` like any other failure. The ceiling is not a path of its own — if the proxy never gets to report it, the idle check below is what catches the task |
| Your own end-of-turn idle check | `team-runtime.md` §3 — nobody running, a task still `IN_REVIEW`, and a line for it in `## Second opinions` |
| `ROTATION` of `unified-reviewer` | The successor was never parked on that task — nothing is handed over to it and no findings arrive for it later |

**One wait period, then `none` — regardless of what any probe says.** The first time a check fires
for that task, cancel it. Do not grant a second period, do not respawn the instance, do not ask it
for a status. This is not a guess about how long engines take: cancelling a second opinion costs the
run one optional opinion on one task, and a hang costs the run.

**If you check liveness at all, check the ledger, scoped to that instance:**

```bash
grep '"role":"second-reviewer-{id}"' .claude/teams/{team}/ledger.jsonl | tail -1
```

Nothing, `launch` with nothing since, or a `failed` line — the action is the same either way, so this
grep only fills `{reason}` in the feed line. **Do not use the `ps` grep from the section above for
this role:** it does not list `cursor-agent`, and neither that probe nor the bounded wait around it
says anything about which engine a second opinion runs on.

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
while that task's `🔬` is still open**: its status in PLAN.md is not DONE, and no `…недоступно`
line has gone out for it yet. Check both before printing — a cancel can fire long after that task's
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

When a coder reports DONE:
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
| A proxy teammate has been quiet for a long time | **Never guess from elapsed time — there is no expected duration, engine runs vary from two minutes to over an hour.** Establish the facts instead, in this order: (1) is the engine process alive? `ps -eo pid,etime,command \| grep -E 'codex (exec\|resume)\|grok\|kimi'`; (2) is the output file still growing? compare size and mtime a minute apart; (3) what does the output file already contain? If the process is alive or the file is growing → it is working, wait. If neither → the run has ended: read the output file, then ask the proxy to report. Only if the proxy itself does not answer twice do you shut it down and replace it. **`second-reviewer-{id}` is the exception** — no second period, no replacement, and that `ps` grep does not cover its engine anyway: cancel it per "When a Second Opinion Does Not Come". |
| Need best practices mid-session | Dispatch a web researcher (general-purpose with WebSearch). Don't research yourself — protect context. |
| Risk analysis reveals a CRITICAL confirmed risk requiring architectural change | Adjust PLAN.md based on Tech Lead's recommendations. If the risk requires a fundamentally different approach — re-plan affected tasks and re-validate with Tech Lead. |
| Risk tester and Tech Lead disagree on risk severity | Tech Lead's judgment takes priority — broader architectural context. Document the disagreement in DECISIONS.md. (Risk analysis happens in Phase 1, while architects are still present on COMPLEX.) |
| Convention violations keep recurring | This is a signal: missing or unclear gold standard. Note it for Phase 3 conventions update. |
