---
name: entrix
description: Set up or repair a repository's single-file Entrix quality harness by discovering real quality signals, generating or updating harness.yaml, and validating that the resulting guardrails are executable.
license: MIT
---

# Entrix Skill

命令提示：`/entrix [init] [phase planning|implementation] [harness validate|run]
[run] [stop-gate] [--repo <path>] [--profile <name>]`

Leave the target repository with one working `harness.yaml`. It is the sole
source of truth for Fitness dimensions, review triggers, evidence producers,
and gate policies. Do not create or read a separate Fitness directory,
manifest, or review-trigger file.

Entrix uses "fitness" in the evolutionary architecture sense: an executable
check that measures whether a codebase still satisfies a quality or
architecture goal. The user-facing description is "quality guardrail".

## Skill Folder Contents

- `specs/README.md`: map of the available references
- `specs/harness-schema.spec.md`: single-file configuration schema
- `specs/dimension-boundaries.spec.md`: how to add or consolidate dimensions
- `specs/dimension-*.spec.md`: per-dimension guidance
- `examples/`: copyable `harness.yaml` snippets
- `../../tests/fixtures/skill_regression/`: bundled repository profiles used by
  the skill regression harness

## Read Order

For any bootstrap or repair task, read in this order:

1. target repository `AGENTS.md` and `CLAUDE.md` if present
2. target repository manifests and task runners: `package.json`,
   `pyproject.toml`, `Cargo.toml`, `justfile`, `Makefile`
3. target repository `.github/workflows/**`
4. existing target `harness.yaml` if present
5. this skill's `specs/README.md`
6. `specs/harness-schema.spec.md` and only the required dimension specs
7. matching `examples/*.md` when entry-document or CI-boundary behavior is
   ambiguous

## Core Rules

- Use real repository signals only. Do not invent commands.
- Keep one `harness.yaml` at the repository root. Do not create sidecar quality
  configuration files.
- Prefer repository-root-safe wrappers such as `just`, `make`, `npm run`, or
  `cargo --manifest-path ...`.
- Keep weighted dimensions at a total of exactly `100`; use `weight: 0` for
  advisory-only dimensions.
- Keep a default local `entrix run` green. Model authoritative checks that need
  CI setup with `execution_scope: ci` rather than a local fast hard gate.
- When the Claude Stop Gate is installed, it is the sole authority for the
  complete Harness run. Do not have Claude run `entrix run` or
  `entrix harness run` immediately before stopping; that duplicates expensive
  checks and can overlap JVM/Gradle processes.
- Treat the task phase as part of the Stop Gate lifecycle. At the beginning of
  planning or brainstorming, run `entrix phase planning --repo .`. Only after
  the user explicitly approves implementation, run `entrix phase implementation
  --repo .`.
- Add a security or release metric only when the repository has a real command
  or CI signal for it.
- Keep every existing agent entry document discoverable: point `AGENTS.md` and
  `CLAUDE.md` to `harness.yaml` when they exist. If neither exists, create only
  a minimal `AGENTS.md`.

## Harness Schema

Use the standard single-file shape:

```yaml
version: "harness/v1"
fitness:
  dimensions:
    - dimension: code_quality
      weight: 50
      threshold: {pass: 100, warn: 90}
      metrics:
        - name: lint
          command: npm run lint 2>&1
          hard_gate: true
          tier: fast
          description: Lint must pass.
    - dimension: testability
      weight: 50
      threshold: {pass: 100, warn: 90}
      metrics:
        - name: unit_tests
          command: npm run test:run 2>&1
          hard_gate: true
          tier: normal
          execution_scope: ci
          description: The authoritative suite runs in CI.
review_triggers:
  rules:
    - name: risky_core_change
      type: changed_paths
      paths: [src/core/**]
      severity: high
      action: require_human_review
evidence_producers:
  - id: fitness
    type: fitness
    name: Entrix Fitness
    builtin: entrix-fitness
gate_policies:
  - name: Fitness must pass
    severity: hard
    rule:
      evidence_id: fitness
      condition: status == "pass"
```

Dimension identifiers use `snake_case`. A dimension contains its complete
`metrics` list; names must be unique. Common metric fields are `name`,
`command`, `pattern`, `hard_gate`, `tier`, and `description`. Use advanced
fields such as `execution_scope`, `timeout_seconds`, `gate`, `evidence_type`,
`confidence`, `stability`, `kind`, `analysis`, `owner`, `run_when_changed`, and
`waiver` only when the repository justifies them.

## Workflow

### 1. Inspect the repository

If this invocation is still in planning or brainstorming, mark that phase
before reading or changing configuration:

```bash
entrix phase planning --repo .
```

Identify real signals from package scripts, task runners, CI workflows,
checked-in helper scripts, and an existing `harness.yaml`. Prefer local
repository commands first, then root-safe commands copied from CI, then direct
tool invocations only when their working directory is unambiguous.

### 2. Design dimensions

Use stable concern names such as `code_quality`, `testability`, `security`,
`release_readiness`, `api_contract`, `design_system`, `ui_consistency`,
`observability`, and `performance`. Add related checks as metrics inside the
same dimension; create a new dimension only for a genuinely independent quality
surface.

### 3. Create or repair `harness.yaml`

For a new repository, prefer `entrix init --repo .`. `init` defaults to
`--profile auto` and selects a language template from repository markers:

- `pyproject.toml`, `pytest.ini`, `requirements.txt`, `setup.py`, or `setup.cfg` -> `python`
- `package.json` or `tsconfig.json` -> `node-typescript`
- `pom.xml` -> `java-maven`
- `build.gradle`, `build.gradle.kts`, or Gradle wrappers -> `java-gradle`
- `go.mod` -> `go`
- `Cargo.toml` -> `rust`

An empty or otherwise unknown repository uses `generic`. If multiple profiles
are detected, stop and ask the user to choose one explicitly, for example
`entrix init --repo . --profile java-maven`. The supported explicit profiles are
`generic`, `python`, `node-typescript`, `java-maven`, `java-gradle`, `go`, and
`rust`. Keep the generated Fitness, review-trigger, producer, and policy
sections together in the same file; adjust a command only when inspection
shows that the repository uses a different real task runner.

Java templates intentionally constrain process fan-out: Maven uses `-T1` and
tests use `-DforkCount=1 -DreuseForks=true`; Gradle uses
`--no-daemon --max-workers=1`. These limit the build tool's own workers in
addition to Entrix's outer producer limit.

If an entry document already exists, add a short note that rules live in
`harness.yaml`. Do not duplicate the full configuration into entry documents.

### 4. Ask before validation

`entrix init` creates `.mcp.json` and `harness.yaml` plus a one-shot runtime
phase marker. After creating or repairing configuration, report the files
changed and ask the user:

```text
Configuration is ready. Do you want to run configuration validation or local checks now?
```

Do not run `entrix harness validate`, `entrix run --dry-run`, `entrix run
--tier fast`, `entrix harness run`, or Stop Gate until the user explicitly
answers yes. A request to initialize, create, or repair configuration is not
approval to run checks.

When the user approves implementation work, switch the phase before editing
source or running implementation checks:

```bash
entrix phase implementation --repo .
```

`entrix init` writes a one-shot initialization phase automatically. The Stop
Hook consumes it at the end of that initialization turn, so configuration
creation does not trigger a full Harness run before the user answers the
confirmation question.

When validation is explicitly approved, run the best available Entrix
invocation in this order: `entrix`, `uvx --from entrix entrix`, then `python3
-m entrix`.

```bash
entrix harness validate harness.yaml
entrix run --dry-run
entrix run --tier fast
```

Repair invalid schema, duplicate names, weights, paths, and non-local commands
before stopping. If a command is CI-only, move it to `execution_scope: ci` and
keep a cheap local smoke check in the default path.

For an explicit, human-requested full diagnostic run, wait for it to finish
before requesting Stop. JVM/Gradle metrics must set `timeout_seconds` and use
`--no-daemon --max-workers=1` unless the repository has an approved resource
budget for more workers.

## Quality Bar

The skill is complete only when:

- `harness.yaml` exists; when validation is explicitly requested, it validates
- Fitness dimensions with positive weights total `100`
- each metric maps to a real repository signal
- review triggers, producers, and gate policies are inline
- existing agent entry documents point to `harness.yaml`
- the explicit local `entrix run`, when requested, is green or a concrete
  repository blocker is reported
- `entrix run --dry-run` and available fast-tier checks run only after explicit
  user approval

## Avoid

- creating multiple configuration files for one repository
- inventing commands or security tools
- leaving a CI-provisioned suite as a default local fast hard gate
- placing a non-runnable optional tool in default local execution
- running validation or checks merely because `entrix init` succeeded
- stopping after producing configuration that only looks plausible
