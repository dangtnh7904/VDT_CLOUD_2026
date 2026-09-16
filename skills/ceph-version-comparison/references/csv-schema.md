# CSV schema and data rules

Use this schema for `00-file-inventory.csv` and as the immutable prefix of every component CSV.

## File format

- Extension: `.csv`.
- Delimiter: semicolon (`;`).
- Encoding: UTF-8 with BOM, so spreadsheet applications recognize Vietnamese text reliably.
- Line endings: CRLF.
- Header: exactly one row.
- Boolean values: uppercase `TRUE` or `FALSE`.
- Integers: plain ASCII digits without thousands separators.
- Row order: stable endpoint-path order from the master inventory.

Use proper CSV quoting. Preserve path text exactly; do not split on spaces, tabs, or newlines when parsing Git output. Generate the inventory from NUL-delimited Git output.

## Required columns

The base columns, in order, are:

```text
index
base_tag
target_tag
path
old_path
status
status_detail
additions
deletions
binary
old_mode
new_mode
old_blob
new_blob
group
owner_report
priority
file_type
review_mode
analysis_decision
diff_note
```

### Identity and source

| Column | Rule |
| --- | --- |
| `index` | One-based stable integer, unique and contiguous in the master inventory. |
| `base_tag` | User-facing base ref used for the comparison. Keep it consistent across all rows. |
| `target_tag` | User-facing target ref. Keep it consistent across all rows. |
| `path` | Endpoint path: target path for A/M/R, deleted path for D. Unique in the master inventory. |
| `old_path` | Source path only for R; blank otherwise. |

The peeled SHAs belong in the plan/README and in the blob fields below; do not silently replace the user-facing tag columns with branch names from another source.

### Git diff metadata

| Column | Rule |
| --- | --- |
| `status` | Exactly one of `A`, `M`, `D`, or `R`. Fail rather than coercing an unexpected type. |
| `status_detail` | Raw status token such as `M` or `R087`; its leading letter must match `status`. |
| `additions` | Non-negative integer for text; blank for binary. |
| `deletions` | Non-negative integer for text; blank for binary. |
| `binary` | `TRUE` exactly when Git numstat reports `-/-`. |
| `old_mode` | Raw six-digit Git mode, including `000000` and `160000`; legacy inventories may use `0` for an absent side. |
| `new_mode` | Raw six-digit Git mode. |
| `old_blob` | Full object ID from raw diff, including the zero object ID when applicable; legacy inventories may use `0` for an absent side. |
| `new_blob` | Full object ID from raw diff. |

Do not convert binary blank LOC to zero. A text `0/0` row can represent a rename, mode-only change, empty marker, or other metadata change and must remain distinguishable from binary.

A gitlink uses mode `160000`; its blob IDs are submodule commit IDs. If the referenced objects are unavailable, preserve the IDs and label the internal dependency analysis as incomplete.

### Classification

| Column | Rule |
| --- | --- |
| `group` | Owner number `1`–`99`; zero padding such as `01` is allowed but not required. Exactly one per row. |
| `owner_report` | Same-basename report stem such as `01-osd-pg-recovery`; it starts with the zero-padded group and `-`. |
| `priority` | `P0`, `P1`, or `P2` reading priority, not final risk. |
| `file_type` | Stable descriptive category such as `runtime/source`, `test/QA`, `documentation`, `build/package`, or `generated/lock/data`. |
| `review_mode` | One of `deep`, `conditional`, `support`, or `reference-only`. |
| `analysis_decision` | Short reason explaining how the file will be used or why it will not be read deeply. |
| `diff_note` | Optional diff-specific caveat such as a heuristic rename, mode change, binary asset, or gitlink. |

Do not infer a risk rating directly from `priority`, `file_type`, churn, or owner.

## Component CSVs

A component CSV must:

1. keep the 21 base columns as its exact leftmost prefix;
2. preserve every base value byte-for-byte after CSV decoding;
3. contain exactly the master rows whose `owner_report` equals its basename;
4. preserve master ordering;
5. contain no duplicate path and no context-only path.

Analysis columns may be appended to the right, for example:

```text
finding_id;symbols;commit_shas;evidence_status;risk_level;confidence
```

Define any extension column before using it and keep its semantics stable across the suite. Do not delete or repurpose a base column.

## Validation invariants

- Three Git representations resolve to the same endpoint-path key set.
- Status totals sum to the row count.
- Text LOC totals reconcile with numstat and shortstat.
- Binary, rename, mode, and gitlink rows retain their special metadata.
- `index` and `path` are unique; index is contiguous.
- All rows share one base ref and one target ref.
- Every classified row has one valid owner, priority, type, review mode, and decision.
- In complete mode, owner subsets form an exact partition of the master inventory.
