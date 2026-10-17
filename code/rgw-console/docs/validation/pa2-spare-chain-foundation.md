# PA2 spare-chain foundation validation

Status date: 2026-10-08

## Added checks

- P201: chain reservation, failure-domain, down-set and lease gate.
- P202: spare image digest mismatch holds the chain.
- P203: admission is denied without the current lease/topology evidence.
- P204: a mapping change during replica validation holds the group.
- P205: handoff completion remains distinct from wave completion.
- P206: source upgrade is blocked until the source is absent from every
  observed `up` and `acting` set.
- P207: end-state reconciliation and a stable window are both required.
- P208: an unexercised final spare reports `NOT_EXERCISED`.
- P209: resume and recovery use fresh observed mapping.
- Cross-chain dependency cleanup is fail-closed.
- Migration 0014 has a contract test for every PA2 ledger table.

## Execution status

The PA2 domain and migration contract tests pass under the repository's
canonical `unittest` runner. The full backend regression on 2026-10-08 reported
139 passing tests and 11 PostgreSQL integration tests skipped because
`TEST_DATABASE_URL` was not configured.

The migration file was moved into `app/migrations/versions`, which is the
package consumed by the migration runner; schema expectations now target
version 15 after the subsequent QoS migration.

No live PA2 action has been run and no live-cluster claim is made.
