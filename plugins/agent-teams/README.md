# Agent Teams

Launch a team of AI agents to implement features with built-in code review gates.

## Prerequisites

> **Agent teams are experimental and disabled by default.** Enabling them is recommended. The pipeline itself
> does not depend on the flag: teammates are named background agents messaging each other by name, so
> it also runs with teams off.

Add `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` to your `settings.json` or environment:

```json
// ~/.claude/settings.json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

Or set the environment variable:

```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```

Restart Claude Code after enabling.

### How the team talks (Claude Code 2.1.178+)

Current Claude Code has no `TeamCreate` / `TeamDelete` — every session has one implicit team — and
offers `TaskCreate` / `TaskList` only to some models (not to Opus 5 by default). And a message to a teammate that is just finishing its turn can be
lost — the tool then answers `queued` instead of `Resuming agent`. So the plugin:

- keeps the plan in `.claude/teams/<team>/PLAN.md`, owned by Lead;
- lets teammates message each other directly, and makes Lead the fallback: when a send comes back
  `queued`, the sender hands Lead a copy and Lead delivers it once the recipient is idle. Before
  going idle with work unfinished, Lead checks that nobody is still waiting on a lost message;
- ends a run by stopping whatever is still running — there is no team to delete.

Details and the delivery measurements: `skills/team-feature/references/team-runtime.md`.

## Installation

```bash
/plugin marketplace add izmailovilya/ilia-izmailov-plugins
/plugin install agent-teams@ilia-izmailov-plugins
```

## Usage

```
/interviewed-team-feature "Add user settings page"
/team-feature <description or path/to/plan.md> [--coders=N] [--no-research]
/conventions [path/to/project]
```

**`/interviewed-team-feature`** is the recommended entry point — it conducts a short adaptive interview (2-6 questions) to understand your intent, then launches `/team-feature` with a compiled brief.

**`/team-feature`** runs the full implementation pipeline directly — useful when you already have a detailed description or a plan file.

**`/conventions`** analyzes your codebase and creates/updates the `.conventions/` directory with gold standards, anti-patterns, and automated checks.

**Examples:**
```
/interviewed-team-feature "Add user settings page with profile editing"
/team-feature docs/plan.md --coders=2
/team-feature "Refactor auth to use JWT" --no-research
/conventions
```

## How It Works

### /interviewed-team-feature

A short adaptive interview before building:

1. Analyzes your request and the codebase
2. Asks 2-6 targeted questions (scope, audience, success criteria, exclusions)
3. Compiles a brief with all answers + project context
4. Launches `/team-feature` with the compiled brief (skipping redundant research)

The number of questions adapts — a vague "improve search" gets more questions than a detailed spec.

### /team-feature

A Team Lead agent orchestrates the full implementation pipeline. The pipeline adapts based on task complexity.

#### Phase 1: Discovery & Planning

**Step 1 — Quick Orientation**

Lead reads CLAUDE.md, checks project layout, and loads `.conventions/` gold standards if they exist. Does NOT read source files — that's what researchers are for.

**Step 2 — Adaptive Research**

Research is conditional — skips what's already known:

- If a brief from `/interviewed-team-feature` provides project context → skip codebase researcher
- If `.conventions/` has relevant gold standards → skip reference researcher
- If `--no-research` flag → skip all research

When needed, two researcher agents explore your codebase in parallel:

- **Codebase Researcher** scans the project structure, tech stack, patterns, and conventions. Returns a condensed summary.
- **Reference Researcher** finds the best existing code examples for each layer the feature touches. Returns **full file contents** — these become few-shot examples for coders.

Optionally, a **web researcher** is dispatched for features requiring external knowledge (OAuth, real-time, etc.).

**Step 3 — Complexity Classification**

The Lead evaluates the feature against concrete triggers (not subjective judgment):

| Level | Triggers | Team |
|-------|----------|------|
| **SIMPLE** | 0-1 medium triggers | Lead + Coder + Reviewer (3 agents) |
| **MEDIUM** | 2-3 medium triggers, 0 complex triggers | Lead + Tech Lead + Reviewer + Coders + Risk Testers (4+ agents) |
| **COMPLEX** | 4+ medium triggers OR any complex trigger | Lead + 3 Architects (debate only) + Reviewer + Coders + Risk Testers (5-8+ agents) |

Complexity changes planning, never the number of reviewers: every task gets exactly one review.

**Medium triggers** (6 checks): 2+ layers touched, changes existing behavior, near sensitive areas, 3+ tasks, task dependencies, 5+ files.

**Complex triggers** (7 checks): 3 layers simultaneously, changes shared code, direct auth/payments changes, 5+ tasks, 3+ dependent task chain, no gold standard exists, 10+ files.

**Step 4 — Plan Validation**

Depends on complexity:

- **SIMPLE:** Skip validation entirely.
- **MEDIUM:** Tech Lead reviews the task list — checks scoping, file assignments, dependencies, architectural approach.
- **COMPLEX:** 3 Architects (Frontend, Backend, Systems) debate the specification before coding starts. See [Architect Debate](#architect-debate-complex-only) below.

**Step 4b — Risk Analysis** *(MEDIUM and COMPLEX only)*

Tech Lead / Primary Architect identifies what could go wrong, then **Risk Testers** verify each risk by reading code and running test scripts:

| Risk Analysis (before code) | Review (after code) |
|------------------------------|---------------------|
| "This migration will delete user data" | "This migration has a syntax error" |
| "Auth middleware won't cover new routes" | "Auth check missing on line 42" |
| "Two tasks will create conflicting DB columns" | "Column name doesn't match convention" |

Risk Testers are spawned in parallel — one per CRITICAL/MAJOR risk. Confirmed risks are added as mitigation criteria to task descriptions before coding begins.

#### Architect Debate (COMPLEX only)

For complex features, 3 specialized Architects settle the specification before any code is written:

1. **Spawn 3 Architects** — Frontend (UI/components/accessibility), Backend (API/DB/data integrity), Systems (testing/CI/DX)
2. **Debate phase** — each architect critiques the plan from their expertise, debates with the others through round files that Lead collects (max 3 rounds)
3. **Verification checks** — each architect contributes checks from their domain to the verification plan
4. **Convergence** — architects send "SPEC APPROVED" with final recommendations
5. **Handover** — each architect writes a ≤25-line review brief for its domain: what a reviewer must
   check in this feature, the traps found during the debate, which boundaries deserve suspicion
6. **Stand down** — all three architects shut down, Primary included. The briefs go into the
   reviewer's prompt, and the reviewer (unified-reviewer) does the code review from Phase 2 on.

**Why they leave.** An architect is cheap in debate and expensive in review, because by review time it
carries the whole debate transcript. Measured on real runs: an architect's debate turn cost ~36k
tokens, its review turn ~143k — same agent, four times the price. Three architects were consuming
54–69% of an entire run against 12–17% for every coder combined. Ending their tenure cut that to 5.8%.

Escalations, pattern-deviation rulings and `DECISIONS.md` go to the Lead; the final cross-task
consistency check is a one-shot agent over the combined diff.

#### Phase 2: Execution

**Coders with Gold Standards**

Coders receive their task along with gold standard examples — real files from your project. Each coder:

1. Reads gold standards and reference files
2. Implements matching the same patterns
3. Runs self-checks (build, lint, type check, convention checks)
4. Sends one review request directly to the reviewer
5. Fixes feedback, gets approval, commits
6. Writes a ≤10-line handover note and **stands down** — the next task gets a fresh coder

Each coder lives exactly one task. Task history helps nobody but is re-read on every remaining turn,
so carrying it is pure cost; anything genuinely worth passing on goes in the handover note.

**The reviewer rotates too** — every three completed tasks, without waiting for a quiet moment:
the retiring reviewer finishes the review it is on, and coders still waiting are told to re-send
their request to the successor.
The retiring reviewer leaves a ≤15-line standing-findings note (what repeated across tasks, what is
already settled) and the replacement takes the same name, so coders' rosters stay valid. Without
rotation, the reviewer accumulates every review of every task and becomes the most expensive agent
in the run.

**Review — one pass per task**

Coders drive the review process and message the reviewer directly; Lead is not in the loop — see "How the team talks" above.

Every task, at every complexity level, passes two gates before commit:

1. **Coder self-check** — conventions checklist, then linter, type checker and tests.
2. **One review** by the Unified Reviewer, in priority order:

| Priority | What it catches |
|----------|----------------|
| **Security** | SQL injection, XSS, auth bypasses, exposed secrets, IDOR |
| **Logic** | Race conditions, off-by-one errors, null handling, async issues |
| **Fit with the plan** | Deviations from gold standards not recorded in DECISIONS.md, contradicted decisions |
| **Quality** | DRY violations, unclear naming, wrong abstractions, dead code |

When a task touches auth, payments, migrations or shared infrastructure, the reviewer goes deeper
on its own — it traces every path from user input to storage and response, and it marks the task
SENSITIVE. A SENSITIVE task can also be read by `second-reviewer` — a second *opinion*, not a second
verdict — on a different engine, if you configured one: its findings go to the reviewer, which still
issues the single verdict the coder gets. See Engines below.

Everything that needs the whole feature in view is checked once, at the end: cross-task
consistency (Tech Lead on MEDIUM, a one-shot checker otherwise) and the verifiers in Phase 3.

#### Phase 3: Completion & Verification

**Step 1 — Conventions Update**

A dedicated conventions task (the last task in PLAN.md; Lead spawns it only here, after every coding task is committed) creates/updates `.conventions/` with patterns discovered during implementation, recurring review issues, and approved deviations.

**Step 2 — Integrated Verification**

Verification runs **before** shutting down the team, so coders can fix failures:

1. Three verifier agents run in parallel:
   - **CI Verifier** — build, typecheck, tests
   - **Browser Verifier** — pages load, elements visible, interactions work, no console errors
   - **Spec Verifier** — file existence, exports, API responses, config values

2. **Fix-verify loop** — if checks fail, coders fix while the team is still alive (max 3 iterations)

3. **Status taxonomy:**
   - PASS / FAIL (code problem) / SKIP (capability or n/a) / UNCLEAR / DEGRADED (agent crashed) / BROKEN (environment issue)

4. **Verification manifest** — integrity audit comparing items sent vs reported

5. Items that can't be auto-verified are collected as **Human Checks** and presented to the user after completion.

**Step 3 — Summary Report**

```
══════════════════════════════════════════════════
FEATURE COMPLETE — VERIFIED
══════════════════════════════════════════════════
Tasks completed: 4/4
Complexity: MEDIUM
Commits: [list]

Risk analysis: 3 risks identified, 1 confirmed & mitigated
Review stats: 2 security, 1 logic, 3 quality issues fixed
Verification: 12/14 passed, 2 human checks
Conventions: .conventions/ updated ✅
══════════════════════════════════════════════════
```

---

### /conventions

Analyzes your codebase and creates/updates `.conventions/` directory with:
- `gold-standards/` — exemplary code snippets (20-30 lines each)
- `anti-patterns/` — what NOT to do
- `checks/` — naming rules, import patterns

These conventions are used by `/team-feature` as few-shot examples for coders. Run `/conventions` standalone to bootstrap conventions for any project.

## Key Artifacts

| Artifact | Created by | Purpose |
|----------|-----------|---------|
| `.conventions/` | Conventions task | Gold standards, anti-patterns, automated checks for future runs |
| `DECISIONS.md` | Tech Lead (MEDIUM); on COMPLEX Primary Architect during planning, then Lead | Architectural decisions, approved deviations, debate summary |
| `VERIFICATION_PLAN.md` | Lead (on COMPLEX, from the architects' checks) | Checklist of automated and manual checks |
| `VERIFICATION_REPORT.md` | Verification phase | Detailed results with pass/fail/skip per check |
| `PLAN.md` | Lead (only writer) | The task list: every task with files, criteria, blockers and status. Lead hands each task to a coder in its spawn prompt — no Claude Code task tools needed |
| `state.md` | Lead | Team state for compaction recovery |

## Team Roles

| Role | Lifetime | Purpose |
|------|----------|---------|
| **Lead** | Whole session | Orchestrates pipeline, dispatches researchers, delivers `queued` messages, monitors progress |
| **Codebase Researcher** | One-shot | Returns condensed project summary (structure, stack, patterns) |
| **Reference Researcher** | One-shot | Returns full content of best example files for each layer |
| **Tech Lead** | Permanent (MEDIUM) | Validates plan, identifies risks, rules on escalations, maintains DECISIONS.md, final cross-task check. Does not review tasks |
| **Architect** | Debate only (COMPLEX) | Debates spec in Lead-run rounds, writes a domain review brief, stands down. 3 personas: Frontend, Backend, Systems |
| **Coder** | Per task | Implements matching gold standards, self-checks, requests review directly from the reviewer |
| **Unified Reviewer** | Permanent, rotated every 3 tasks | The one per-task review: security, logic, fit with the plan, quality |
| **Second Reviewer** (optional) | One SENSITIVE task, on demand (`second-reviewer-{id}`, opt-in) | A different engine's findings with `file:line`, to the Unified Reviewer only — never a verdict, never to a coder |
| **Risk Tester** | One-shot | Verifies specific risks by reading code and running test scripts |
| **CI Verifier** | One-shot | Runs build, typecheck, lint, tests — reports PASS/FAIL/BROKEN |
| **Browser Verifier** | One-shot | Navigates pages, checks elements and interactions via Chrome |
| **Spec Verifier** | One-shot | Checks file existence, exports, API responses, config values |
| **Proxy Teammate** | Same as the role it carries | Holds a team role while delegating the thinking to an external CLI agent — see Engines below |

## Engines — Optional External CLI Agents

**Every role runs on Claude by default. With no config file, nothing here applies** — the pipeline
behaves exactly as documented above.
`second-reviewer` is the one exception: it is off unless you list it.

If you have other coding CLIs installed, you can reassign individual roles to them. Work moved out
bills against that tool's subscription instead of your Claude context and rate limit. Codex in
particular over-reports issues, which is useful for review and risk work as long as findings are
triaged before they reach a coder — the pipeline does that triage for you.

Copy `agent-teams.example.json` to `~/.claude/agent-teams.json` and change only what you want:

```json
{
  "roles": {
    "unified-reviewer": "codex",
    "risk-tester": "codex",
    "web-researcher": "grok"
  }
}
```

Supported engines: `claude` (default), `codex`, `kimi`, `grok`, `cursor`.

How each kind of role is moved:

- **One-shot roles** (researchers, risk tester, CI/spec verifiers, legacy scan) — no Claude agent is
  created; the orchestrator runs the CLI and reads its report.
- **Team roles** (reviewers, tech lead, architects, coder) — a thin Claude proxy joins the team
  under the same name and delegates to a persistent external session, so review round 2 remembers
  round 1. Other teammates see no difference.

What the proxy does and does not do:

- It passes **paths and commit ranges**, never file contents — the engine runs inside the repository
  and reads what it needs itself.
- It spends at most **three tool calls of its own per engine call**. Investigating the code before
  delegating is the failure mode this rule exists to prevent: on the first real run a reviewer proxy
  made 30 engine calls against 190 shell commands of its own and effectively did the review itself.
- In the `coder` role it **never edits a file** — the engine writes, the proxy verifies `git status`
  and makes the commit.
- It triages every finding against the cited lines before relaying it, because external engines
  over-report.

**Optional depth on SENSITIVE tasks.** When the reviewer marks a task SENSITIVE and you have
configured a `second-reviewer` on a different engine, that engine reads the same task and sends its
findings to the reviewer — never to the coder. The reviewer checks each finding against the actual
lines, drops what it cannot confirm, and folds the rest into its own single verdict, marked
`[second:<engine>]`. The gate count does not change: one reviewer, one verdict.
With no `second-reviewer` configured — the default — none of this happens.

A second opinion means a second vendor's model reads the changed files of your most sensitive
tasks — auth, payments, migrations. That is the point of it, and it is worth knowing before you
switch it on. Turn it on if that trade is one you want: it costs one extra engine run per SENSITIVE
task, billed against that engine's own subscription, and it can never block a task on its own.

Guarantees that hold regardless of configuration:

- `lead` and `browser-verifier` always run on Claude (team ownership; Chrome extension).
- Missing binary, auth failure, or a dead engine mid-run falls back to Claude automatically and
  says so in the progress feed. Set `"fallback": "fail"` if you would rather the run stop.
- External output is never trusted as-is: findings are verified against the cited lines before they
  block a task, and verifier reports must quote real command output.
- A second reviewer never issues a verdict: it hands findings to the one reviewer, which verifies
  them against the cited lines before any of them can reach a coder.
- Decisions stay on the Claude side — engines produce findings, not approvals.
- `--engines=off` on a single run ignores the config entirely.

Nothing is duplicated for safekeeping: each engine already records its own full conversation
(`~/.codex/sessions/`, `~/.kimi-code/sessions/`, `~/.grok/sessions/`, `~/.cursor/chats/`), so a run only records the
*address* — one line per engine call in `.claude/teams/<team>/ledger.jsonl`. If even that is lost,
`scripts/engine-sessions.py <project>` rebuilds the map from the engines' own stores and prints a
ready `resume` command for each session.

Full spec — role registry, config schema, CLI presets, failure handling:
`skills/team-feature/references/engines.md`.

## Structure

```
agent-teams/
├── .claude-plugin/
│   └── plugin.json
├── agents/
│   ├── architect.md
│   ├── browser-verifier.md
│   ├── ci-verifier.md
│   ├── codebase-researcher.md
│   ├── coder.md
│   ├── proxy-teammate.md
│   ├── reference-researcher.md
│   ├── risk-tester.md
│   ├── spec-verifier.md
│   ├── tech-lead.md
│   └── unified-reviewer.md
├── skills/
│   ├── conventions/
│   │   └── SKILL.md
│   ├── interviewed-team-feature/
│   │   ├── SKILL.md
│   │   └── references/
│   │       └── interview-principles.md
│   └── team-feature/
│       ├── SKILL.md
│       └── references/
│           ├── engines.md
│           ├── phase1-planning.md
│           ├── phase2-monitoring.md
│           └── phase3-verification.md
├── agent-teams.example.json
└── README.md
```

## License

MIT
