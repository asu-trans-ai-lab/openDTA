# F05 Mini-Spec — Supply-contract FD parameters + Daganzo-mid merge + diverge/lane-drop gates

Per rules §15. Branch: `feature/node-models` → PR #12. **The most sensitive
kernel change of the project: it retires the `(t+i)%m` node rotation
(finding M-1) inside the node-transfer loop.** Authoritative model: the
DTALite paper §3.7.2 (Daganzo 1994 priority merge with the mid() operator);
gates prepared by the book battery (ST06/07/08 READMEs carry the frozen
truths from Knoop §11.1 and Treiber ch. 8).

Three separately attributable commits on one branch:

## F05-pre (M-13) — FD parameters into the supply contract

`link.csv` gains optional columns `jam_density` (veh/mi/lane) and
`backwave_speed` (mph); absent → the current global defaults (200 / 12)
byte-identically. `Link` stores them; `LinkQueue` computes `spatial_cap` and
`backwave_tt` from the link, not from `global.h` constants. Pure plumbing —
no behavior change on any existing dataset (regression: full battery
byte-identical). This unlocks per-link FDs for ST08's front-speed oracle and
F07's μ(t).

## F05-a — Daganzo-mid merge allocation (the kernel change)

**Current behavior:** the node loop drains incoming links in rotation order
`(t+i)%m`, each while `has_outflow_cap`; under spatial/KW receiving, the
downstream storage gate makes the rotation an implicit ~alternating merge
rule — undocumented, priority-blind (M-1).

**Requested behavior:** per (node, receiving downstream link, interval),
when the receiving budget R_t binds, allocate it across the competing
incoming links by Daganzo-mid with lane-proportional priorities:

```
q_i = mid{ d_i,  R_t − Σ_{j≠i} d_j,  p_i · R_t },   p_i = nlanes_i / Σ nlanes
```

where `d_i` = vehicles ready at link i's exit queue this interval, and
R_t = the downstream link's per-interval receiving allowance (spatial/KW
storage headroom, and — new, per the paper's cap_out = min{q_max, cap_in}
— never more than the downstream link's own service rate per interval,
which is what makes ST06's R = 2400 bind).

**Integerization:** fractional shares (p_A·R = 3.2/interval) accumulate in
per-(node, incoming-link) deterministic credit accumulators (the S4
accumulator concept — `credit += share; release = floor(credit);
credit -= release`). No RNG. FIFO within each link unchanged; the
invariance principle (raising d_B must not raise q_B once both congest)
falls out of the mid formula.

**Scope guard:** single-incoming nodes take a fast path identical to today
(no allocation, no accumulator) — every existing green case (ST00…ST05,
tandem, baselines) has single-incoming nodes only and must stay
**byte-identical**. The allocation path activates only at true merges.

## F05-b — Diverge & lane-drop gates (no new model — measurement)

Diverge stays path+FIFO by construction (paper §3.7.3). Under spatial
receiving, ST07's blocked off-ramp must throttle the through movement via
the shared FIFO exit queue: gate asserts main-movement plateau falls into a
band around the Knoop FIFO value (600; acceptance band measured and frozen
at implementation, per the README). ST08 activates its today-testable
invariants as a gate (bottleneck discharge == 1800 exactly while queued;
per-interval CD_i == CA_{i+1} conservation across the chain) and records
segment queue-onset times for the front-trajectory oracle (full numeric
freeze deferred to the FD-contract follow-up with Treiber Problem 8.5).

## Gates

| Gate | Assertion |
| --- | --- |
| ST06 (spatial tier) | downstream plateau 2400/h; per-approach discharge **1920 / 480** (±2%); invariance: d_B ↑ 1500→2000 leaves q_B at 480 |
| ST07 (spatial tier) | shared-link FIFO throttling: main plateau in the frozen band around 600; ramp 1200; no independent-caps bypass |
| ST08 | bottleneck discharge 1800 exact while queued; chain conservation per interval; onset-time monotonicity upstream |
| Full battery | 15 existing gates green; single-incoming datasets **byte-identical** (fast-path proof); baselines untouched |

## Files
`include/global.h` (defaults only), `include/supply.h` (Link FD fields,
LinkQueue), `src/utils.cpp` (read_links two optional columns),
`src/simulation.cpp` (node loop: fast path + merge allocation), fixtures'
gate script `tools/check_node_models.py`, ST06/07/08 yml flips.

## Risk
High (node loop). Mitigations: fast-path byte-invariance over the entire
existing battery; three attributable commits (pre / merge / gates); the
rotation code is deleted only in the multi-incoming branch; red-first on
ST06's 4:1 split.
