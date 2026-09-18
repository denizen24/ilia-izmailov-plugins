# Team Runtime: implicit team, plan file, lead relay

How the team physically exists and talks in current Claude Code. Every other file in this skill
assumes these rules; when one of them seems to say otherwise, this file wins.

## What the runtime gives you (measured, Claude Code 2.1.27x)

- **No `TeamCreate` / `TeamDelete`.** A session has one implicit team. `team_name` on `Task` /
  `Agent` is deprecated and ignored. A teammate is simply a background agent spawned with a `name`.
- **`TaskCreate` / `TaskGet` / `TaskUpdate` / `TaskList` are model-gated.** Claude Code offers them
  only to older models (Claude 3.x, Opus 4.0–4.7, Sonnet 4.x, Haiku 4.5) or when
  `CLAUDE_CODE_ENABLE_TODO_TOOLS` is set. On Opus 5 they are absent by default.
- **Messages are addressed by name.** `SendMessage(to="<name>")` reaches a teammate; a background
  teammate reaches the lead with `SendMessage(to="main")`, and its final reply reaches the lead
  anyway when its turn ends.
- **Delivery depends on the recipient's state** (in-process teammates — every session inside an IDE
  extension, and the default everywhere else):

  | Sender → recipient | Recipient state | Result |
  |---|---|---|
  | lead → teammate | finished its turn | delivered — the teammate is resumed |
  | lead → teammate | running, and it takes another tool round | delivered at that round |
  | lead → teammate | running, but it ends its turn without another tool round | `success: queued` — **not delivered** |
  | teammate → teammate | still running tool calls | delivered at its next tool call |
  | teammate → teammate | finished its turn | `success: true, queued` — **but never delivered** |

  The reviewer, tech-lead and waiting coders spend most of a run with their turn finished. Direct
  teammate-to-teammate messaging therefore loses exactly the messages the pipeline depends on, and
  the sender is told it succeeded.

  **Row 3 is the one that surprises a lead.** A teammate busy with someone else's request is not a
  safe recipient: on 2026-09-17 a reviewer mid-review for task #3 was sent task #2's request,
  answered #3, and ended its turn reporting "nothing further pending" — the second request was never
  in its transcript. So the idle check in §3 applies to **Lead's own forwards too**, not only to
  messages between teammates: a request stays open until the answer comes back, whoever sent it.

Hence three rules: **no team lifecycle calls, the plan lives in a file, every message between
teammates goes through the lead.**

## 1. The team is implicit

- Pick the team name as before (`feature-<short-name>`). It names the run directory
  `.claude/teams/{team-name}/`, nothing else. Create the directory by writing the first file into it.
- Spawn teammates with `Task(subagent_type=..., name="<role name>", run_in_background=true, prompt=...)`.
  Do not pass `team_name`.
- Record every teammate in the state.md roster. If the runtime returns an agent id and a name is ever
  refused, address that teammate by its id and write the id next to the name in the roster.
- **Respawning under the same name is safe.** When a newer agent takes a name, `SendMessage(to=name)`
  reaches the newest one ("latest wins"), so a rotated reviewer or an `ENGINE_DOWN` replacement keeps
  its name and coders' rosters stay valid.
- If agent teams are switched off (no `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`, policy, older build),
  nothing below changes: background agents plus lead relay is the whole mechanism.

## 2. The plan lives in `tasks.md`

`.claude/teams/{team-name}/tasks.md` is the single task list. Do not use `TaskCreate` and friends
even where they exist — a plan split between two stores drifts, and the tools vanish on model change.

```markdown
# Tasks — feature-{name}

## #1 Add settings API endpoint
Blocked by: —
Files: src/server/routers/settings.ts
Reference files: src/server/routers/profile.ts
Acceptance criteria:
- ...
Convention checks:
- ...
Tooling: test `pnpm vitest` · lint `pnpm biome check` · types `pnpm tsc --noEmit`
Feature DoD applies — see VERIFICATION_PLAN.md
```

- **Who writes:** Lead creates and edits tasks. Tech Lead (MEDIUM) and the Primary Architect
  (COMPLEX, Phase 1 only) may edit the description of an existing task — acceptance criteria, risk notes — while
  planning, when Lead is waiting on them. Coders never edit it.
- **Status is not in this file.** Status lives in state.md (`UNASSIGNED → IN_PROGRESS(coder-N) →
  IN_REVIEW(coder-N) → COMPLETED`), written only by Lead from the messages it receives.
- **Assignment is explicit.** Lead names the task id in each coder's spawn prompt. Coders do not
  claim tasks; one coder, one task, then it stands down.
- "Blocked by" is Lead's scheduling rule: never assign a task whose blockers are not COMPLETED.

## 3. Lead relay — the only messaging protocol

### Teammate side

Every message a teammate sends goes to the lead. A message meant for another teammate carries a
routing header on its first line:

```
TO: unified-reviewer
REVIEW: task #3. Files changed: src/server/routers/settings.ts
Gold standard references: src/server/routers/profile.ts
```

- `TO:` lists exact roster names, comma-separated. A message without `TO:` is for the lead itself
  (DONE, STUCK, QUESTION, DECISION, `ROUND N` answers, ...).
- Send it with `SendMessage(to="main", ...)`. If you are ending your turn anyway, the final reply
  with the same header works too — it reaches the lead. **One channel per message:** never send it
  both ways.
  **Prefer the final reply, and keep the two disjoint.** The runtime hands Lead your end-of-turn
  report whether or not you also called `SendMessage`, so a message sent both ways arrives twice and
  Lead cannot tell a repeat from a new request (every architect and reviewer did this in the
  2026-09-17 run until asked not to). If you do call `SendMessage` for something that must travel
  immediately, make your final reply a single line that names it — "REVIEW for task #3 sent" — never
  a second copy of the body.
- **After sending something that needs an answer, end your turn.** Do not sleep, poll or re-read
  files while waiting: the answer arrives as a new message from the lead, and that message resumes
  you.
- Answers you receive start with `FROM: <name>`. Reply to that name through the same `TO:` header.
- A message from Lead **without** a `FROM:` line is Lead's own question or instruction (ROTATION,
  STATUS?, a REVIEW_LOOP position request, ROUND N). Answer it to Lead, with no `TO:` line — whatever
  your role file says about not messaging Lead applies to routine work, not to this.
- **Exception — proxy teammates while their engine runs.** A proxy that launched its engine in the
  background stays in its turn until the engine process exits: it has nothing to be resumed by if it
  ends its turn early. "End your turn while waiting" applies to waiting on teammates, not on your engine.
- Keep relayed messages short: verdict and file path. Detail lives in `reports/` (SKILL.md,
  "Everything Important Goes to a File") — the lead forwards text, it never reads your files for you.

### Lead side

For each incoming message with a `TO:` header:

1. For every name in `TO:` — `SendMessage(to="<name>", message="FROM: <sender>\n<body without the TO: line>")`.
   One message per recipient, in parallel. **Forward verbatim** — no summarising, no editing, no
   reading of the referenced files. An exact repeat of a message you already forwarded is ignored.
2. Append one line per recipient to `.claude/teams/{team-name}/relay.log` (see below).
3. Apply the side effects the message implies (e.g. `IN_REVIEW` status in state.md, 📢 feed line).
4. If a name in `TO:` is not in the roster (stood down, never spawned), do not forward.
   Reply to the sender: `ROSTER: <name> is not on the team — current roster: ...`. A name that
   is mid-rotation is not "not on the team": hold the message and forward it to the successor.

### relay.log — what is still owed

Create it empty at Step 5, before the first teammate is spawned. One line per message Lead forwards
or sends itself, and one per answer addressed to Lead, appended with `>>`, never rewritten:

```
{HH:MM} {sender} -> {recipient} | {first line of the body}
{HH:MM} lead -> architect-backend | ROUND 2
{HH:MM} architect-backend -> lead | ROUND 2 from BACKEND: AGREE
{HH:MM} lead -> x | CLOSED: {what}      (closes everything open towards x for that subject)
```

A request is **open** until a message from its recipient back to its sender arrives:
`REVIEW` from coder-2 to unified-reviewer is open until a `unified-reviewer -> coder-2` line exists after
it; the same for `ESCALATION`, `QUESTION`, and `ROUND N` until `architect-x -> lead | ROUND N ...`.
Write `CLOSED:` when a request stops mattering (debate ended with FINAL, a task was re-scoped). The file survives compaction, so this is
how Lead knows what is owed after losing its context, and which pending review to re-forward when a
reviewer is rotated or replaced.

Relay costs the lead one short tool call per recipient and keeps it out of the code. It is not
"coordinating": the lead does not decide who reviews, does not wait for all verdicts, does not judge
them — coders still drive their own review loop.

### When an answer does not come

A missing answer means a lost or unsent message, not a slow teammate. Nothing wakes a team in which
every member has ended its turn — so the check has a fixed trigger:

**Idle check — before Lead ends a turn while work is unfinished and no teammate or engine is
running.** In this order:

1. **Flush first.** Every `TO:` message you received but never forwarded (no `relay.log` line) —
   forward and log it now. Forwarding an answer closes the request it answers.
2. **Then resend what is still open**, skipping any recipient marked `STOOD_DOWN` in state.md (close
   those with `CLOSED:` instead) and any name mid-rotation (its requests are held for the successor).
   Keep the envelope intact — the resend must look like the original with one extra line:
   `FROM: <original sender>\nRESEND:\n<original body>` (for Lead's own requests: `RESEND:\n<body>`).
3. Only a recipient that ignores a resend is treated as stuck (phase2-monitoring.md).

A teammate that receives a `RESEND:` for something it already answered sends the same answer again —
no new review.

## 4. Ending the run

There is no team to delete. At shutdown:

- Teammates whose turn has finished need nothing — they are idle transcripts, not processes.
- A teammate still running gets `SendMessage(to="<name>", message={"type": "shutdown_request"})`
  or `TaskStop`. Confirm it stopped.
- Mark every roster entry `STOOD_DOWN` in state.md.

## 5. Separate-process teammates (tmux / iTerm2) — untested

With `--teammate-mode tmux` or `iterm2` every teammate is its own process and may idle instead of
finishing, so teammate-to-teammate delivery could work there. This has not been measured. Keep lead
relay in that mode too until someone verifies that a message to an idle teammate is delivered.
