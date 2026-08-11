# V1-e Mini-Spec — the three frozen self-tests + path loading summary

Per OPENDTA_V1_MVP_SPEC.md section 7 and build-order bullet V1-e. These
three tests are **the v1 acceptance bar** — the spec's success definition
ends "three self-tests green". Branch `feature/v1e-self-tests`.

Most of the machinery already exists and is green; V1-e is mainly *new
assertions on existing cases* plus one new fixture triplet. What is new is
listed per test.

## New output: `path_loading_summary.csv`
Deferred from V1-d because Test 1 has to build the path->link incidence
mapping anyway, and writing it twice would fork that mapping.

```
path_id, od_id, period, path_volume, vehicles_generated,
vehicles_exited, vehicles_remaining, avg_travel_time_min,
avg_distance_mi, link_sequence_len
```
`path_volume` is the frozen input flow f_k; `vehicles_generated` is what
S2a largest-remainder actually produced. The two differ by at most the
rounding residual and the gate asserts exactly that — it is the audit
that catches a vehicleizer silently losing or inventing demand.

## Test 1 — free-flow fixed path (extends ST00)
EXISTS: Q = 0, TT = FFTT to the second (ST00 gold, already green).

NEW assertions, all three from the path layer rather than the link layer,
so they fail if the path->link mapping is wrong even when the DNL is right:
- **`x_l = sum_k A_lk f_k`** — every link's loaded volume equals the sum of
  the path flows crossing it, where A is the path-link incidence matrix
  built from `path.csv`'s link_sequence. This is the assertion that proves
  the DNL loaded the paths it was given and nothing else.
- **`VMT = sum_l x_l L_l`** recomputed from the path side and matched to
  `run_summary.json`.
- **`VHT = sum_l x_l FFTT_l`** — exact under free flow, since no vehicle
  waits. Any deviation means phantom delay.

## Test 2 — single-link bottleneck vs the fluid oracle (extends ST02a/ST04a)
EXISTS: exact analytical oracle, SQM paper digits (already green).

NEW assertion: **`N_entered == N_exited + N_remaining`**.

> **Dependency — read before implementing.** V1-d found (D-3) that the
> agent-side completion record and the link N-curves disagree whenever
> vehicles are still queued at the horizon: `dep_intvls` is PRE-SET by
> `increment_dep_interval()` when a vehicle joins an exit queue and only
> overwritten on actual release. On cases that fully drain (ST02a, ST04a
> both do — V1-d's gate shows conservation 0 FAIL) the identity holds and
> this test passes today. It will NOT hold on a case that ends congested
> until D-3 is closed with a kernel release stamp. **Scope V1-e to the
> draining cases and say so in the gate**, rather than writing an
> assertion that quietly encodes the defect as expected behaviour.

## Test 3 — short-corridor profile triplet (extends ST03_tandem_gold) — NEW
The only genuinely new fixture work. Same frozen path volumes, same
network, run three times under **uniform / single-peak / double-peak**
departure profiles (the profiles already exist in the ST02a / ST02d bank;
this is wiring, not new profile math).

Invariant across the triplet — these must NOT move:
- per-path and per-link volumes;
- VMT;
- vehicles generated / exited.

Must move, in the stated direction:
- **VHT** rises as the profile concentrates (uniform < single-peak, and
  double-peak between the two if the peaks are lower than the single);
- **P** (queue duration) and **v_T2** — a sharper peak makes a deeper,
  shorter queue: v_T2 falls, and P need not rise;
- the queue time profile itself changes shape.

Plus, on every member of the triplet:
- **spillback direction is correct** — when the downstream link fills, the
  queue appears on the UPSTREAM link, never downstream of the bottleneck;
- **every trajectory is complete** (subject to the same D-3 caveat: the
  triplet must be given a drain buffer so all three fully clear, otherwise
  the assertion is testing the defect rather than the physics).

This test is what distinguishes a real DNL from a static assignment: the
same demand, differently timed, must produce the same mileage and
different delay.

## Gate — tools/check_self_tests.py (20th)
Red-first, as with V1-b/c/d. All three tests report into `gate_report.json`
alongside the existing battery entries, so "three self-tests green" is a
machine-readable claim rather than a sentence in a report.

## Files
`dev/test/v1e/` (the profile triplet fixtures), `include/handles.h` +
`src/utils.cpp` (path_loading_summary writer, reusing the
`output_run_reports()` metric pass), `dev/self_test_simulation/tools/
check_self_tests.py`, runner registration.

## Explicitly NOT in scope
Fixing D-3. V1-e scopes its assertions to draining cases and names the
limitation; closing D-3 touches the protected kernel and is its own change.
