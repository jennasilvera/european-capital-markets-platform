# Contributing and Review Standard

## Purpose

This repository is maintained as professional analytical infrastructure.

Changes should improve one or more of:

- accuracy;
- auditability;
- reproducibility;
- maintainability;
- analytical usefulness;
- source traceability;
- control quality.

Complexity is not a goal.

## Development Standard

Before a change is considered ready for review, it should satisfy all
applicable checks for:

1. mechanical correctness;
2. analytical consistency;
3. source traceability;
4. reproducibility;
5. appropriate documentation;
6. controlled handling of assumptions;
7. appropriate publication treatment.

## Local Quality Gate

Before commit, run:

    uv lock --check
    uv run ruff check .
    uv run pytest
    git diff --check

All applicable checks must pass.

## Code Changes

Code should:

- prefer explicit behavior over hidden side effects;
- keep domain logic separate from presentation logic;
- avoid unnecessary dependencies;
- preserve deterministic behavior where possible;
- raise clear errors for invalid analytical states;
- include tests for material business logic.

## Data Changes

Do not commit externally sourced data until its publication treatment has been
explicitly established.

Never commit:

- credentials;
- API keys;
- private tokens;
- confidential client information;
- restricted market data;
- temporary Excel lock files;
- local databases;
- generated intermediate files without a defined purpose.

Data changes should preserve provenance and should not overwrite conflicting
observations without an audit trail.

## Analytical Changes

A material analytical-methodology change should document:

1. what changed;
2. why it changed;
3. which calculations or outputs are affected;
4. whether historical outputs require regeneration;
5. whether assumptions changed;
6. whether release comparability is affected.

## Assumptions

Material assumptions must be explicit.

An analyst assumption must not be presented as:

- a disclosed fact;
- a verified market observation;
- a source-derived value.

Where an assumption affects a recommendation materially, its sensitivity should
be considered.

## Testing Standard

Tests should focus on meaningful failure modes.

Examples include:

- invalid taxonomy combinations;
- inconsistent transaction dates;
- impossible financing terms;
- missing required evidence;
- duplicate identifiers;
- incorrect calculated metrics;
- invalid release states;
- prohibited silent overwrites.

Tests should verify business rules rather than merely increase test count.

## Review Standard

Review should consider three layers.

### Mechanical Review

Check:

- tests;
- formatting and linting;
- schema validity;
- calculation integrity;
- broken references;
- data exceptions.

### Analytical Review

Check:

- transaction classification;
- market interpretation;
- comparable selection;
- methodology;
- assumptions;
- financing logic;
- scenario consistency.

### Senior-Message Review

Check:

- what the analysis is saying;
- why it matters;
- whether evidence supports the conclusion;
- whether the recommendation follows from the analysis;
- what would change the conclusion.

## Release Standard

A release should not proceed with unresolved blocker-level exceptions.

Released outputs should be:

- identifiable;
- dated;
- reproducible;
- traceable to controlled inputs;
- immutable after release.

A correction or update should create a new release rather than silently replace
an existing released output.

## Commit Discipline

Commits should be logically coherent and reviewable.

Avoid combining unrelated changes.

Commit messages should describe the substantive change rather than the act of
editing files.

Examples:

    Establish repository governance and architecture
    Add transaction taxonomy validation
    Implement source-evidence lineage model
    Add ECM performance calculation controls

## Repository Hygiene

Do not add directories, abstractions, automation, or frameworks solely to make
the repository appear more sophisticated.

Every maintained component should have a clear analytical, operational, or
control purpose.
