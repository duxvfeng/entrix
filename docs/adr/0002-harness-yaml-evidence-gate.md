# ADR 0002: YAML-Driven Evidence Collection and Gate Arbitration for Claude Stop Hook

- Status: Proposed
- Date: 2026-08-16

## Context

Entrix already ships a `stop-gate` subsystem that intercepts Claude Code `Stop` requests and decides whether the agent is allowed to end a task. The current flow is:

```
Claude Stop
    ↓
entrix stop-gate
    ↓
EvidenceCollector  →  runs entrix fitness + review-trigger
    ↓
GateArbiter        →  hardcoded checks on hard_gate / score / human_review
    ↓
PASS / FAIL / BLOCKED
```

This works as a first proof of concept, but it has two structural problems:

1. **Evidence producers are implicit and hard to extend.** `EvidenceCollector` directly calls `run_fitness_report` and `evaluate_review_triggers`. There is no project-level way to say "for this repo, also collect Playwright E2E results" or "skip unit tests on doc-only branches".

2. **Gate rules are hardcoded in Python.** `GateArbiter` understands fitness-specific concepts (`hard_gate_blocked`, `score_blocked`, `human_review_required`). If a project wants a different stop policy — e.g. "require a passing type-check on frontend changes" or "block oversized diffs" — it must modify Entrix source code.

To make Entrix a genuinely reusable, cross-project quality-harness infrastructure, the following concerns must be separated and made configurable:

- **What facts/evidence should be produced** (the evidence specification)
- **How evidence is normalized** (a common schema)
- **What evidence is required for a task to stop** (the gate policy)
- **When each producer or gate applies** (conditional activation)

## Decision

Introduce a YAML-driven **Evidence + Gate** layer in Entrix. The existing `stop-gate` becomes one consumer of this layer; the layer itself is configured by a per-project `harness.yaml` file.

The layer is built around four independent concepts:

1. **Evidence Producer** — defines how to produce one piece of evidence (run a command, parse a report, read git stats, call an internal Entrix sub-system).
2. **Evidence** — a normalized, machine-readable fact produced by a producer.
3. **Evidence Store** — a filesystem-backed location where evidence is persisted.
4. **Gate Policy** — a declarative rule that inspects evidence and returns a judgment.

The Claude Stop Hook will:

1. Locate and load `harness.yaml` (or gracefully skip if absent).
2. Ask the **Evidence Engine** to collect all enabled evidence.
3. Persist evidence in the **Evidence Store**.
4. Ask the **Gate Engine** to arbitrate based on the configured `gate_policies`.
5. Return a decision to Claude.

### Scope of configurability

`harness.yaml` will be the single source of truth for:

- Which evidence producers run for a given task
- Conditions under which a producer runs (`changed_any`, `files_exist`, `branch`, `env`, etc.)
- How command output is parsed into standardized evidence
- Which gate policies must pass before the agent may stop
- Severity of each gate (`hard`, `soft`, `advisory`, `blocked`)

### Backwards compatibility

- Existing `docs/fitness/*.md` metrics remain supported.
- Existing `docs/fitness/review-triggers.yaml` remains supported.
- They will be exposed as **built-in producers** that `harness.yaml` can reference, not replaced.
- If a repository has no `harness.yaml`, the stop-gate will keep its current behavior: run fitness + review-trigger and apply the current hardcoded arbitration.

### File location

The primary configuration file is:

```text
harness.yaml
```

A hidden fallback is allowed for projects that prefer a dedicated directory:

```text
.harness/harness.yaml
```

Only one file is authoritative per repository root.

## Rationale

### Why YAML instead of Python?

The goal is cross-project reuse. A project team should be able to express "run these checks before Claude stops" without forking or patching Entrix. YAML is the right trade-off:

- It is version-controllable alongside the project source.
- It is readable by humans and LLMs.
- It is constrained enough to be validated safely.
- It avoids the security and reproducibility issues of running arbitrary code in the hook.

### Why separate Evidence from Gate?

This mirrors the legal/physical analogy used in the prompt:

- **Evidence** = the facts collected (did tests pass? how big is the diff?)
- **Gate** = the judgment based on facts (are the facts sufficient to allow stopping?)

Decoupling them makes it possible to:

- Re-run arbitration on old evidence without re-running expensive checks.
- Add new gate policies without changing producers.
- Add new producers without changing gate logic.
- Audit exactly what facts led to a block decision.

### Why standardize on a common evidence schema?

The Gate Engine must be agnostic to the underlying tool. Whether evidence comes from `pytest`, `cargo test`, `maven`, `tsc`, or an internal graph analysis, the Gate Engine sees the same fields:

- `id`
- `type`
- `status`
- `producer`
- `started_at`
- `duration_ms`
- `summary`
- `artifacts`

This keeps arbitration simple, testable, and portable.

## Consequences

### Positive

- **Cross-project reuse:** A team can drop a `harness.yaml` into a repo and get project-specific quality gates without changing Entrix.
- **Declarative stop criteria:** Product owners and tech leads can read and modify stop criteria directly.
- **Auditability:** Every stop attempt leaves a timestamped evidence bundle on disk.
- **Extensibility:** New evidence sources can be added by configuration first, code second.
- **Testability:** The Gate Engine can be unit-tested against static evidence JSON without running real commands.
- **LLM-friendly:** A standardized evidence schema gives Claude a predictable feedback format when a gate fails.

### Tradeoffs

- **Initial complexity:** The new layer requires loaders, condition evaluators, parsers, and a small expression DSL.
- **YAML limitations:** Complex conditions may eventually push users toward a more powerful DSL or plugin system.
- **Migration cost:** Existing stop-gate code (`collector.py`, `arbiter.py`) needs to be refactored to delegate to the new layer.
- **Performance:** Reading and parsing multiple producer outputs adds overhead, though evidence is only collected when Claude requests a stop.

## Proposed `harness.yaml` schema

### Top-level structure

```yaml
version: "harness/v1"

# Global activation conditions.
# Producers and gates only run when these conditions are met.
when:
  files_exist:
    - package.json
  branch:
    exclude:
      - docs/**
  changed_any:
    - frontend/**

# Evidence producers: how facts are collected.
evidence_producers:
  - id: api-test
    type: test
    name: API unit tests
    command: pytest tests/api -q --tb=short
    producer: pytest
    timeout_seconds: 120
    when:
      changed_any:
        - api/**
        - tests/api/**
    parser:
      type: junit
      path: api.xml
    artifacts:
      - type: junit
        path: api.xml

  - id: web-e2e
    type: test
    name: Web E2E tests
    command: npx playwright test
    producer: playwright
    timeout_seconds: 300
    when:
      changed_any:
        - frontend/**
    parser:
      type: junit
      path: playwright-results.xml

  - id: typecheck
    type: typecheck
    name: TypeScript type check
    command: npm run typecheck
    producer: tsc
    parser:
      type: exit_code

  - id: diff-stats
    type: diff
    name: Git diff statistics
    builtin: diff-stats
    artifacts:
      - type: json
        path: diff-stats.json

# Gate policies: what evidence is required to pass.
gate_policies:
  - name: all tests pass
    severity: hard
    rule:
      evidence_type: test
      condition: status == "pass"

  - name: api test full pass rate
    severity: hard
    rule:
      evidence_id: api-test
      condition: summary.passed / summary.total >= 1.0

  - name: minimum fitness score
    severity: hard
    rule:
      evidence_id: entrix-fitness
      condition: summary.final_score >= 80

  - name: oversized diff requires human review
    severity: blocked
    rule:
      evidence_id: diff-stats
      condition: summary.added_lines > 500
    action: require_human_review

# Optional task-level overrides.
# Different Claude tasks can opt into different producer/gate subsets.
tasks:
  - id: fast-stop
    include_producers: [typecheck, diff-stats]
    include_gates: [all tests pass, minimum fitness score]
```

### Condition DSL

The `when` block supports a small, extensible set of predicates:

```yaml
when:
  files_exist:
    - package.json
    - Cargo.toml

  changed_any:
    - src/**
  changed_all:
    - tests/**
  changed_none:
    - docs/**

  branch:
    include:
      - feature/**
    exclude:
      - docs/**

  env:
    CI: "true"

  evidence:
    - id: api-test
      status: pass
```

All predicates in a single `when` block are combined with AND semantics. Lists inside a predicate use OR semantics unless documented otherwise.

### Standard evidence schema

Every producer emits JSON in the following shape:

```json
{
  "schema_version": "evidence/v1",
  "id": "api-test",
  "type": "test",
  "name": "API unit tests",
  "status": "pass",
  "producer": "pytest",
  "task_id": "TASK-102",
  "started_at": "2026-08-14T15:40:00Z",
  "duration_ms": 8231,
  "summary": {
    "total": 18,
    "passed": 18,
    "failed": 0,
    "skipped": 0
  },
  "artifacts": [
    {
      "type": "junit",
      "path": "api.xml"
    }
  ],
  "raw": {
    "exit_code": 0,
    "command": "pytest tests/api -q --tb=short",
    "output_snippet": "test result: ok. 14 passed; 0 failed;"
  }
}
```

Field conventions:

- `id`: stable identifier, referenced by gate rules.
- `type`: `test`, `lint`, `typecheck`, `diff`, `coverage`, `security`, `custom`.
- `status`: `pass`, `fail`, `skipped`, `error`, `timeout`.
- `producer`: the actual tool or subsystem that produced the fact.
- `summary`: numeric/structured data used by gate expressions.
- `artifacts`: files that should be retained for audit.
- `raw`: optional human-readable or debugging payload.

The Gate Engine is only allowed to inspect `id`, `type`, `status`, `summary`, and `artifacts`. It must never parse tool-specific output from `raw`.

### Gate rule expression language

Gate rules use a deliberately small expression language:

```yaml
condition: status == "pass"
condition: summary.passed / summary.total >= 1.0
condition: summary.final_score >= 80
condition: summary.added_lines <= 500
condition: status in ["pass", "skipped"]
```

Supported operators:

- `==`, `!=`
- `<`, `<=`, `>`, `>=`
- `in` for membership in a list
- `/` for division, `+` `-` `*` for arithmetic
- `and`, `or`, `not` with explicit parentheses required for mixed precedence

The expression is evaluated against an evidence object. If the expression is falsy and the policy severity is `hard`, the gate fails. If severity is `blocked`, the gate blocks and may trigger an action such as `require_human_review`.

## Proposed module layout

```text
entrix/
├── harness/
│   ├── __init__.py
│   ├── config.py              # harness.yaml loader and validator
│   ├── conditions.py          # when predicate evaluation
│   ├── evidence.py            # Evidence dataclass and schema
│   ├── store.py               # EvidenceStore persistence
│   ├── engine.py              # EvidenceEngine orchestration
│   ├── producers/
│   │   ├── __init__.py
│   │   ├── base.py            # Producer protocol
│   │   ├── command.py         # Generic command producer
│   │   ├── builtin.py         # diff-stats, git, etc.
│   │   └── entrix.py          # Bridges existing fitness/review-trigger
│   └── gate/
│       ├── __init__.py
│       ├── policy.py          # GatePolicy dataclass
│       ├── arbiter.py         # GateEngine arbitration
│       └── dsl.py             # Condition expression parser
└── stop_gate/
    ├── hook.py                # kept, but delegates to harness
    ├── adapter.py             # kept
    └── ...
```

### Refactoring existing stop-gate components

| Existing file | New responsibility |
| --- | --- |
| `stop_gate/collector.py` | Thin wrapper: call `EvidenceEngine.collect(...)` and store results |
| `stop_gate/arbiter.py` | Thin wrapper: call `GateEngine.arbitrate(...)` with loaded policies |
| `stop_gate/model.py` | Replace `EvidencePack` with `EvidenceBundle` aligned to `evidence/v1` |
| `stop_gate/engine.py` | Orchestrate the new harness calls; keep error handling and state management |
| `stop_gate/hook.py` | Keep CLI contract; internally use `HarnessRunner` |

### New CLI surface

```bash
# Validate harness.yaml
entrix harness validate

# Run evidence collection for the current task
entrix harness run --task fast-stop

# Re-arbitrate a previously stored evidence bundle
entrix harness replay .harness/evidence/TASK-102/20260814154000-bundle.json

# Stop-gate entry point (kept, uses harness under the hood)
echo '{"session_id": "...", "task_id": "..."}' | entrix stop-gate
```

## Follow-up

Recommended implementation order:

1. **Schema and loader**: implement `harness/config.py` with Pydantic or dataclass validation.
2. **Evidence Store**: implement `harness/store.py` to write/read `evidence/v1` bundles.
3. **Command producer**: implement `harness/producers/command.py` with `exit_code`, `regex`, and `junit` parsers.
4. **Built-in producers**: wrap `entrix run` and `review-trigger` as `entrix-fitness` and `entrix-review-trigger` producers.
5. **Condition evaluator**: implement `harness/conditions.py` for `files_exist`, `changed_any`, `branch`, and `env`.
6. **Gate engine**: implement expression parsing in `harness/gate/dsl.py` and arbitration in `harness/gate/arbiter.py`.
7. **Stop-gate integration**: refactor `stop_gate` to delegate to the harness layer while preserving the existing hook contract.
8. **Tests and documentation**: add unit tests for parsing, condition evaluation, and arbitration; document `harness.yaml` in `docs/`.

Future extensions to consider after the initial implementation:

- Plugin-based producers (entry-point discovery) for repositories with unusual tooling.
- Remote evidence ingestion (CI systems publishing evidence to the store).
- Time-windowed condition predicates (`changed_in_last_days`).
- Gate policy inheritance / shared base policies across a monorepo.
- Evidence schema versioning strategy when `evidence/v2` becomes necessary.
