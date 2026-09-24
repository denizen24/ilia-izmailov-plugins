# Phase 3: Completion & Verification — Detailed Protocol

> Print points are marked 📢 — short feed lines in the user's language, product terms. The final reports (verification report, summary, human checks) already exist; the feed makes the *process* between them visible.

When all coding tasks are completed:

Coders still work in this phase (conventions, fixes, legacy cleanup) and still message the reviewer
directly: keep delivering `QUEUED` copies and run the idle check before going idle
(`team-runtime.md` §3).

## 1. Conventions Update

📢 One line entering Phase 3: `🏁 Code is written. Wrapping up: updating project conventions, then running all checks.`

Spawn a coder for the conventions task (the last task in PLAN.md) if it is still TODO — Phase 2 never spawns it.

The coder receives the task description which tells them exactly what to create/update (signal sources are listed there). If `.conventions/` didn't exist before, bootstrap it with the key patterns researchers identified.

The conventions task is tracked in PLAN.md like any other task. It goes through the same review flow (coder self-checks → unified-reviewer approves → commit).

After the conventions task is done, report what was created/updated in the summary.

## 2. Cross-Task Consistency Check

**MEDIUM:** SendMessage to tech-lead: `CROSS-TASK CHECK: git diff {base-commit}..HEAD` — it replies with a list of inconsistencies (see tech-lead.md).

**SIMPLE and COMPLEX:** no long-lived architectural agent exists by now — on COMPLEX the architects
handed over review briefs and stood down after the debate. Spawn a **one-shot** checker instead. It
needs to read code, which Lead deliberately does not do, but it needs to read only the final diff —
a narrow context that dies with the agent:

```
Task(
  subagent_type="Explore",
  description="Cross-task consistency check",
  prompt="Review the combined diff of this feature for cross-task inconsistencies — the problems
that appear only when separate tasks are put together, and that a per-task reviewer could not see.

Diff: `git diff {base-commit}..HEAD`
Feature: {1-2 line description}
Definition of Done: {DoD}
Architect review briefs (COMPLEX): {paths to reports/review-brief-*.md — read them}

Look for: the same concept named or modelled two different ways across tasks; duplicated logic that
two coders wrote independently; contradictory assumptions at the seams between tasks; a shared type,
config or schema changed by one task in a way another task did not account for.

Do NOT report per-task issues — the reviewer already covered those. Only report what needs two or more
tasks side by side to notice.

Return a short list: file:line, what is inconsistent, which tasks disagree. Empty list if clean."
)
```

Findings become fix tasks: add them to PLAN.md, spawn a coder per task, and after their DONE re-run
this check once. What is still inconsistent after that goes to the report as an open item.

**Never skip this step because the run looks clean.** It is the only check that sees two tasks at
once, and parallel tasks break each other in ways no per-task reviewer can see. Measured on
2026-09-17: two tasks moved the same shared component in opposite directions, one of them quietly
dropped a notice the user relies on before the call connects — and it passed three reviewers, both
page test suites, the build, and a 194-measurement browser run. The cross-task checker found it in
one pass. A green board is exactly when this step pays for itself.

## 3. Completion Gate

Lead verifies before declaring done:
```
Glob(".conventions/**/*")
```
- If .conventions/ does not exist or was not modified during this session → **STOP. Feature is NOT complete.**
- Go back to step 1 and run the conventions task. If it was never created → add it to PLAN.md now and spawn a coder for it.

## 4. Prepare VERIFICATION_PLAN.md

```
Read(".claude/teams/{team-name}/VERIFICATION_PLAN.md")
— Update file/export paths with actual paths from completed tasks
— Update API endpoints with actual URLs
— Update browser check URLs with actual dev server URLs
— Add any new checks discovered during implementation
```

## 5. Integrated Verification (team is still alive — coders can fix failures)

### 5a. Parse the Verification Plan

Read VERIFICATION_PLAN.md and parse sections by `##` headers:

| Section | Verifier agent |
|---------|---------------|
| `## Build & Types` | ci-verifier |
| `## Tests` | ci-verifier |
| `## Browser Checks` | browser-verifier |
| `## Spec Checks` | spec-verifier |
| `## Human Checks` | reported as-is (no agent) |

- Only process `- [ ]` items (unchecked). Skip `- [x]` items.
- Warn on unknown `##` sections — items will be skipped.

### 5b. Pre-flight Readiness Check

If Browser Checks or API-based Spec Checks exist:
```
Bash: curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 {base_url}
```
- If ECONNREFUSED or timeout → move browser + API checks to Human Checks with reason: "Dev server not running at {url}"
- Do NOT try to auto-start the server
- Continue with remaining checks (build, types, file-based spec checks)

### 5c. Spawn Verifier Agents in Parallel

📢 Before spawning: `🧪 Verification: {N} automated checks (build, tests, browser, spec).`

Only spawn agents for sections with items. Launch ALL in parallel.

**Engine check** (Step 0b table): `ci-verifier` and `spec-verifier` on an external engine are not spawned as Claude agents — write the same prompt to a file and launch it through `scripts/run-engine.sh` with `--report verify-{role}.md`, waiting on its `.done` marker (`engines.md`, "Launching an Engine") (read-only sandbox for `spec-verifier`; `ci-verifier` needs the **write** sandbox because builds and tests write artifacts). `browser-verifier` is always Claude. A verifier report is only usable if it quotes actual command output — an external engine claiming "tests pass" without the output counts as BROKEN, not PASS.

```
Task(subagent_type="agent-teams:ci-verifier",
  prompt="Run these CI checks:
{all items from Build & Types and Tests sections}
Report PASS/FAIL/BROKEN per check with evidence.")

Task(subagent_type="agent-teams:browser-verifier",
  prompt="Verify these browser checks:
{all items from Browser Checks section}
Report per check with evidence.")

Task(subagent_type="agent-teams:spec-verifier",
  prompt="Verify these spec checks:
{all items from Spec Checks section}
Report per check with evidence.")
```

**Status taxonomy** (all verifiers use this unified 7-status system):

| Status | Meaning | Blocks? |
|--------|---------|---------|
| PASS | Verified successfully | No |
| FAIL | Code problem found | Yes — fix loop |
| SKIP(capability) | System can't verify (Chrome missing, auth needed) | Yes — human |
| SKIP(n/a) | Doesn't apply to this feature | No |
| UNCLEAR | Ambiguous result | Yes — human |
| DEGRADED | Agent timed out or crashed | Yes — human |
| BROKEN | Environment unreliable (server down, deps missing) | Yes — human |

### 5d. Collect Results + Integrity Audit

- If an agent **times out or crashes** → mark all its items as DEGRADED
- Route each status per the taxonomy table above (Blocks? column): blocking non-FAIL statuses go to Human Checks with the verifier's reason; BROKEN items are collected separately (environment issue, not code issue).

**Verification Manifest**: for each verifier, compare items sent vs items reported. Mark any missing items DEGRADED and note the discrepancy in the report.

### 5e. Fix-Verify Loop

📢 When results are collected (5d), print the outcome in product terms — failures named as user-visible problems, not check IDs:

```
🧪 Results: 12 of 14 ✅. Two problems: the save button does nothing on an empty form; the migration test fails.
```

(If everything passed: `🧪 All {N} checks passed ✅.`)

If there are **FAIL** items:
1. Add targeted fix tasks to PLAN.md based on failure evidence and spawn a coder per task
2. Wait for coders to fix and commit
3. Re-run ONLY the failed checks (spawn fresh verifiers for failed items only)
4. **Hard cap: 3 iterations max.** Tag each iteration: "Verification run {N}/3: fixing {list}"
   📢 Per iteration: `🔨 Fix iteration {N}/3: {what's being fixed, product terms}` and, after re-verify: `🧪 Re-check: {result}`
5. After 3 attempts → mark remaining FAILs as unresolved, add to Human Checks with full retry trace

If there are **BROKEN** items: do NOT retry — these are environment issues. Add to Human Checks with action "fix environment".

### 5f. Compile Progressive Verification Report

```
══════════════════════════════════════════════════
VERIFICATION REPORT
══════════════════════════════════════════════════

## Level 0: One-line status
{STATUS} — {N}/{total} passed, {N} failed, {N} human checks, {N} broken
{STATUS: ALL_PASS | PASS_WITH_CAVEATS | HAS_FAILURES | ENVIRONMENT_BROKEN}

## Level 1: Summary by category

| Category | Total | Pass | Fail | Skip | Unclear | Broken |
|----------|-------|------|------|------|---------|--------|
| Build & Types | {n} | ... | ... | ... | ... | ... |
| Tests | {n} | ... | ... | ... | ... | ... |
| Browser Checks | {n} | ... | ... | ... | ... | ... |
| Spec Checks | {n} | ... | ... | ... | ... | ... |

## Level 2: Failure details

### Failed Checks (unresolved after {N} fix attempts)
#### {check description}
What was checked: {evidence}
Expected: {X}
Actual: {Y}
Fix attempts: {trace}

### Broken (environment issues)
#### {check description}
Problem: {what went wrong}
Action: {what to fix}

## Level 3: Integrity & scope

### Verification Manifest
{per verifier: items sent vs reported, discrepancies}

### NOT verified (scope disclosure)
- {e.g., cross-task interactions, performance under load, accessibility — add feature-specific uncovered areas}

## Human Checks
{items from Human Checks section + SKIP + UNCLEAR + DEGRADED + unresolved FAIL}
- [ ] {what to check}
  Context: {why human verification needed}
  → {step-by-step instructions}

══════════════════════════════════════════════════
```

Save report to `.claude/teams/{team-name}/VERIFICATION_REPORT.md`

## 6. Legacy Cleanup (team is still alive — coders can remove legacy)

**This step is MANDATORY.** Do not skip it even if `LEGACY_REPORT.md` looks empty — always run the scan for safety. The user must have a chance to decide what happens to legacy code before the team is shut down.

### 6a. Read coder-reported legacy

```
Read(".claude/teams/{team-name}/LEGACY_REPORT.md")
```

Coders appended entries here during Step 4.5 of their workflow. Parse all `## [task #N] ...` entries into a list.

### 6b. Run a safety scan for legacy coders missed

Dispatch a single Explore subagent to catch what coders might have missed. Give it the list of files touched this session (from commits or state.md). This is the `legacy-scanner` role — if it is assigned to an external engine (Step 0b table), launch it read-only through `scripts/run-engine.sh` with this same prompt instead of spawning Explore:

```
Task(
  subagent_type="Explore",
  description="Scan for legacy leftovers",
  prompt="Scan the following files touched during this session for legacy code left behind after refactoring:
{list of files touched this session}

Check for legacy leftovers (per CLAUDE.md legacy rules): unused imports/variables/functions/files
(grep for references to each exported symbol), duplicate old+new implementations side-by-side,
dead code paths behind flags, deprecation comments (`// deprecated`, `// TODO remove`),
hardcoded fallbacks to old logic, migration scripts/shims no longer needed.

For each finding, output:
- Where: file:line
- What: one sentence
- Evidence: grep result showing usage count (e.g., '0 references', '2 references — one in tests')
- Suggested action: delete / keep / investigate

Thoroughness: medium. Under 3 minutes. Report findings concisely — max 10 items, prioritize highest-confidence dead code."
)
```

Append the scan findings to `LEGACY_REPORT.md` under a separate section `## From Phase 3 safety scan`.

**A scan item is a hypothesis, not an order.** The scanner reads text; it does not run the product.
When the user approves a cleanup, the coder that carries it out is explicitly allowed — and expected —
to verify the claim first and to come back with `ESCALATION` instead of doing it, if the item turns
out to be wrong. Put that sentence in the cleanup task. Real case, 2026-09-17: a scan called two CSS
classes on a `<video>` redundant next to `absolute inset-0`; removing them changed nothing in the
tests or the build, and enlarged the cropped video in a real browser — a replaced element with
`width/height: auto` takes its intrinsic size. The coder measured it in Chromium, refused the item
and wrote the measurement into `.conventions/` so nobody "cleans it up" again. Items about layout,
timing, or anything a headless test environment cannot render deserve that treatment by default.

### 6c. Decide with the user

**If LEGACY_REPORT.md is empty after the scan** (no coder reports + no scan findings):
Print to chat: `Legacy cleanup: nothing to review — no legacy leftovers detected.` Skip to Step 7 (Summary Report).

**If items exist**, print the full list in chat (human-readable, numbered):

```
══════════════════════════════════════════════════
LEGACY DETECTED — what to do with each item?
══════════════════════════════════════════════════

Found {N} legacy item(s) left after implementation:

1. **{title}** ({source: coder-N / scan})
   Where: `{file}:{line}`
   What: {description}
   Still used? {yes/no/unclear — with evidence}
   Why it's here: {reason from coder or "detected by scan"}

2. **{title}** ...
...
══════════════════════════════════════════════════
```

Then ask the user with **one AskUserQuestion call, one question per item** (max 5 questions per call — if more items, batch into multiple calls). Question: "{short title} at {file}:{line}. What to do?" with three single-select options:
- **Delete** — coder removes it now (creates a cleanup task, goes through review)
- **Keep** — leave as is; it's needed or safer to keep
- **Later** — save to `.legacy-todo.md` at repo root for future cleanup

### 6d. Apply user decisions

For each item based on the user's choice:

**"Delete" items** → add a single cleanup task to PLAN.md bundling all delete items:
```
## Task {N}: Cleanup legacy after feature completion
Status: TODO
Blocked by: none

Description: Remove the following legacy items approved by user:

{list of items to delete with file:line and description}

Do NOT remove anything not on this list. Run self-checks + request review as usual. Commit with: 'chore: cleanup legacy after {feature-name}'
```

Spawn a fresh coder for it (coders stand down after one task). Wait for DONE. The reviewer must approve.

**"Later" items** → append to `.legacy-todo.md` at repo root (create the file if missing):
```
Edit / Write (.legacy-todo.md):

## {YYYY-MM-DD} — deferred from feature "{feature name}"

- [ ] `{file}:{line}` — {description} (still used? {yes/no/unclear})
- [ ] `{file}:{line}` — ...
```

**"Keep" items** → no action, just log in summary report.

### 6e. Re-run verification if Delete tasks were created

If cleanup tasks were run, re-run the relevant checks from VERIFICATION_PLAN.md (build, types, tests) to make sure nothing broke. This reuses Step 5e fix-verify loop machinery. Max 2 iterations for cleanup fixes.

## 7. Summary Report

Print the summary (includes verification):
```
══════════════════════════════════════════════════
FEATURE COMPLETE — VERIFIED
══════════════════════════════════════════════════

Tasks completed: X/Y
Complexity: SIMPLE / MEDIUM / COMPLEX
Commits: [list of commit SHAs with messages]

Risk analysis (pre-implementation):
  Risks identified: N | Confirmed & mitigated: N | Dismissed: N

Review stats (post-implementation):
  Security: N found & fixed | Logic: N | Quality: N   (by finding category in the review reports)
  Convention violations: N | Escalations: N
  Second opinion on {engine}: N task(s) | Findings offered: N | Confirmed: N

Acceptance (parent verify per task):
  Tasks accepted by the checker: N/{coding tasks} | reopened once: N | unresolved: N
  Deviation journals from external engines: N file(s), N line(s)

Verification:
  Automated checks: {N}/{total} passed
  Fix-verify iterations: {N}/3
  Human checks remaining: {N}

Legacy cleanup:
  Items found: {N} (coder reports: {X} + scan: {Y})
  Deleted now: {N} | Kept: {N} | Saved to .legacy-todo.md: {N}

Conventions:
  .conventions/ updated: Y/N
  Files: [list]

Definition of Done: {static criteria met / partial}
Runtime verification: {N/A if no human checks | PENDING — see Human Checks below}
══════════════════════════════════════════════════
```

**The `Second opinion` line prints only when a second opinion actually ran** — no `second-reviewer`
in the Step 0b table, or no task marked SENSITIVE, and the line is omitted entirely. Not `0`, not
"none": on a stock run this block is byte-identical to what it was before the feature existed.

Take the numbers off disk — Lead never read the review reports, and a compaction may have taken the
rest of the run with it:

- **Tasks covered:** `ls .claude/teams/{team-name}/reports/ | grep -oE '^review-task[^-]+-second-r' | sort -u | wc -l`
  — distinct tasks, since a relaunch leaves a `-{label}` copy beside the first file rather than
  overwriting it
- **Findings confirmed:** `grep -h '\[second:' .claude/teams/{team-name}/reports/review-task*-unified-r*.md | wc -l`
- **Findings offered:** confirmed plus the lines under the `### Not confirmed (second opinion)`
  headings in the same files. Those lines carry no severity token on purpose — they count here and
  nowhere else, never in the Security / Logic / Quality counts above.
- **Engine:** the `second-reviewer` row of the Step 0b table.
- **Acceptance:** `ls .claude/teams/{team-name}/reports/accept-task*.md | wc -l` against the coding
  tasks in PLAN.md; `grep -l '^ACCEPT:.*FAIL' …/reports/accept-task*.md` for the reopened ones;
  a task DONE without a report is named as such (docs-only tasks are expected there).
- **Deviations:** `ls …/reports/deviations-*.md 2>/dev/null | wc -l` and `cat … | wc -l`.

## 8. Shutdown Team

There is no team to delete (`team-runtime.md` §4) — the team is implicit and ends with the session.

- Permanent teammates — all levels: unified-reviewer; MEDIUM: also tech-lead; COMPLEX: the
  architects already stood down in Phase 1.
- Those whose turn has finished need nothing. Any still running: `SendMessage` with
  `{"type": "shutdown_request"}` or `TaskStop`, and confirm it stopped.
- Mark every roster entry `STOOD_DOWN` in state.md.
- Leave `.claude/teams/{team-name}/` in place: it is the record of the run.

## 9. Present Human Checks to User

**This step is mandatory whenever any Human Checks, BROKEN, SKIP, UNCLEAR, or unresolved FAIL items exist.** The user must see the full actionable checklist in this same turn — never stop at "Human Checks below" without showing them.

### Step 9a — Print the detailed checklist IN CHAT (not inside AskUserQuestion)

Render as a numbered, step-by-step checklist so the user can follow it without asking a follow-up. Group by stage if multiple phases are involved (deploy → observe → verify).

Template:

```
══════════════════════════════════════════════════
HUMAN CHECKS — what you need to do
══════════════════════════════════════════════════

{One-line summary: "Team is done statically. {N} things still need human eyes."}

{If changes touch deploy/runtime, structure as stages:}

### Stage 1 — Deploy ({estimated time})
Command: `{exact command}`
What happens: {one sentence — what the deploy does}
How to know it's done: {specific signal — "GitHub Actions green", "service restarts"}

### Stage 2 — Observe on {env} ({time window})
Watch for specific signals:
- [ ] {Specific log line / metric / behavior to look for} — means {what it confirms}
- [ ] {Absence of specific error pattern} — e.g., "no `{error text}` in last {N} minutes"
- [ ] {Specific endpoint / UI flow to hit manually}

### Stage 3 — Sanity checks ({time window})
- [ ] {User flow 1 to try end-to-end}
- [ ] {User flow 2}
- [ ] {Rollback command ready if needed}: `{command}`

{If simpler — just list items directly:}

- [ ] {Check 1 with concrete instructions}
- [ ] {Check 2 with concrete instructions}

### What "good" looks like
{2-3 bullets describing the positive signals the user should see}

### If something looks wrong
- Rollback: `{command}`
- Logs: `{command or dashboard URL}`
- Ping me in chat with the error — I can investigate

══════════════════════════════════════════════════
```

**Populating the checklist** — pull items from:
- VERIFICATION_PLAN.md `## Human Checks` section
- BROKEN items (environment issues)
- SKIP(capability) + UNCLEAR + DEGRADED items
- Unresolved FAIL items (after 3 fix attempts)

If the VERIFICATION_PLAN's Human Checks are vague ("deploy and watch logs"), **expand them here into concrete stages** based on what the feature actually touches. Look at the commits — if they touch deploy config, billing, pg-boss, auth middleware, database migrations, etc., generate stage-specific checks (exact log lines, error patterns, user flows). Do not output generic "watch logs" without specifics.

### Step 9b — Follow up with AskUserQuestion

After printing the checklist, ask:

```
AskUserQuestion(
  questions=[{
    "question": "Ready to run the checklist? I can help with any stage.",
    "header": "Human checks",
    "options": [
      {"label": "Start Stage 1 now", "description": "Run the deploy command"},
      {"label": "Walk me through it", "description": "Go stage by stage with me"},
      {"label": "I'll do it myself later", "description": "Park the checklist, report back when done"}
    ],
    "multiSelect": false
  }]
)
```

### When no human checks are needed

If ALL checks passed and there are zero human-check items — skip Step 9 entirely and print: `ALL CHECKS PASSED — feature fully verified, no manual checks needed.`
