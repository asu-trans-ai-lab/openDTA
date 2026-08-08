# v1 → v2: what was missing and what changed

v1 (`GOLD-DTA-2R-MP-v1`) was verified before this upgrade: its solver
reproduces its own frozen gold byte-for-byte and all 51 of its checks pass.
The gaps below are measured against the gate discipline, the design
invariants (I1–I12), and the data-contract specification — not against v1's
own goals.

## Gap 1 — no sequential gates (blocking)
v1 jumps straight to the composite network case. When an engine mismatches it,
the error could be in the queue integrator, the period boundary, the tandem
handoff, PCE, or the profile — indistinguishable. v2 adds G1/G2/G2b as
separate hand-computable cases with the gate-reference numbers frozen verbatim
in `assertions.json`, asserted numerically (161 checks total, all passing).

## Gap 2 — no vehicle layer (blocking)
v1's gold is fluid-only; Gate 3 checks 3.1–3.8 had no evidence. v2 adds
`vehicle_gold.py`: largest-remainder vehicleization (Σₜ N == round(V) exact,
no ceil inflation, no RNG), a deterministic FIFO vehicle DNL, the
`vehicle_link_trajectory_gold.csv` audit trail with BOTH `demand_period_id`
and `supply_period_id` per row, `vehicle_trajectory_gold.csv` with
`trip_completed`/`incomplete_reason`, and `reconciliation_gold.csv`
(tap → vehicleized → entered → completed). 55 rows in G3 and 617 in G4 show
`demand_period ≠ supply_period` — I4 as evidence, not documentation.

## Gap 3 — I3 was true in the data but asserted nowhere
v1's L5 queue is continuous across 08:00 (56.2 → 57.5) but no check would
have caught a regression. v2 adds `period_boundary_audit.csv` per case
(Q at t⁻/t⁺, μ before/after, both delays, physically-bounded reset detector)
plus explicit continuity cells: G1's Q(08:00)=266.667 across a μ **increase**,
G2b's Q(07:45)=210 across a μ **decrease mid-queue** — asserted simultaneously
with CD→CQ conservation, because a reset bug breaks both and separate tests
can let both pass. The delay discontinuities (16.00→13.33 down in G1;
14.0→16.8 up in G2b) are asserted as **correct physics** so a reviewer does
not "fix" them.

## Gap 4 — corridor conservation untestable (no ramps)
v1's corridors are bare mainline lists; `CA_{i+1} = CD_i + R^on − R^off` was
only exercised trivially, and on real corridors it would fail legitimately
and read as a DNL bug. v2's G4 declares an on-ramp (merge n1) and an off-ramp
(diverge n3) in `corridor.csv` and freezes `corridor_conservation_gold.csv`
per junction per interval, residual ≤ 1e-9.

## Gap 5 — contract fields missing
Added to `link_period.csv`: `capacity_unit` (declared per row, I7),
`reference_tt_sec` (the third quantity in the μ / τ⁰_physical / τ⁰_reference
separation), `capacity_ratio`, `reference_tt_source`. Added
`departure_profile_binding.csv` with the fallback hierarchy and uniform
fallback profiles. CRLF line endings removed.

## Gap 6 — outputs missing E_a(t), experienced TT, corridor layer
Every `link_time_performance` row now stores `exit_time = t + TT(t)` (I10)
and `experienced_tt_sec` alongside the instantaneous value.
`corridor_time_performance_gold.csv` carries experienced (composed through
`E_a`) AND instantaneous corridor TT, clearly labelled, plus slowest link —
derived from state, never from a period midpoint.

## Gap 7 — a real defect found and fixed in the reference solver itself
With 60 s ticks, fftt values of 66/72 s put cohort ready-times mid-tick,
producing a phantom standing queue of ≈ one tick of inflow on every
free-flowing link (v1's L5 "T0 07:31" contained this artifact; on ramps it
manifested as a fake 5-PCE permanent queue). Fixed by making simulation and
record resolution independent (I11): G3/G4 simulate at 6 s, record at 60 s.
G1 gains a guard assertion (Q(07:10)==0) so the defect class cannot return.
This is precisely the kind of engine bug the gates exist to catch — the gold
generator had it too.

## Gap 8 — recording semantics made hand-checkable
v1 recorded state after processing the tick, so CA(07:00) already included
07:00–07:01 arrivals and no gold value matched a hand table exactly. v2
records before the tick: every row equals the continuous value at t, and the
Gate 1 gold matches the reference table verbatim.

## Gap 9 — dynamic negative case
v1's negative case was static only. v2 adds the I4 trap
(`vehicle_truck_boundary_entry.csv`): statically legal truck, dynamically
illegal at L2 entry at 08:00:36. Verified against the reference loader:
rejection at entry with reason and blocked link, after legally traversing L1.

## Unchanged from v1 (deliberately)
The G3 network topology, demand, classes, and period structure; the fluid
point/tandem queue physics; determinism ("no random numbers, inputs immutable
after release"); long-format outputs; the gate-manifest philosophy.
