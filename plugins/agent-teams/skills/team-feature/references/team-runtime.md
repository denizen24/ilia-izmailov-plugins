# Team Runtime: implicit team, plan file, direct messages with a Lead fallback

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
- **Delivery depends on the recipient's state, and the tool result tells you which case you hit.**

  | Recipient state when you send | SendMessage result | Delivered? |
  |---|---|---|
  | finished its turn (idle) | `Resuming agent <name>` | **yes** — the recipient is woken with your message |
  | running, and it takes another tool round | `queued for delivery … at its next tool round` | yes, at that round |
  | running, but it ends its turn without another tool round | `queued for delivery … at its next tool round` | **no** — it finishes without reading it |

  Measured 2026-09-18 on Claude Code 2.1.276 (terminal and bb, with and without
  `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`, foreground and background agents): a message to an idle
  teammate returned `Resuming agent` and was answered every time. A message to a teammate that was
  finishing its turn returned `queued` and was never read. An earlier measurement on 2.1.272–274 in
  the IDE extension reported `queued` — and a loss — for idle teammates too.

  **So `Resuming agent` means delivered, and `queued` means maybe not.** The rule below needs no
  knowledge of which build or mode you are in: a sender that sees `queued` hands a copy to Lead.
  Row 3 is real in practice: on 2026-09-17 a reviewer busy with task #3 was sent task #2's request,
  answered #3, and ended its turn — the second request was never in its transcript.

Hence three rules: **no team lifecycle calls, the plan lives in a file, teammates message each
other directly and hand Lead a copy whenever delivery is not confirmed.**

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
  nothing below changes: named background agents plus `SendMessage` is the whole mechanism.

## 2. The plan lives in `PLAN.md`

`.claude/teams/{team-name}/PLAN.md` is the single task list, and its statuses are the single task
state. Do not use `TaskCreate` and friends even where they exist — a plan split between two stores
drifts, and the tools vanish on model change.

```markdown
# Plan — feature-{name}

Status values: TODO → IN_PROGRESS(coder-N) → IN_REVIEW(coder-N) → DONE. Only Lead edits this file.

## Task 1: Add settings API endpoint
Status: TODO
Blocked by: none
Files to create/edit: src/server/routers/settings.ts
Reference files (read for patterns): src/server/routers/profile.ts

Description: ...
Acceptance criteria:
- ...
Convention checks:
- ...
Tooling: test `pnpm vitest` · lint `pnpm biome check` · types `pnpm tsc --noEmit`
Feature DoD applies — see VERIFICATION_PLAN.md
```

- **Who writes:** Lead, and only Lead. Tech Lead (MEDIUM) and the architects (COMPLEX, Phase 1
  only) read it and send their changes — acceptance criteria, risk notes, new tasks — to Lead in
  their answers; Lead writes them in. Coders never edit it.
- **Status is in this file.** Lead sets `IN_PROGRESS(coder-N)` before the spawn, `IN_REVIEW` and
  `DONE` from the coder's messages. state.md keeps the roster, rotations and escalations, not task
  statuses — one store for each thing.
- **Assignment is explicit.** Lead copies the task section verbatim into the coder's spawn prompt.
  Coders do not claim tasks; one coder, one task, then it stands down.
- "Blocked by" is Lead's scheduling rule: a task is available when it is TODO and every blocker is
  DONE. The conventions task is never available in Phase 2 — Lead spawns it in Phase 3.

## 3. Messages: direct, with Lead as the fallback

### Teammate side

- **Send directly to the teammate:** `SendMessage(to="<name>", message="REVIEW: task #3. ...")`.
  Messages for Lead itself (DONE, STUCK, QUESTION, DECISION, `ROUND N` answers) go to `main`.
- **Read the tool result every time:**
  - `Resuming agent <name>` → delivered. Nothing else to do.
  - `queued for delivery …` → **not confirmed.** Immediately send the same text to Lead, prefixed
    with one line: `SendMessage(to="main", message="QUEUED: <name>\n<the same body>")`. Do not
    send it to the teammate a second time — Lead takes it from here.
  - an error, or an unknown name → `STUCK: cannot reach <name>` to Lead.
- **After sending something that needs an answer, end your turn.** Do not sleep, poll or re-read
  files while waiting: the answer resumes you. Ending your turn promptly also keeps you out of the
  "running, about to finish" state in which messages to you get lost.
- **A message whose first line is `RESEND: from <sender>`** is a copy Lead delivered because the
  original may have been lost. If you already answered that request, reply to Lead only
  `ALREADY ANSWERED: <its first line>` — no second review, no second message to the sender.
  Otherwise handle it normally and answer `<sender>` directly.
- **Answer every request that reached you** before ending your turn — two REVIEW requests can
  arrive in the same turn.
- **Exception — proxy teammates while their engine runs.** A proxy that launched its engine in the
  background stays in its turn until the engine process exits: it has nothing to be resumed by if it
  ends its turn early. "End your turn while waiting" applies to waiting on teammates, not on your engine.
- Keep messages short: verdict and file path. Detail lives in `reports/` (SKILL.md, "Everything
  Important Goes to a File").

### Lead side

Lead is not in the message path. It only picks up what the senders flag, and it never reads the
files a message points to.

**On `QUEUED: <name>` from `<sender>`:** append a line to `.claude/teams/{team-name}/pending.log`:

```
{HH:MM} {sender} -> {name} | {first line of the body} | OPEN
```

Then deliver it the moment `<name>` is idle — right away if it already is (its turn ended since the
send: you got its completion notification, or `ListAgents` shows it idle), otherwise on its next
completion notification:

```
SendMessage(to="<name>", message="RESEND: from <sender>\n<the body, verbatim>")
```

- `Resuming agent` → mark the line `DELIVERED`. If you got `queued` again, leave it `OPEN` and
  retry on the next completion notification.
- Forward verbatim — no summarising, no editing.

**Lead's own messages follow the same rule.** VALIDATE PLAN, DEBATE PLAN, ROUND N, FINAL, IDENTIFY
RISKS, ROTATION, ROSTER UPDATE, STATUS?: if the result is `queued`, add a pending.log line with
sender `lead` and send it again on that teammate's next completion notification. To avoid the case
altogether, send Lead's first instruction to a freshly spawned teammate only after its `READY` — every
long-lived teammate (reviewer, tech-lead, architects) is spawned with "reply READY and end your turn".
- If `<name>` was rotated or replaced meanwhile, deliver to the successor (same name, latest wins).

### When an answer does not come — idle check

Nothing wakes a team in which every member has ended its turn. So before Lead ends a turn while
work is unfinished and **no teammate or engine is running**:

1. Deliver every `OPEN` line in `pending.log` (as above).
2. For every task `IN_REVIEW` or `IN_PROGRESS` in PLAN.md whose coder is idle, send the coder
   `STATUS?`. It answers what it is waiting for and quotes the unanswered request in full. If it
   waits for a review or a ruling, resend that request yourself: `RESEND: from coder-N` + the quoted
   body. Do the same for any instruction of yours still unanswered (a ROTATION without DONE, a round
   without its answer): send it again.
   **Exception — a task listed in `## Second opinions` in state.md.** Its reviewer is parked waiting
   for a second opinion on that task — an opinion, never a second verdict — so resending that coder's
   REVIEW deepens the deadlock this check exists to break. Leave the REVIEW alone and handle the
   task per "When a Second Opinion Does Not Come" in `phase2-monitoring.md`.
3. Only a teammate that ignores a `RESEND:` or a `STATUS?` is treated as stuck (phase2-monitoring.md).

This check costs nothing on a healthy run: a team with a message in flight always has someone
running, and a team where everyone is idle with work left has lost something.

## 4. Ending the run

There is no team to delete. At shutdown:

- Teammates whose turn has finished need nothing — they are idle transcripts, not processes.
- A teammate still running gets `SendMessage(to="<name>", message={"type": "shutdown_request"})`
  or `TaskStop`. Confirm it stopped.
- Mark every roster entry `STOOD_DOWN` in state.md.

## 5. Separate-process teammates (tmux / iTerm2) — untested

With `--teammate-mode tmux` or `iterm2` every teammate is its own process and may idle instead of
finishing. This has not been measured. The rules above still hold, because they key off the tool
result, not the mode: `queued` always means "hand Lead a copy".
