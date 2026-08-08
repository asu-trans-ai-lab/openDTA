# DTALite → OpenDTA Migration Strategy (frozen 2026-08-08)

**Principle:** do NOT merge the classical DTALite simulator into OpenDTA
wholesale. The engineering objective is:

> **Re-express validated classical DTALite behaviors as modular OpenDTA
> policies.**

- **OpenDTA's compact simulator = the reference kernel.** Its spine
  (load agents → entrance queue → FFTT → exit queue → node discharge → next
  link, with FIFO, outflow-cap, spatial/KW receiving, CA/CD/waiting updates)
  is valuable — do not destroy it.
- **Classical DTALite = feature donor / legacy oracle.** Local authoritative
  clone: `OpenDTA_ASU/DTALite_legacy` (see `F03d_determinism_rng_audit.md`
  for the RNG/service-discretization specifics).

```
TAPLite regional assignment → columns → OpenDTA clean DNL kernel
                                        + selected, gated DTALite features
```

## What classical DTALite donates (each behind its own gate)

| Donor feature | Notes |
| --- | --- |
| Fractional discharge realization | per-link LCG seed 101, per-interval Bernoulli(frac) — HIGH priority (solves 0.1 veh/interval); port the concept as `ServiceDiscretizer`, not the allocation routine |
| Departure-time profiles | column pool → profile_no → integer vehicles → timestamps; legacy adds deterministic within-profile staggering, not random jitter — behavioral reference for F04, reproduce or deliberately improve with documented reason |
| Period × mode allowed-use | GP/HOV/HOT/truck/managed lanes — regional MPO requirement |
| Time-dependent capacity / events / signals | becomes the μ_a(t) layer — LATER, after constant-μ analytical gold |
| Spatial receiving capacity | downstream occupancy vs storage — the level beyond point queue (spillback, merges) |
| Regional statistics | completed trips, VMT/VHT, network speed — migrate |
| Parallel processing | 4 loops (link init, link state, link entrance→exit, node) — LAST, as its own P-family |

## What must NOT be blindly migrated

- **PCE**: classical code forces `p_agent->PCE_unit_size = 1` with the real
  conversion commented out — PCE is a concept to REBUILD with a new explicit
  test, never "already gold".
- Real-time rerouting, information/DMS response, cell-based behavior,
  impacted-agent tracking, online shortest paths, dynamic ODME — Ring 3,
  outside the regional baseline chain.

## Three rings

- **Ring 1 (required regional DNL):** period/profile loading (F03c contract),
  fractional service, point queue (OpenDTA), spatial receiving, allowed-use,
  PCE (rebuilt), CA/CD/Q/TT (OpenDTA), VMT/VHT (classical), link×time +
  corridor outputs (new).
- **Ring 2 (regional realism):** μ_a(t), work zones/incidents, lane changes,
  signal timing, ramps, headway, spillback refinement, multi-period
  continuous loading — one gold gate each.
- **Ring 3 (advanced DTA):** rerouting/DMS/cell-based/ODME — later, never
  mixed into the baseline.

## Migration mechanics

- **R0 first — freeze both engines as references**: run identical single-link
  / tandem / small-network cases through both where feasible; record
  CA, CD, Q, TT, VMT, VHT, trajectories → differential testing baseline.
- **R1 — departure loading only** (F04a/F04b): D^r + p(t) → D_k → N_k;
  gates Σ N_k = N exact and A_sim(t) ≈ A_profile(t). No link service touched.
- **R2 — `ServiceDiscretizer`**: tiny reusable component
  (integer part / fractional part / fixed-seed draw), knows nothing about
  network/path/OD/rerouting/signals. Gate: c ∈ {0.1, 0.3, 1.0, 1.7};
  same seed ⇒ byte-identical service sequence; long-run mean → c.
- **Then the single-link analytical point-queue gate** (the major gate):
  λ(t) from profile, constant μ, independent Newell gold A/D/Q + T0/T2/T3 +
  Qmax + mean wait. Acceptance: N exact; |ΔCA|,|ΔCD| ≤ 1 vehicle at
  checkpoints; |ΔT_i| ≤ 1 simulation interval; aggregates < 1% (tighter for
  deterministic cases).
- **Then spatial queue**: N_a(t) = CA − CD ≤ K_a; gate chain two links →
  storage → spillback → upstream blocking → tandem → merge/diverge.
- **Then allowed-use + PCE golds**: GP/HOV × SOV/HOV with illegal-trajectory
  count = 0; PCE_truck = 2 with explicit service/storage accounting.
- **Only then μ_a(t)**: `link_id,time_start,time_end,discharge_rate`;
  start with the 3-piece 1800/600/1800 analytical case, not the full signal
  machinery.
- **Regional outputs**: `link_time_performance` (CA, CD, inflow, outflow,
  queue, volume, speed, TT, waiting, occupancy, mu_supplied, mu_used),
  `network_summary` (VMT/VHT/delay/throughput/completed),
  `corridor_performance` for heatmaps.
- **Parallelization last, as its own family**: P01 link init (lowest risk) →
  P02 link processing → P03 node processing (highest risk: merge priority,
  FIFO, receiving, ordering). Blocking gate: threads ∈ {1,2,4,8} ⇒ CA/CD/Q/
  trajectories identical or explicitly tolerance-controlled.

## Target architecture

```
          TAPLite / Regional UE → columns.csv
                     ↓
              Agent Loader (period + profile)
                     ↓
              Serial DNL Core  ← authoritative
              (point queue / spatial queue / FIFO / node transfer)
               |             |
        Service Policy   Supply Policy
        (fractional μ    (μ_a(t), incidents,
         discretization)  signals)
                     ↓
              Link-time states → VMT/VHT + Corridor QA
```

Policies: `DeparturePolicy, ServiceDiscretizer, SupplyProfile,
ReceivingConstraint, ModeAccessPolicy, NodeTransferPolicy,
PerformanceCollector`. Parallelism lives OUTSIDE the mathematical behavior:
one set of DNL rules consumed by a Serial Executor and a Parallel Executor —
never three divergent simulation.cpp variants.

## Frozen near-term roadmap

```
F03c  time contract (Draft PR #1, review → merge)
F-6   repair TT/speed garbage (waiver expires)
F04a  profile → departure demand
F04b  deterministic vehicle generation
F04c  cumulative departure Gold
F04d  classical fractional-service discretizer (ServiceDiscretizer)
G1*   analytical single-link point queue
G2*   tandem
F05   spatial receiving capacity
F06   PCE + allowed-use
F07   mu(t) / event supply
F08   regional VMT/VHT / link-time outputs
P01   parallel link initialization
P02   parallel link processing
P03   parallel node processing
```

Real-time rerouting, DMS, cell-based simulation, and ODME stay outside this
chain. The goal: a small, auditable OpenDTA kernel with the best classical
DTALite features progressively restored and independently validated — not a
large rewrite that becomes impossible to trust.
