# PA2 spare-chain foundation

This slice adds the durable model and pure reconciliation rules for a PA2
spare-chain upgrade. It does **not** enable cluster mutation.

## State contract

The wave progresses through these observed-state checkpoints:

`WAVE_PLANNED -> CHAIN_READY -> SPARE_CANDIDATE ->`
`SPARE_ADMISSION_ALLOWED -> HANDOFF_GROUP_CONVERGING ->`
`HANDOFF_GROUP_SCRUBBING -> HANDOFF_GROUP_ACCEPTED ->`
`HANDOFF_COMPLETE -> SOURCE_UPGRADING -> SPARE_ROTATED ->`
`WAVE_RECONCILING -> WAVE_STABILIZING -> WAVE_COMPLETE`

`HANDOFF_COMPLETE` is deliberately not an alias for `WAVE_COMPLETE`. The
source still has to be upgraded, returned as the next spare, and reconciled
against the selected end state before the wave can enter its stability window.

## Fail-closed rules

- A spare must be reserved, healthy, on the expected digest and isolated from
  production traffic.
- Admission requires a distinct failure domain, a safe down set and ownership
  of the current lease generation.
- Each handoff group needs stable mapping plus conclusive replica checks.
- The source cannot be upgraded until absent from the full `up` and `acting`
  scope.
- A resumed worker must reacquire current mapping and reconcile the durable
  ledger; it never trusts a previous command return code.
- Cleanup cannot remove a spare or dependency still owned by another chain.
- If the final spare never receives a PG, its operation result is
  `NOT_EXERCISED`, not `PASS`.

## Durable ledger

Migration `0014_pa2_spare_chain_ledger.sql` adds wave, spare registry, chain,
handoff-group, rotation-step and end-state records. These records are intended
to be written transactionally with the existing phase-event and outbox
records when live orchestration is introduced in a later slice.

## Current boundary

The code in this slice is a domain simulator and schema contract only. It does
not add executor actions, SSH commands, Ceph mutation endpoints, or a claim
that PA2 has been exercised on a live cluster.
