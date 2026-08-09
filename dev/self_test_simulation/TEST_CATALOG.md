# OpenDTA Simulation Self-Test Catalog

The authoritative registry of every simulation self-test case: its traffic-flow
mathematics, exact expected values, gate criteria, current status, and — for
every red item — a diagnosed owner. Human-review companion:
`test_catalog.html` (self-contained, with diagrams). Principle:

> Analytical truth → small case → production engine → numerical comparison →
> human visualization. Engine output is never frozen into "gold".

## 0. The core contract (paper Eq. (8)–(10))

For agent f on link a, from its recorded timestamps:

```
TT_fa = TD_fa − TA_fa  =  FFTT_a + t_w,fa  =  t_F,fa + t_Q,fa
v̄_fa  = L_a / TT_fa
```

Three speeds — never conflated again:

| Symbol | Name | Definition |
| --- | --- | --- |
| v_F | free_flow_speed | link attribute |
| v̄_a(t) | experienced_average_speed | L_a / TT_a(t), TT aggregated by entry time |
| v_Q | queueing_speed | congested-branch FD speed inside the physical queue |

Under constant-μ, no-spillback SQM (triangular FD, backward wave w, jam
density k_j):

```
k_Q = k_j − μ/w          v_Q = μ / k_Q
t_Q = t_w · v_F / (v_F − v_Q)          (time physically in queue)
t_F = FFTT − t_w · v_Q / (v_F − v_Q)   (time at free-flow speed)
d_Q = v_Q · t_Q                        (physical queue segment length)
```

Applicability: t_F > 0. When t_w is large relative to FFTT (e.g. ST02a's
30-min delay on a 1-mile link) the SQM constant-bottleneck form does not
apply — those cases stay point-queue-only golds.

Vehicle space-time trajectory (paper Fig. 2(d) computational form), with
t1 = TA, t2 = t1 + t_F, t4 = TD:

```
x_f(t) = v_F (t − t1)                  t1 ≤ t < t2
x_f(t) = x_f(t2) + v_Q (t − t2)        t2 ≤ t ≤ t4
```

## 1. Two independent TT computation paths (consistency gate)

- **Agent path (primary truth):** TT_f = TD_f − TA_f from per-agent
  timestamps. The link `waiting_time[]` aggregate is a derived/check
  quantity, never the primary source.
- **Cumulative-curve path:** under FIFO, TT(t) = D⁻¹(A(t)) − t.

Gate (S5a/S5b): `|TT_agent(t) − TT_CA/CD(t)| ≤ 1 simulation interval`.

## 2. Three event clocks (never collapse into one number)

Using ST02a as the example (FFTT = 1 min, minute-grid oracle):

| Clock | T0 | Tpeak | T3 |
| --- | --- | --- | --- |
| entry-rate breakpoints (demand definition) | 30 | 90 | 150 |
| service-point continuous (entry + FFTT) | 31 | — | — |
| sampled minute-grid queue events (what oracle & engine report) | **32** | **91** | **151** |

The expected values asserted by validators are always the **sampled** clock;
the other two are documented so nobody "fixes" a 2-minute discrepancy that is
actually correct.

## 3. Case registry

### ST00_F6_FREEFLOW — free-flow TT/speed + determinism (GREEN 9/9)
1-mile 60-mph link, capacity 3600/h (integer 6 veh/interval), demand 60/h.
Expected: every row TT = 1.0 min, speed = 60 mph; 3 runs byte-identical.
History: RED on the pre-S0 engine (59/60 rows garbage; the only passing row
was t=0 where `vdfps[0]` happened to be legal — the OOB signature); GREEN
after the S0 three-line fix.

### ST02a_step_gold — point-queue analytical (step λ)
λ = 600/1800/600 veh/h over [0,30)/[30,90)/[90,150) min; μ = 1200; N = 2700.

| Quantity | Expected | Basis |
| --- | --- | --- |
| A(30)/A(90)/A(150) | 300 / 2100 / 2700 | ∫λ |
| T0/Tpeak/T3 (sampled) | 32 / 91 / 151 | minute-grid oracle |
| Qmax | 600 veh | (1800−1200) veh/h × 1 h |
| max individual wait | 30 min | Qmax/μ |
| total delay | 600 veh·h | ½·600·2h queue triangle |

### ST02b_quadratic — PAQ-style quadratic pulse
λ(t) = 400 + 1600·max(0, 1−((t−60)/45)²), discretized to 30 × 5-min integer
pieces (oracle solved on the discretized profile — exact for the intended
contract). N = 2602; T0/Tpeak/T3 = 32/91/143; Qmax = 568; delay = 567.48.

### ST02c_cubic — skewed cubic pulse (slow recovery)
λ(t) = 300 + 12000·s²(1−s)·1.9, s = t/150. N = 5503; T0/Tpeak/T3 =
37/146/293 (drain periods auto-appended); Qmax = 2873; delay = 6019.02.

### ST02d_twin_peaks — two-bottleneck-episode profile
Twin quadratic pulses at t = 40 and t = 110. N = 2590; T0/Tpeak/T3 =
27/56/82; Qmax = 224; delay = 172.79. Exercises queue formation–clearance–
re-formation within one horizon.

### ST04a_sqm_paper — paper-exact SQM trajectory case (new)
λ = 600/1500/900 veh/h over 10/8/8 min; μ = 1200; L = 1 mi; v_F = 60;
FD: w = 12 mph, k_j = 180 veh/mi/ln → **v_Q = 15 mph**. N = 420.

| Quantity | Expected | Formula |
| --- | --- | --- |
| Qmax | 40 veh | (1500−1200)·8/60 |
| t_w max | 2.0 min | Qmax/(1200/60) |
| TT max | 3.0 min | FFTT + t_w |
| v̄ min | 20 mph | 60·L/TT |
| **t_Q max** | **2.6667 min** | t_w·v_F/(v_F−v_Q) = 2·60/45 |
| **t_F max** | **0.3333 min** | FFTT − t_w·v_Q/(v_F−v_Q) = 1−2·15/45 |
| **d_Q max** | **0.6667 mi** | v_Q·t_Q |
| free-flow segment | 0.3333 mi | L − d_Q |

Point-queue layer (A/D/Q) validates today; the SQM layer (t_F/t_Q split,
trajectory reconstruction, dual-strip speed) lands with S5a–S5d.

### ST00c_terminal_three_vehicles — agent-level TA/TD micro gate (RED)
1-mile 60-mph link (FFTT = 1.0 min), μ = 600/h = exactly 1 veh/interval,
three vehicles entering interval 0. Gold TT = 1.0 / 1.1 / 1.2 min, total
delay 0.30 min, asserted **per agent from trajectories.csv** — never via the
aggregate waiting table. Gate: `tools/check_agent_timestamps.py`. Current
RED: only 1 of 3 vehicles appears (S0d dedup); the terminal TT stays at FFTT
(S0c-1). Mini-spec: `dev/doc/S0c_terminal_departure_minispec.md`.

### ST02f_knoop_step / ST02g_trapezoid — book-derived point-queue golds (runnable now)
ST02f: Knoop §2.6 uniformly ×0.9 (μ=3600 for exact integer service): oracle
Qmax = 450 veh, TD = 168.75 veh·h — **matches the scaled book values
exactly**. ST02g: May–Keller trapezoidal demand (μ=5400): Qmax = 1600,
TD = 2354.2 veh·h, queue persists ~81 min past the demand peak (book-analog
of TQ_N = 2.53 h). Both red pre-S2 (+18 family), green targets for S2b.

### ST06 / ST07 / ST08 — network node & shockwave battery (prepared for F05)
Generated by `tools/generate_network_cases.py`; each case dir carries a
README with **tiered expectations** (point/spatial-queue characterization
today vs the frozen F05 book truth):
- **ST06 merge (Daganzo, Knoop §11.1.1):** R = 2400, d = 3500/1500, p = 4:1
  → F05 gate q = (1920, 480); invariance: raising d_B must not raise q_B.
  Characterization today (spatial queue): downstream discharges exactly
  2400/h; the split follows the implicit rotation rule (M-1).
- **ST07 diverge (FIFO/CTF, Knoop §11.1.2):** shared 3600, exits 3600/1200,
  f_ramp = 2/3 → F05 gate q = (600, 1200) total 1800. Characterization
  today: ramp pinned at 1200 with growing queue; main alternates 0–1200/h
  (partial FIFO blocking through the shared exit queue — between the
  point-queue 1200 and the FIFO 600, as predicted).
- **ST08 lane-drop chain (8 × 0.25 mi, 3600→1800):** front-tracking via
  per-segment queue-onset times. Verified today: bottleneck discharge
  **exactly 1800/h** while queued (jam-outflow invariant) and KW spillback
  already reaches segment 7 (queue 54 veh). Full front-speed assertions
  freeze at F05 with the FD contract (w = Δq/Δk).

### ST02e / ST10 — μ(t) cases (enabled: false until F07)
ST02e incident (May §12.2.3, 600-multiples): TD = 450·t_R² sweep gate
(exponent 2.00 ± 0.02); ships `capacity_profile.csv` as the F07 input
contract preview. ST10 Webster signal (Elef Ex. 9.2): d₁ = 13.5 s/veh,
delay ∝ red² sweep.

### ST01 / ST03 — profile loading & tandem (declared, disabled)
Await S1/S2 (profile-consuming vehicleization) and S6 (tandem via the frozen
gold G2/G2b cases).

### L0 / L1 — DTALite-S 3-corridor benchmarks (planned)
The legacy DTALite-S 3-corridor package (3600 vehicles, per-agent per-link
TA/TD sequences in `output_agent.csv`) becomes:
- **L0 legacy replay**: reproduce the trajectories the old executable
  actually produced — did OpenDTA lose classical agent-simulation behavior?
  Caveat recorded: the legacy reader keyed on `lane_cap` while the CSV says
  `lane_capacity_in_vhc_per_hour`, so the old run likely used the 1000/h/lane
  default — L0 replays that reality, it does not bless it.
- **L1 corrected physical benchmark**: capacities/lanes/speeds explicitly
  converted to the new contract, checked against analytical truth.
Not analytical gold — mesoscopic trajectory-behavior gold: RMSE(TT), queue
onset, bottleneck discharge, corridor completion time, selected x–t
trajectories, old-vs-new TA/TD scatter. HTML: network map, bottleneck
CA/CD/Q, 100-vehicle x–t fan, link×time TT and speed heatmaps.

## 4. Current red/green board (every red has an owner)

| Observation | Value | Probable owner | Planned step |
| --- | --- | --- | --- |
| ST00 all checks | 9/9 GREEN | — | done (S0) |
| CA vs A_entry (all ST02) | 0.00 after clock alignment | healthy | — |
| Total N (ST02a) | 2700 exact | healthy | — |
| CD offset (ST02a) | +18 veh transient | **minute-batching in setup_agents** (`i/vol·dur` quantized to whole minutes → burst arrivals) + tick ordering | **S2** |
| Q offset / Qmax +18 | 618 vs 600 | same | **S2** |
| Phantom early T0 (sim 2 vs 32) | sampling of burst batches | same | **S2 + clock audit** |
| Delay +40 veh·h | batching + bookkeeping | **S2 first**, re-judge at S5 |
| ST02b N = 2604 vs 2602 | +2 veh | **F-2 ceil inflation** (float error × 30 periods) | **S2** (largest remainder) |
| Speed stays FFS under 600-veh queue | physical inconsistency | **S0c-2: terminal-link waiting accounting** (`update_waiting_time()` only on the transfer branch) | **S0c mini-spec** (oracle-based diagnostic FAILs it meanwhile) |
| Terminal TD never written back to agent | trajectory TT under-reported by the whole queueing delay | **S0c-1**: `set_dep_interval(t)` missing in the `reaches_last_link` branch | **S0c mini-spec** |
| 1 of 3 vehicles in trajectories.csv | audit trail suppressed | **S0d**: `output_trajectories()` dedups by (dep_time, OD) — with minute batching this hides most of the fleet | **S0c mini-spec** |
| Integer capacity +1 (fixed) | 1200/h served at 1800/h | F-3 integer branch | **done (S0b)** |
| link.csv capacity is PER LANE | `get_cap() = cap × lane_num` (supply.h:204); ST06 downstream 2400 was served at 4800 until the case declared per-lane values | **M-11**: units-contract fact (GMNS per-lane vs consensus Q-1 total-per-direction); conversion belongs in the F05/F07 supply adapter; single-lane cases unaffected | document; adapter at F05/F07 |
| Sub-minute FFTT reports TT=0, speed=inf | ST08 0.25-mi segments (FFTT 15 s) | **M-12**: `to_minute()` integer truncation inside `get_travel_time()` reporting | own micro-fix + short-link gate before F05 chain work |

Attribution rule: the +18 family is charged to **S2 loading realization
first**, not "S5 physics" — the oracle is exact for the intended
piecewise-constant contract, and the pre-S2 engine does not yet realize that
contract at 6-sec resolution. No queue-engine changes based on these reds
until S2 lands and the residuals are re-measured.

## 5. Roadmap (frozen order — S0c before everything, S2 split)

```
S0/S0b DONE
S0c-1  terminal actual departure timestamp  (set_dep_interval in terminal branch)
S0c-2  terminal waiting-time accounting     (update_waiting_time; period-index
                                             semantics frozen in the mini-spec)
S0d    trajectory output emits every agent  (drop the dep_time/OD dedup)
       → ST00c green; ST02/ST04 TT & speed panels become non-green (honest)
S1     profile → bins
S2a    ceil → conserved integer vehicles    (fixes ST02b N 2604 vs 2602)
S2b    minute batching → 6-sec deterministic staggering
       → rerun ST02/ST04: the +18 family must disappear
S3     A(t) audit
S4     fractional ServiceDiscretizer
S5a    CA/CD → TT(t) by FIFO inversion D⁻¹(A(t)) − t   (general oracle)
S5b    agent TA/TD → TT(t)  (PRIMARY truth; vs S5a ≤ 1 interval)
S5c    TT → experienced average speed v̄(t)
S5d    SQM (t_F, t_Q, v_Q) + x_f(t) reconstruction     → ST04a full
S6     tandem → L0/L1 3-corridor replay → F05 spatial/spillback
```

**Do-not list while ST00c/ST02/ST04 are red:** no capacity or λ(t) edits, no
tolerance widening, no diagnostic-threshold inflation, no SQM reconstruction,
no spatial queue, no μ(t). The reds are the roadmap, not noise.

**Oracle clock note (constant μ only):** TT(t_e) = FFTT + Q((t_e+FFTT)⁻)/μ —
the queue is sampled at the service point, not at entry; the validator
implements this shift explicitly. The general oracle is the S5a FIFO
inversion, which needs no such formula.

Also planned once S1/S2 land — the **time-contract equivalence gate**: the
same λ(t) expressed as (A) many 5-min demand periods and (B) one period + a
departure profile must produce matching cumulative loading
(A_A(t) ≈ A_B(t) ≤ 1 vehicle).

## 6. Tolerances (tiered, from the frozen rules)

| Class | Tolerance |
| --- | --- |
| conservation (N loaded/discharged) | exact (0 vehicles) |
| cumulative counts at checkpoints | ≤ 1 vehicle |
| event times (sampled clock) | ≤ 1 simulation interval |
| Qmax / delay / VHT aggregates | < 1% (target < 0.1% deterministic) |
| TT dual-path consistency (S5) | ≤ 1 simulation interval |

## 7. Report anatomy (validate_case.py HTML)

Per case: run manifest (commit, exe/case/expected hashes, resolution,
threads, RNG, clock conventions) → check table → Panel A cumulative curves
(A_entry, D; sim vs oracle) → Panel B queue → Panel C flow rates vs μ →
Panel D waiting/travel time (sim vs oracle — the S0c defect is visible here)
→ space-time speed strip (upgrading to dual strips: engine-reported vs
TA/TD-reconstructed, mismatch = FAIL, at S5b) → Panel E x–t trajectory fan
(at S5d).
