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
  | lead → teammate | running, even inside its last tool call | delivered before its turn ends |
  | teammate → teammate | still running tool calls | delivered at its next tool call |
  | teammate → teammate | finished its turn | `success: true, queued` — **but never delivered** |

  Reviewers, tech-lead and waiting coders spend most of a run with their turn finished. Direct
  teammate-to-teammate messaging therefore loses exactly the messages the pipeline depends on, and
  the sender is told it succeeded.

Hence three rules: **no team lifecycle calls, the plan lives in a file, every message between
teammates goes through the lead.**

## 1. The team is implicit

- Pick the team name as before (`feature-<short-name>`). It names the run directory
  `.claude/teams/{team-name}/`, nothing else. Create the directory by writing the first file into it.
- Spawn teammates with `Task(subagent_type=..., name="<role name>", run_in_background=true, prompt=...)`.
  Do not pass `team_name`.
- Record every teammate in the state.md roster. If the runtime returns an agent id and a name is ever
  refused, address that teammate by its id and write the id next to the name in the roster.
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
  (COMPLEX) may edit the description of an existing task — acceptance criteria, risk notes — while
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
TO: security-reviewer, logic-reviewer, quality-reviewer, tech-lead
REVIEW: task #3. Files changed: src/server/routers/settings.ts
Gold standard references: src/server/routers/profile.ts
```

- `TO:` lists exact roster names, comma-separated. A message without `TO:` is for the lead itself
  (DONE, STUCK, QUESTION, DECISION, ROUND SUMMARY, ...).
- Send it with `SendMessage(to="main", ...)`. If you are ending your turn anyway, the final reply
  with the same header works too — it reaches the lead.
- **After sending something that needs an answer, end your turn.** Do not sleep, poll or re-read
  files while waiting: the answer arrives as a new message from the lead, and that message resumes
  you.
- Answers you receive start with `FROM: <name>`. Reply to that name through the same `TO:` header.
- Keep relayed messages short: verdict and file path. Detail lives in `reports/` (SKILL.md,
  "Everything Important Goes to a File") — the lead forwards text, it never reads your files for you.

### Lead side

For each incoming message with a `TO:` header:

1. For every name in `TO:` — `SendMessage(to="<name>", message="FROM: <sender>\n<body without the TO: line>")`.
   One message per recipient, in parallel. **Forward verbatim** — no summarising, no editing, no
   reading of the referenced files.
2. Apply the side effects the message implies (e.g. `IN_REVIEW` status in state.md, 📢 feed line).
3. If a name in `TO:` is not in the roster (stood down, rotated, never spawned), do not forward.
   Reply to the sender: `ROSTER: <name> is not on the team — current reviewers: ...`.

Relay costs the lead one short tool call per recipient and keeps it out of the code. It is not
"coordinating": the lead does not decide who reviews, does not wait for all verdicts, does not judge
them — coders still drive their own review loop.

### When an answer does not come

A missing answer means a lost or unsent message, not a slow teammate. Before anything else, check
your own transcript: did you forward it? If not, forward it now. If you did and the recipient ended
its turn without acting on it, send it again once with `RESEND:` in front of the body. Only a
recipient that ignores a resend is treated as stuck (phase2-monitoring.md).

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
