# Upgrade-relevance gate

Use this gate to keep component Markdown focused on upgrade decisions while preserving a complete forensic diff in CSV.

## Two artifacts, two jobs

- The component CSV is the complete ledger. It contains every master-inventory row owned by the report, including tests, docs, frontend/client code, generated files, refactors, formatting, and build-only changes.
- The component Markdown is the decision document. It deeply analyzes only behavior with a credible causal path to the safety, continuity, duration, rollback, or validation of this specific version upgrade.

Do not remove a row from CSV because it is trivial. Do not create a Markdown finding merely because a row is `P0`, large, in a runtime directory, or associated with an interesting commit title.

## Screen before excluding

Every CSV row must receive a lightweight relevance screen before it is excluded from detailed Markdown. Related rows may be screened together as one coherent commit or behavior cluster, but the mapping must explicitly cover every row. Inspect at least:

- the actual hunk, binary/mode/gitlink metadata, or generated-file provenance;
- the responsible commit subject and relevant commit context;
- enough caller, deployment, or test context to detect an upgrade exception.

Never exclude solely because of path, owner, `P2`, `file_type`, `review_mode`, churn, or commit title. These fields prioritize reading; they do not prove irrelevance.

## Promote to a detailed finding

Promote a change when endpoint code and supporting evidence show that it can affect at least one of these upgrade concerns:

1. rolling or mixed-version compatibility, including primary/leader movement and version-skewed outcomes;
2. daemon stop/start, activation, mount, replay, recovery, peering, backfill, scrub, rebalance, or convergence;
3. persistent data, on-disk format, encoding, schema, feature bits, migration, or data repair;
4. wire protocol, authentication, capability, or client compatibility when it can change service continuity during or after rollout;
5. availability, correctness, durability, capacity headroom, or resource pressure during the upgrade window and stabilization period;
6. configuration/default changes whose effective value can change because the new version is deployed or restarted;
7. orchestration, packaging, dependencies, or build behavior actually used to deliver the target binaries;
8. downgrade/rollback boundaries or tools required to recover from an upgrade failure;
9. observability or performance behavior that can alter a rollout stop/go decision, validation signal, maintenance-window duration, or recovery time.

The user does not need a numeric probability. A low-probability or deployment-specific effect still belongs when there is a credible causal path. Mark its applicability `conditional` and name the As-Is fact that determines applicability. Do not lower evidence confidence merely because likelihood is low: endpoint code can establish a rare behavior with high confidence. Report evidence confidence, likelihood, and deployment applicability as separate concepts. Mere speculation or a generic claim that “all runtime changes may matter” is not a causal path.

## Keep out of detailed findings

Unless an exception above is demonstrated, aggregate these as trivial or supporting changes:

- pure rename, formatting, comment, cleanup, refactor, dead-code removal, or log wording that does not change a rollout decision or failure signal;
- tests, fixtures, QA suites, and documentation that only corroborate another behavior;
- frontend, dashboard, client, or convenience-tool changes unrelated to upgrade compatibility, continuity, control, or validation;
- generated assets and dependency churn with no used delivery/runtime effect;
- build changes relevant only to an unused custom build configuration;
- a normal target-version feature or optimization with no demonstrated effect on upgrade safety, continuity, rollback, stabilization, or acceptance.

A test, doc, client, frontend, or build file can still be evidence for a promoted finding. Its file category never overrides demonstrated upgrade relevance.

## Record the final disposition

For a completed component analysis, map every CSV row to one final disposition:

- `material`: directly supports one or more detailed upgrade findings;
- `conditional`: supports a finding whose applicability depends on a named As-Is fact or explicit action;
- `support`: test, documentation, fixture, or integration evidence for a promoted finding, with no independent upgrade effect;
- `trivial`: screened and found to have no credible upgrade effect;
- `mixed`: one file contains both finding-relevant and trivial/support hunks.

Prefer the appended CSV columns defined in `csv-schema.md`: `upgrade_disposition`, `finding_id`, and `disposition_reason`. An existing suite may use an equivalent explicit mapping, but the Markdown counts must reconcile exactly to the component CSV total. Do not overwrite initial triage fields only in the component subset; base fields must remain identical to the master inventory.

## Markdown contract

Component Markdown must:

1. link the complete same-basename CSV and report its total row count;
2. state that detailed findings passed the upgrade-relevance gate;
3. group material behavior into findings rather than files;
4. include a compact `Trivial/support changes` section for all remaining row classes, with exact disposition counts that reconcile to the CSV total and a short reason they do not affect the upgrade decision;
5. avoid a row-per-file list or detailed prose for excluded rows;
6. preserve existing finding IDs when revising a report; gaps are preferable to silently renumbering cross-referenced findings.

Tests and docs cited inside findings are evidence, not separate findings. A trivial/support summary may name a few representative paths or commits only when that explains the disposition; the complete enumeration remains in CSV.

## Decision test

Before keeping a detailed finding, finish this sentence with evidence:

> If this change were absent, present, or version-skewed during the upgrade, then ___ could differ in a way that changes preparation, rollout, continuity, rollback, stabilization, or validation.

If the blank cannot be completed without generic speculation, keep the diff in CSV and classify it in the aggregate trivial/support section.
