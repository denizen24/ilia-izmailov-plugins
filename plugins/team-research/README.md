# Team Research

Launch a team of AI agents for deep parallel codebase research — causal understanding, not just coverage.

## Prerequisites

> **Agent teams are experimental and disabled by default.** You need to enable them before using this plugin.

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

## Installation

```bash
/plugin marketplace add izmailovilya/ilia-izmailov-plugins
/plugin install team-research@ilia-izmailov-plugins
```

## Usage

```
/team-research <research question or topic>
```

**Examples:**
```
/team-research "How does authentication work in this project?"
/team-research "Full architecture review"
/team-research "Security + performance audit of the API layer"
/team-research "How does data flow from UI to database?"
```

## How It Works

A Research Lead agent orchestrates a 4-phase investigation pipeline that builds **causal understanding** — not just collects facts.

### Phase 1: Plan

A **Scout** agent quickly scans the codebase landscape (5 minutes max), identifying 3-7 distinct areas and suggesting investigation angles with depth tiers. The Lead then defines MECE angles with explanation-based stop criteria.

> **Why explanation-based?** "Found all entry points" is a coverage checklist. "Can explain WHY this module exists and what breaks without it" forces actual understanding. The difference matters — coverage produces lists, understanding produces insights.

### Phase 2: Investigate

**Investigators** (2-7) work in parallel, each assigned an angle. Every investigator applies the **Depth Protocol**:

| Element | What it captures |
|---------|-----------------|
| **WHAT** | Structural description with file:line references |
| **WHY** | Causal explanation — why does this exist? Why this design? |
| **FRAGILITY** | What would break if this changed? |
| **CONTEXT** | How did this appear? (git history, comments) |
| **SURPRISE** | What was unexpected vs the mental model? |

Every claim is tagged with its source:
- **Observed** — seen directly in code (with file:line)
- **Inferred** — logical conclusion from observations
- **Hypothesized** — best guess, needs verification

Investigators can communicate with each other for cross-pollination.

### Phase 2.5: Cross-Pollinate

The Lead juxtaposes surprising findings from different investigators, looking for emergent questions that no single investigator could have asked. Up to 2 targeted deepening agents may be spawned for high-value cross-cutting questions.

### Phase 3: Challenge

A **Challenger** agent stress-tests findings through 3 adversarial lenses:

1. **Evidence Quality** — are Source Tags real? Are file:line references valid?
2. **Pre-Mortem** — imagine the research was wrong in 3 months. What did we miss?
3. **Frame Gap Detection** — what perspectives are missing from the findings?

If needed, a **Critic** (failure mode analysis) or **Specialists** (domain experts for security, database, external APIs) are spawned on demand.

### Phase 4: Deliver

The Lead synthesizes all findings into a structured report with:
- Executive summary with causal understanding
- Detailed findings in Depth Protocol format
- Cross-cutting insights (the most valuable section)
- Unresolved tensions (contradictions are features, not bugs)
- Source confidence levels
- Open questions and recommendations

## Team Roles

| Role | Lifetime | Model | Purpose |
|------|----------|-------|---------|
| **Lead** | Whole session | — | Plan, orchestrate, cross-pollinate, synthesize |
| **Scout** | One-shot | Haiku | Quick landscape scan — maps terrain, doesn't investigate |
| **Investigator** | Per angle | Sonnet | Deep investigation with Depth Protocol and Source Tags |
| **Challenger** | One-shot | Sonnet | Adversarial stress-testing of all findings |
| **Critic** | On-demand | Sonnet | Failure mode analysis when Challenger flags gaps |
| **Specialist** | On-demand | Sonnet | Domain-specific deep dives (security, database, external-api) |

## Engines — Optional External CLI Agents

**Every role runs on Claude by default. With no config file, nothing here applies.**

If you have other coding CLIs installed (Codex, Kimi, Grok, Cursor), you can move the one-shot roles —
`research-scout`, `research-challenger`, `research-critic`, `research-specialist` — to another model. The point is not the other
subscription but the other model's blind spots: a challenger on a different model disagrees with the
investigators in different places, which is what Phase 3 is for.

The config is the same `~/.claude/agent-teams.json` the `agent-teams` plugin reads; each plugin takes
only its own role IDs, and this plugin's carry the `research-` prefix so a shared file cannot aim
at another plugin's `critic` by accident:

```json
{
  "roles": {
    "research-challenger": { "engine": "cursor", "model": "cursor-grok-4.6-xhigh" },
    "research-critic": "codex"
  }
}
```

- `lead` and `investigator` always run on Claude — investigators claim tasks and talk to each other,
  and that protocol does not cross a CLI boundary.
- External roles run read-only; the Lead writes the same prompt to a file, runs the CLI, and reads the
  report.
- Every `file:line` an external engine cites is checked before its claim is used; claims without a
  citation count as Hypothesized.
- A missing CLI or a failed run falls back to Claude and says so (`"fallback": "fail"` stops instead).

Details and presets: `skills/team-research/references/engines.md`.

## Team Size

```
N_optimal = min(ceil(sqrt(angles * complexity)), 7)
```

| Scope | Agents | Example |
|-------|--------|---------|
| Narrow question | 2-3 | "How does auth work?" |
| Medium exploration | 4-5 | "Understand full architecture" |
| Broad multi-domain | 5-7 | "Security + performance audit" |

Never exceed 7 in a flat team. For broader scope — run 2-3 separate `/team-research` instead.

## Key Principles

- **Depth > Coverage** — 3 well-explained findings beat 10 surface observations
- **Causal understanding** — not just WHAT exists, but WHY it exists and what would break
- **Source Tags everywhere** — every claim tagged Observed/Inferred/Hypothesized
- **Tensions are valuable** — contradictions in the report are features, not bugs
- **Structural mechanisms > cognitive instructions** — the Depth Protocol forces real computation

## Structure

```
team-research/
├── .claude-plugin/
│   └── plugin.json
├── commands/
│   └── team-research.md
├── agents/
│   ├── scout.md
│   ├── investigator.md
│   ├── research-challenger.md
│   ├── critic.md
│   └── specialist.md
└── README.md
```

## License

MIT
