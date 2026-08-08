# Simulation Improvement Design — Step-by-Step Cases (S0–S6)

Design for review before any simulation-side code change. Each step: exact
code target, its own case with hand-computable numbers, and acceptance
criteria per the frozen tolerance tiers (conservation exact / event times
≤ 1 simulation interval / aggregates < 1%). One step lands, gates, and is
human-reviewed before the next begins. Companion docs:
`F03d_determinism_rng_audit.md`, `F04_dtalite_migration_strategy.md`.

---

## S0 — Repair F-5/F-6 (the waiver expires here)

### Root cause, located exactly

**Defect 1 (F-5, the visible F-6 symptom).** `supply.h:1492`:

```cpp
size_type get_travel_time(size_type i, unsigned short k) const
{
    auto tt_intvl = get_period_fftt_intvl(i);   // BUG: passes simulation
                                                // interval i, not period k
    return to_minute(tt_intvl) + get_avg_waiting_time(i) / SECONDS_IN_MINUTE;
}
```

`get_period_fftt_intvl` indexes `vdfps[k]` — passing `i` (a simulation
interval, e.g. 600) reads far past the 1–4 entry `vdfps` vector: an
**out-of-bounds heap read**. Garbage fftt → garbage travel_time →
`speed = length / garbage` → the 0 / 41130 / 8738 / `inf` drift seen in
regression, varying with heap layout per run. Exactly matches the observed
signature: only `travel_time`/`speed` columns drift, every other column is
byte-stable.

**Defect 2 (F-6 boundary).** `supply.h:1521`:

```cpp
auto arr_rate = cum_arr[i + delta] - cum_arr[i];   // i + delta runs past
                                                   // cum_arr.size() at the
                                                   // end of the horizon
```

**Defect 3 (adjacent, fix together).** `get_travel_time` returns `size_type`
(unsigned integer minutes) — truncates fractional minutes; return `double`.
(Behavior change is confined to the two already-waived columns.)

### Minimal patch (3 lines + 1 signature)

1. `get_period_fftt_intvl(i)` → `get_period_fftt_intvl(k)`;
2. clamp the upper index: `auto j = std::min(i + delta, cum_arr.size() - 1);`
3. return type `double` for `get_travel_time` (speed math unchanged).

Files touched: `include/supply.h` only. Protected components untouched.

### Case & gate

- Rerun Two_Corridor point-queue and kinematic-wave DTA **3×**:
  `link_performance_dta.csv` must now be **byte-identical across reruns**
  (drift gone at the root, not masked).
- All other baseline outputs byte-identical to F01 references.
- Hand check (Two_Corridor, point queue): uncongested rows must show
  `travel_time = fftt(period)` exactly and `speed = length/fftt·60`;
  congested rows `travel_time = fftt + avg_wait/60`.
- **The F-6 waiver is then deleted from the baseline README** and
  `travel_time`/`speed` return to the byte-exact regression gate, with new
  frozen reference values recorded.

Risk: low (indexing fix). But it touches `supply.h` → full gate suite reruns.

---

## S1 — F04a: conditional profile → departure-bin demand (no vehicles)

Pure arithmetic on already-loaded objects; no simulation change.

**Code target:** new small function consuming `dep_profiles` (F03c
conditionals) + period demand; emits `departure_bin_demand.csv`
(`period_id, agent_type, profile_id, bin_start, bin_width_sec, conditional_weight,
demand`).

**Case A (hand):** D = 1000, AM_PEAK bins 0.4 / 0.6 → D_k = 400 / 600.
**Case B (real):** TRANSIMS four-period fixture — every (period, agent):
Σ_k D_k = 1000 exactly.

**Gate (exact):** `Σ_k D_k = D` to 1e-9; every bin inside its window;
weights match the G5 audit's conditionals bit-for-bit.

---

## S2 — F04b: bins → integer agents (largest remainder; F-2 dies here)

**Code target:** `setup_agents()` — the first kernel touch. Replace
`ceil(volume)` + uniform spread with:

1. per column: integer vehicle count by **largest-remainder over bins**
   (Σ_t N_t = round(V) exactly, no ceil inflation, no RNG) — the same rule
   the gold `vehicle_gold.py` uses;
2. departure times: deterministic within-bin staggering (legacy behavioral
   reference: even offsets within the bin, NOT random jitter);
3. no profile bound → previous uniform behavior byte-preserved (fallback).

**Cases:**
- V = 1000, two bins 0.4/0.6 → exactly 400 + 600 agents, ordered times;
- V = 10.2 (fractional column) → 10 agents (largest remainder), not 11
  (ceil) — the explicit F-2 regression case;
- unbound dataset (Two_Corridor as-is) → **byte-identical trajectories vs
  F01 baseline** (fallback proof).

**Gate (exact):** Σ agents = Σ round(column volumes); per-bin counts match
S1 demand bins after integerization (|N_k − D_k| < 1); unbound datasets
unchanged.

---

## S3 — F04c: agents → cumulative departure A(t) gold

No new simulation behavior — an audit output + gate.

**Code target:** emit `cumulative_departure_audit.csv`
(`period_id, agent_type, minute, A_sim, A_theory`), where
A_theory(t) = D · F_r(t) from the conditional profile.

**Case:** TRANSIMS Trucks, D = 1000, MD window: A(t) staircase vs
1000·F_r(t).

**Gate:** |A_sim(t) − A_theory(t)| ≤ 1 vehicle at every minute checkpoint
(integerization bound); final value exact.

---

## S4 — F04d: ServiceDiscretizer (legacy LCG port)

**Code target:** new self-contained component (knows nothing about network /
path / OD / signals):

```cpp
class ServiceDiscretizer {          // legacy-faithful
    // per-link state: seed reset to 101 at construction
    // per interval: c = mu*dt/3600; frac = c - floor(c)
    // seed = (17364*seed + 0) % 65521; r = seed/65521.0
    // n_t = floor(c) + (r < frac ? 1 : 0)      // correct orientation
};
```

Wired into `LinkQueue` to **replace `get_flow_cap()`** (the quadruply
defective single-draw — see F03d §3): per-interval fill of `outflow_cap`,
exact integer path when frac == 0 (no +1 inflation).

**Cases (unit, no network):** c ∈ {0.1, 0.3, 1.0, 1.7} veh/interval,
10,000 intervals, seed 101:
- rerun ⇒ **byte-identical n_t sequence** (twice);
- mean(n_t) → c within 1% at 10k draws (LCG quality bound);
- c = 1.0 ⇒ n_t ≡ 1 (integer path exact, never 2);
- no starvation: c = 0.1 with persistent queue ⇒ D(T) > 0;
- cross-check against the deterministic accumulator oracle
  (`R += c; n = floor(R); R -= n`): cumulative released differs by ≤ 1 at
  every t.

**Network gate:** integer-capacity datasets (Two_Corridor: every link's
μ·6/3600 is whole) produce **byte-identical trajectories vs the S0 baseline**
— proving the replacement only changes fractional behavior.

---

## S5 — Gold A: analytical single-link point queue (the major gate)

**No new code** — the first physics validation of the whole chain
S1→S2→S3→S4 against an independent oracle.

**Case (all hand-computable):** single link, μ = 1200 veh/h constant,
profile-driven arrivals:

```
lambda(t) = 600  veh/h   t in [0, 30) min
            1800 veh/h   t in [30, 90)
            600  veh/h   t in [90, 150)
```

Analytical gold (Newell: D(t) = inf_{s≤t}[A(s) + μ(t−s)], Q = A − D):

| Quantity | Value |
| --- | --- |
| A(30) / A(90) / A(150) | 300 / 2100 / 2700 veh |
| Queue onset T0 | t = 30 min (λ crosses μ) |
| Queue growth | +600 veh/h on [30, 90) |
| Peak queue Qmax | **600 veh at t = 90** |
| Queue clearance T3 | **t = 150 min exactly** (drains at −600 veh/h) |
| D(90) / D(150) | 1500 / 2700 veh |
| Max individual wait | Qmax/μ = 30 min |
| Total delay (Q triangle) | ½ · 600 · 2 h = **600 veh·h** |

**Acceptance:**
- vehicles loaded = 2700 exact;
- |CA_sim − A|, |CD_sim − D| ≤ 1 vehicle at checkpoints t = 30, 60, 90,
  120, 150;
- |T0_sim − 30|, |Tpeak_sim − 90|, |T3_sim − 150| ≤ 1 simulation interval
  (6 s);
- Qmax, total delay: < 1% (target < 0.1%, deterministic integer case);
- run twice: byte-identical.

Also rerun with **three different profiles at the same D**: totals must stay
exact and equal; A(t)/queue trajectories must differ. Identical curves
across different profiles = automatic FAIL.

---

## S6 — Tandem gate (reuse frozen gold)

Feed `cases/G2_two_link_tandem` and `G2b` inputs through the engine:
CD₁(t) == CQ₂(t + τ⁰₂) to ≤ 1 vehicle; queue continuity at the μ step
(G2b Q₂(07:45) = 210, delay 14.0 → 16.8 up — asserted as correct physics);
vehicle conservation CA₁(T) − CD₂(T) = vehicles in system. Only after S6:
spatial receiving (F05), PCE/allowed-use (F06), μ(t) (F07), outputs (F08),
parallel P01–P03 per the migration strategy.

---

## Sequencing and discipline

```
S0 (F-5/F-6 fix, supply.h only)  → waiver expires, new frozen TT/speed refs
S1 (F04a, arithmetic + audit csv)
S2 (F04b, setup_agents largest-remainder + fallback byte-preservation)
S3 (F04c, A(t) audit gate)
S4 (F04d, ServiceDiscretizer replaces get_flow_cap)
S5 (Gold A analytical single link — the major gate)
S6 (tandem via frozen gold cases)
```

Every step: mini-spec confirmation → feature branch → Draft PR → gates →
completion report → human review → merge. Constant μ throughout; μ(t),
spatial queue, PCE, parallelism all wait behind S6.
