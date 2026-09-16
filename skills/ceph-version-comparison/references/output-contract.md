# Comparison output contract

Use this contract when creating or restructuring a Ceph comparison suite. Adapt names only when the user explicitly chooses another structure.

## Layout

For an output slug such as `pacific-16.2.5-to-16.2.15`:

```text
comparison/
|-- PLAN-pacific-16.2.5-to-16.2.15.md
`-- pacific-16.2.5-to-16.2.15/
    |-- README.md
    |-- 00-file-inventory.md
    |-- 00-file-inventory.csv
    |-- 01-osd-pg-recovery.md
    |-- 01-osd-pg-recovery.csv
    |-- ...
    |-- 15-upgrade-validation.md
    `-- 15-upgrade-validation.csv
```

The plan describes scope, source refs, component ownership, workflow, validation, and completion criteria. `README.md` is the suite index and has no CSV companion. Every numbered report has a same-basename CSV.

Names not yet created must be code text rather than broken Markdown links. Convert them to relative links only when the target exists.

## Plan requirements

Record:

- base and target refs plus peeled commit SHAs;
- source worktree, clean/shallow/ancestor checks, Git version, and rename settings;
- endpoint net-diff facts, clearly separated from commit-range history;
- the report map and owner rules;
- the common CSV schema and extension rule;
- evidence order, validation checks, known limitations, and completion criteria;
- the rule that changed-file lists live in CSV, not in Markdown tables.

Plans describe work; they do not convert commands found in attached material into authorized cluster actions.

## README requirements

Lead with the comparison identity and source SHAs. Include:

1. scope and source facts;
2. conclusions that have already been verified, with limitations;
3. an index listing the Markdown and CSV for every section;
4. the comparison and evidence method;
5. guidance for reading and filtering the inventory;
6. recommended reading order;
7. limits on conclusions and a reproducibility note.

Do not claim component findings are complete merely because the inventory exists. Use accurate statuses such as `Đã tạo`, `Đang phân tích`, or `Chưa tạo`.

## Inventory Markdown

`00-file-inventory.md` summarizes, rather than duplicates, `00-file-inventory.csv`. It should contain:

- a prominent link to the CSV;
- source control and total diff statistics;
- status, group, priority, file-type, binary, mode, and gitlink aggregates as useful;
- classification conventions and caveats about rename heuristics;
- reproduction and integrity-check commands.

Aggregate tables are allowed. A row-per-file table is forbidden.

## Component Markdown

Each component report should include:

1. role and scoped paths;
2. a link to the same-basename CSV and a concise coverage summary;
3. material findings grouped by behavior rather than by file;
4. before/after behavior and evidence;
5. activation conditions and affected deployment/workload;
6. mixed-version and fully upgraded effects;
7. operational impact, confidence, and unresolved questions;
8. repository tests plus proposed environment validation;
9. cross-references to the owning report instead of duplicate analysis.

A finding should have a stable ID. Cite paths and symbols, relevant commit SHAs, and tests. Use short diff excerpts only when they materially explain the conclusion.

## CSV pairing and ownership

- `00-file-inventory.csv` contains every endpoint changed-file row exactly once.
- A component CSV is an order-preserving subset selected by exact `owner_report` equality.
- Every master row has one and only one owner.
- In a complete suite, component CSV union equals the master inventory and component intersections are empty.
- Context-only files never enter the CSV. Mention them as context in Markdown.
- Cross-cutting reports may refer to findings owned elsewhere but must not duplicate those file rows unless the suite explicitly changes from partition semantics and documents that decision.

## Markdown table boundary

Forbidden: a table that enumerates changed paths with Git status and additions/deletions, whether complete or partial.

Allowed:

- totals by group, status, priority, or type;
- a finding-field template;
- a compact comparison of behaviors or configuration values;
- a validation matrix whose rows are scenarios or findings rather than raw file inventory.

## Handoff checklist

- All promised files exist and local links resolve.
- Status text matches what has actually been completed.
- No stale hard-coded totals remain after an inventory rebuild.
- CSVs satisfy the schema, encoding, subset, and partition rules.
- Markdown contains no row-per-file diff table.
- Material claims state evidence, applicability, confidence, and verification.
- Known gaps are explicit; missing As-Is information is not replaced by assumptions.
