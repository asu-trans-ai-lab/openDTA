# F03d — Determinism / RNG Audit (NO behavior change)

Audit only: this document inventories every random or nondeterministic process
in the openDTA engine, records the **authoritative legacy DTALite reference
behavior**, and freezes the rules F04+ must follow. Zero source-code
modification is part of this feature.

Legacy reference clone: `OpenDTA_ASU/DTALite_legacy` (asu-trans-ai-lab/DTALite,
shallow @ HEAD 2026-08-08). Cited lines verified there.

---

## 1. Inventory: randomness / nondeterminism in openDTA (at F03c head)

| # | Site | What it is | Deterministic? |
|---|---|---|---|
| R1 | `include/global.h:79` `uniform(lb, ub)` | the **only RNG in the engine**: `static std::random_device rd; static std::mt19937 gen(rd());` | **No — seeded from `random_device`, differs every process run; no seed control** |
| R2 | `include/supply.h:1550` `LinkQueue::get_flow_cap()` | sole caller of R1: fractional per-interval outflow capacity rounding | No (via R1), and defective — see §3 |
| R3 | `src/simulation.cpp` `setup_agents()` | `ceil(volume)` agents, uniform departure spread (`i/vol*dur`) | Yes (no RNG) — defect F-2 is bias, not randomness |
| R4 | F-6 uninitialized reads | `travel_time`/`speed` garbage in `link_performance_dta.csv` (both volume==0 and volume>0 rows; 5 unstable lines across 3 same-exe reruns) | **No — memory garbage, NOT an RNG**; every other output column byte-stable |
| R5 | OpenMP parallel loops (UE column generation, I/O) | thread scheduling | UE outputs verified byte-identical across reruns (F01/F02/F03c regressions) — no observed nondeterminism today, but no design guarantee |
| R6 | `supply.h` `unordered_set` (column hashing) | hash-container iteration order | not observed to affect outputs (columns.csv byte-stable); flagged for watch |

**Conclusion:** run-to-run drift in openDTA today has exactly two roots:
R1/R2 (unseeded RNG in capacity rounding) and R4 (F-6 uninitialized reads).
The F03c regression drift is fully explained by R4 — `setup_agents()` has no
RNG, so it was correct not to attribute it to departure-time randomness.

---

## 2. Authoritative legacy DTALite reference (do not redesign casually)

> **Legacy DTALite service-discretization behavior is authoritative until
> independently shown incorrect.**

Legacy has **two distinct random subsystems** — they must never be conflated:

### 2a. WELL512a — the validated general-purpose RNG
`WELLRNG512a` (Panneton & L'Ecuyer, U. Montréal; Matsumoto, Hiroshima) —
the user-supplied source is the authoritative implementation. Seeding:
`g_RandomSeed = 100`; `state[k] = k + g_RandomSeed`; `InitWELLRNG512a(state)`
(legacy `input.h:2682`). Exposed as `g_get_random_ratio()`.
Used for: departure-time sampling in `CDeparture_time_Profile`
(small-sample cases, `DTA.h:146,174`, member seed 101) and zone/district
sampling (`input.h:939,1022`).

### 2b. Inline LCG — fractional service capacity rounding
`AllocateLinkMemory4Simulation` (`simulation.cpp:110-141`):

```cpp
unsigned int RandomSeed = 101;          // LOCAL, reset per link
// per simulation second t:
residual = OutFlowRate - (int)OutFlowRate;
RandomSeed = (LCG_a * RandomSeed + LCG_c) % LCG_M;   // a=17364, c=0, M=65521
random_ratio = float(RandomSeed) / LCG_M;
cap[i][t] = (int)OutFlowRate + (random_ratio < residual ? 1 : 0);
```

Properties that make this the reference:
- **Bernoulli with the correct orientation**: P(+1) = fractional part, so
  E[cap per interval] equals the fractional capacity exactly
  (c = 0.1 veh/interval → one vehicle every ~10 intervals, never starved);
- **drawn per interval**, so a 0.1-capacity work zone discharges over time;
- **reproducible by construction**: fixed local seed 101 per link, fixed call
  order, no cross-link or cross-thread state → same input ⇒ identical
  capacity realization, every run;
- constants `LCG_a=17364, LCG_c=0, LCG_M=65521` (`DTA.h:45-47`; 16-bit M is a
  deliberate memory tradeoff, documented there).

Known legacy wart (do not import): `DTA.h:758` — Peiheng's 02/02/21 comment
flags an uninitialized `m_RandomSeed` in one class. Any port must
initialize every seed explicitly.

### 2c. The conceptual split that must be documented in code

```
capacity stochasticity      C -> C'                 : OFF for gold baselines
service discretization      C'*dt/3600 -> {0,1,...} : KEPT and tested
```

The second one is **numerical discretization, not physical uncertainty**.
Deleting it "because gold tests must be deterministic" would break the model
(a 0.1 veh/interval work zone would never discharge). Gold handles it with
two modes (§4) — never by removal.

---

## 3. Defect findings in openDTA `get_flow_cap()` (feeds defect F-3)

```cpp
double c1 = link->get_cap() / SECONDS_IN_HOUR * res;
size_type c2 = std::floor(c1);
size_type residual = uniform(0.0, 1.0) >= c1 - c2 ? 1 : 0;
return c2 + residual;
```

1. **Horizon-constant draw**: called once in the `LinkQueue` constructor and
   used to fill `outflow_cap(n, ...)` — one realization for the entire
   horizon, vs legacy per-interval draws. A fractional capacity becomes
   all-or-nothing for the whole run.
2. **Inverted Bernoulli**: `uniform >= frac ? 1 : 0` gives P(+1) = 1 − frac.
   c = 0.1 → E[cap] = 0.9 instead of 0.1 — ninefold overcapacity; c = 0.9 →
   E[cap] = 0.1 — ninefold undercapacity.
3. **Integer capacities silently inflated**: frac = 0 ⇒ `uniform >= 0` always
   true ⇒ cap = c2 + 1 every time. A link with exactly 2.0 veh/interval gets
   3. (This branch is deterministic, which is why Two_Corridor trajectories
   were byte-stable in F01/F03c regressions despite the unseeded RNG.)
4. **Unseeded RNG**: `random_device`-seeded `mt19937`, no seed control — the
   fractional path is unreproducible by design.

Legacy comparison: none of 1–4 exist in the legacy LCG scheme.

---

## 4. Frozen rules going forward

1. **Temporary waiver, not a rule**: the F03c regression change (exclude
   `travel_time`/`speed` columns of `link_performance_dta.csv` on all rows)
   is a **waiver for defect F-6 only**. It expires when F-6 is repaired;
   those two columns then return to the byte-exact gate. Permanently
   excluding the DNL's two most important outputs is not acceptable.
2. **F-6 is repaired as its own minimal feature** (before F04 queue physics):
   defect = nondeterministic/uninitialized travel_time and speed in
   link_performance_dta. Until then: no parallel-determinism claims; no gold
   status for TT/speed; trajectories + CA/CD/Q/density/queue remain the
   stable reference.
3. **Gold Mode A — integer-service analytical**: choose capacities so
   c ∈ {1, 2, 3} veh/interval exactly; zero randomness anywhere; compare to
   the Newell/point-queue analytical solution
   `D(t) = inf_{s≤t} [A(s) + M(t) − M(s)]`, `Q = A − D`.
4. **Gold Mode B — fractional-service statistical**: c ∈ {0.1, 0.3, 1.7};
   legacy LCG algorithm + fixed seed; require (a) same seed ⇒ byte-identical
   trajectory, (b) mean released ≈ Σc, (c) no starvation under persistent
   queue. Different seeds may differ per-vehicle but must match in long-run
   throughput.
5. **Deterministic accumulator as test oracle** (not production replacement):
   `R += c; n = floor(R); R -= n` — used to cross-check the RNG rounding's
   long-run behavior.
6. **Tolerance tiers** (single-link analytical gold):
   - conservation: exact (|ΔN| = 0 after integerization; ≤1e-9 continuous);
   - cumulative counts at checkpoints: ≤ 1 vehicle;
   - event times (onset T0, peak, clearance T3): ≤ 1 simulation interval
     (6 s at res=6), never percentages;
   - aggregate Qmax / mean wait / VHT: < 1% initially, target < 0.1% for
     deterministic integer-capacity cases. 1% is for realistic corridor
     validation, not analytical gold.
7. **First round uses constant μ.** Time-dependent μ(t) via link_time_profile
   waits until the chain λ(t) → A(t) → Q(t) → D(t) survives the analytical
   gates. Never tune five subsystems at once.
8. **RNG porting rule**: same algorithm, same explicit seed, same call
   ordering, single-thread reference sequence first; parallel only after the
   single-thread sequence is frozen.

---

## 5. Revised feature sequence (replaces the monolithic F04)

```
F03c  time-contract reader          → Draft PR #1, line-by-line review, then merge
F03d  this audit                    → no code change
F-6   repair TT/speed garbage       → minimal patch; rerun EXACT regression; waiver expires
F04a  conditional profile → departure-bin demand      Gate: demand conservation (exact)
F04b  bins → integer agents (largest remainder)       Gate: vehicle count (exact)
F04c  agent departures → cumulative A(t)              Gate G6A: A(t) vs theoretical profile
F04d  legacy RNG / service-discretization port audit  Gate: fractional capacity (Mode B)
F04e  single-link service implementation              Gate: D(t)
F04f  queue formation/clearance                       Gate G7A: Newell CA/CD/Q
F04g  waiting time / travel time                      Gate G7B: T0/T2/T3 + analytical TT
F04h  legacy DTALite cross-check                      Gate: old-vs-new
      → only then two-link / tandem / two-corridor / Chicago
```

Each step lands alone, gated, human-reviewed. Chicago running proves nothing
about any of these steps.
