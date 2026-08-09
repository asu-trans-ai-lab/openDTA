# Traffic-Flow Theory → OpenDTA Testing Notes

Distilled from five texts in `consensus_datasets/traffic_flow_books/` (read
2026-08-09, one targeted pass per book; section/page citations included so
every claim is human-verifiable):

- **[Seibold]** *A Mathematical Introduction to Traffic Flow Theory* — actually
  Benjamin Seibold's 69-slide IPAM tutorial (2015); cited by slide number.
- **[Elef]** Elefteriadou, *An Introduction to Traffic Flow Theory* (2014).
- **[May]** May, *Traffic Flow Fundamentals* (1990).
- **[Knoop]** Knoop, *Traffic Flow Theory: An Introduction with Exercises*
  (TU Delft Open, 3rd ed. 2020).
- **[T&K]** Treiber & Kesting, *Traffic Flow Dynamics* (2013).

Purpose: mine the books for (a) exact/analytical results usable as simulator
gold tests, (b) invariants for automated gates, (c) design lessons for the
core code. Everything maps onto the existing S-ladder and ST case bank
(`dev/self_test_simulation/TEST_CATALOG.md`).

---

## 1. The books validate the vertical-queue foundation — and its limits

Knoop §2.2 writes the point-queue recursion **exactly as OpenDTA implements
it**: `q_out = min{C·Δt, stack}`, stack += (q_in − q_out)Δt. May Ch. 12 and
Elef Ch. 6 build the same cumulative-curve framework (vertical gap = queue,
horizontal gap = delay, area = total delay) that our ST02 oracle already
uses. Two limits both books state explicitly:

- cumulative-curve delay **ignores spillback** (Knoop §2.3) — spatial effects
  need shockwave theory (their Ch. 4 / Ch. 11);
- a point queue cannot reproduce physical queue-front speeds — Elef Ex. 6.1
  should be kept as a *documented model-limitation test*, not a pass/fail
  gate for the point-queue tier.

**Slanted (oblique) cumulative curves** (Knoop §2.4, q₀ = capacity) are a
cheap, high-signal visualization we should add to the HTML reports: slope
changes reveal capacity changes and capacity drop directly.

## 2. New analytical gold cases with book-exact numbers

| Proposed case | Source | Setup | Frozen expected values |
| --- | --- | --- | --- |
| **ST02e_incident** | May Fig. 12.5/Table 12.2 (pp. 349–350) | λ=4800, μ=6000→μ_R=4000 for t_R, then back | closed forms: t_Q=1.67t_R, Q_M=800t_R, d_M=10t_R min, **TD=666.67·t_R²** → at t_R=0.25/0.5/0.75/1.0 h: TD=42/167/375/667 veh·h. The **quadratic-in-t_R law** itself is a parametric sweep gate (4 runs, fit exponent ≈ 2) |
| **ST02f_knoop_step** | Knoop §2.6 (pp. 16–17) | λ=3600/5000/2000 veh/h (1h/0.5h/…), C=4000 | first delayed vehicle N=3600; Qmax=500 @ t=1.5h; max delay 7.5 min (vehicle 6100); clears t=1.75h; **TD=187.5 veh·h**; mean delay of delayed 3.75 min |
| **ST02g_trapezoid** | May §12.2.4 May–Keller (Fig. 12.7, p. 354) | μ=5500, λ: 3000→6600→3000 (1h ramps, 1h peak) | queue persists **TQ_N=2.53 h** past demand peak; TD from Eq. 12.20 |
| **ST04b_accident_oracle** | T&K Problem 8.5 + solution (pp. 124, 443–447) | l_eff=8m, T=1.5s, V₀=28 m/s, Q_in=3024, one of two lanes closed 30 min | every intermediate printed: Q_max=2016/lane, c_up=−8.77 km/h, reopening front −19.2 km/h, jam dissolves t=3312 s @ x=1936 m, worst travel time **718.1 s**. Full oracle for the spatial/KW tier |
| **ST08_shockwave (KW tier)** | Knoop §4.2–4.3 (Tables 4.1–4.4) | lane drop 3→2 and incident cases | front speeds w_BC=−7.3, w_CA=+8.9; incident w_AB=−4.2, w_BD=−16 km/h — assert queue-front trajectory slopes in x–t output |
| **ST09_moving_bottleneck** | Knoop Ch. 5 (3 worked examples) | truck 10 km/h, d=3000/4500, overtaking 0/1000 | shock between B and downstream state moves **exactly at truck speed**; queue-tail direction flips with demand (−0.96 vs −6.3 km/h) |
| **ST10_signal (needs μ(t)/F07)** | Elef Ex. 9.2 (pp. 198–199); May §12.2.1; T&K 8.5.9.1 | V=800, s=1800, C=60s, g/C=0.5 | uniform delay **13.5 s/veh**; queue clears r·ω_AB/(ω_BC−ω_AB); delay grows with **red² ** (T&K Problem 8.4) — the μ(t) acceptance family |
| **ST11_corridor_gold (F08 era)** | May §8.2 (pp. 232–244) | 3 subsections, 5×15-min slices, 2 ramps, SS2 bottleneck | **TTT=614.5 veh·h**, 26,975 veh-mi, 43.9 mph, mainline delay 75.0 veh·h; with ramp metering: 658.25 / 118.75 / 0 — a complete corridor-level regression target with period-to-period queue carryover (FREQ3 lineage — the structural ancestor of DTALite link-period supply) |

## 3. Merge / diverge: the rules to implement and the traps to test (F05/F06 era)

- **Merge (Daganzo)** — Knoop §11.1.1 three-branch rule with worked numbers
  (d₁=3500, d₂=1500, p=4:1): R=8000→(3500,1500); R=4500→(3500,1000);
  R=2000→**(1600,400)**. T&K 8.38–8.41: when supply binds, split the excess
  **proportional to capacities** (the invariance principle, Lebacque: priorities
  ∝ capacities, never current demands — Knoop §11.2/Tampère requirements).
- **Diverge (FIFO/CTF)** — Knoop §11.1.2 worked numbers: C_main=4000,
  C_ramp=1000, d=3000, exit share 2/3 → Φ=½ → **(500, 1000), total 1500** —
  one blocked exit throttles the through movement too (T&K calls the network
  version "gridlock phenomenon"). **An engine with independent per-link caps
  will wrongly pass 4000 on the main line — this is the sharpest diverge red
  test we can build.**
- **Engine finding (register now):** OpenDTA's node loop serves incoming links
  in rotating order `(t+i)%m` ([simulation.cpp:261]) — that IS an implicit
  merge priority rule (≈ alternating round-robin), undocumented, neither
  capacity-proportional nor demand-proportional. Before F05, freeze a decision:
  keep-and-document vs replace with the Daganzo/proportional rule. Whatever is
  chosen, ST06 (merge numbers above) becomes its gate.
- Empirical context (Elef Ch. 8): merges break down more per added *ramp*
  vehicle than mainline vehicle; active bottleneck ⇒ congested upstream +
  demand-starved free-flow downstream — a cheap corridor-level sanity gate.

## 4. Kinematic-wave tier: exact solutions, invariants, and what error is legitimate

- **Shock speed** w = Δq/Δk (Rankine–Hugoniot) holds in any conservation-law
  model ([Seibold] slide 32, [Knoop] Eq. 4.9, [T&K] Eq. 8.9, [May] Eq. 11.4)
  — the single most model-agnostic front-trajectory gate.
- **Triangular FD ⇒ only two wave speeds** (T&K 8.17–8.20): V₀ forward, c =
  −l_eff/T backward (≈18–20 km/h US). Any interior front moving at another
  speed is a bug. **Jam outflow = Q_max exactly** (no capacity drop in
  first-order models — T&K p. 97 fn. 11).
- **Newell/LTM three-detector principle** (Knoop §10.4.1; T&K §10.8): N(x,t) =
  min(upstream curve translated at V₀, downstream curve translated at c plus
  k_j storage). Link-level, cell-free, **exact for piecewise-linear FD** —
  T&K §8.5.8's section-based model is the same idea and is *exact with zero
  numerical diffusion*. **Recommended F05 architecture**: OpenDTA's
  link-based structure is closer to LTM than to CTM — implementing spillback
  via LTM cumulative-curve bounds keeps the engine exact where CTM would
  smear, and our cumulative-curve oracles apply directly.
- **Discretization legitimacy** ([Seibold] slides 56–59; T&K §8.4, 9.5.6):
  Godunov/CTM error is O(Δx) numerical diffusion — shocks smear over a few
  cells but travel at the right speed and sharpen as Δx→0. CFL for a 6-s step
  at V₀=110 km/h requires cells ≥ ~183 m (T&K 8.27). Tester's rule: *smeared
  but correctly-moving front = discretization; wrong-speed front, growing
  smear, or entropy violation = bug.*
- **Entropy negative test** ([Seibold] slide 33): initialize jam upstream /
  empty downstream; a buggy engine that transports the discontinuity intact
  ("expansion shock") conserves vehicles yet is wrong — correct answer is the
  rarefaction (triangular FD: contact at V₀). Also: LWR obeys a maximum
  principle — spontaneously growing oscillations in a first-order engine are
  a bug, never "instability physics" (slide 35).
- **Node Riemann oracle with numbers** ([Seibold] slide 62): f₁=2ρ(1−ρ/4),
  f₂=4ρ(1−ρ/3), ρ₁=ρ₂=2.5 → interface flux = min(D₁,S₂) = 5/3 — a two-link
  supply/demand unit test independent of any network machinery.

## 5. Stochastic tier (S4 Mode B and beyond): quantitative targets

- **M/M/1** (May Table 12.5): E(m)=ρ²/(1−ρ), E(w)=ρ/[μ(1−ρ)]; worked λ=100,
  μ=150: E(m)=1.4, E(n)=2.0.
- **M/D/1** (May Table 12.6): E(w)=ρ/[2μ(1−ρ)] — **exactly half the M/M/1
  wait**. This is the natural statistical acceptance band for the
  deterministic-service + random-arrival mode of ServiceDiscretizer tests.
- **M/M/N toll plaza gold** (May Table 12.8): λ=800, 2 gates, μ=600: shared
  queue E(w)=4.9 s vs independent queues 12.0 s — a future multi-lane service
  test with a counterintuitive frozen answer.
- **Capacity is a random variable** (Elef Ch. 4): three distinct values —
  max pre-breakdown > breakdown > queue discharge ("two-capacity", drop
  3–18% per Knoop §6.2 empirics). First-order engines cannot reproduce it;
  until a Ring-2 two-capacity/inverse-λ FD feature exists, **assert discharge
  == C** and record the drop as out-of-model. Elef's product-limit breakdown
  curve (Table 4.4) is the calibration target if stochastic capacity ever
  returns (it stays OFF for gold baselines per F03d).
- Elef Ex. 7.1 (GPSS single server, 10-run means with sd's) is a ready-made
  distributional acceptance template: assert means within published sd bands,
  never single-run equality.

## 6. Verification & validation discipline to adopt (Elef Ch. 7; May Ch. 13)

- The **verification → calibration → validation triangle** (May Fig. 13.2):
  calibrate on a subset, validate on hold-out data with **no further
  adjustment**; never adjust field data (Elef p. 150) — the book form of our
  "inputs are never tuned to fit".
- **Replications for stochastic modes**: N ≥ z²s²/e² with s from ~10 pilot
  runs (Elef p. 151; their example needed 15 runs for ±0.25 max-queue).
  Independent random streams per stochastic entity, selectable seeds (May
  p. 384) — matches the legacy per-link LCG design (F03d §2b).
- **Warm-up** ≥ end-to-end traversal time before collecting statistics
  (Elef p. 152). Our drain-period trick is the tail-side twin; an explicit
  warm-up flag belongs in the harness when networks grow.
- **Pitfall to test for explicitly** (Elef p. 146): when demand exceeds entry
  capacity, vehicles queue *outside* the network with no statistics and the
  network falsely looks uncongested. OpenDTA loads arrivals into the first
  link's entrance queue unconditionally — fine today, but the moment an entry
  capacity exists (F05 spillback to origins), an "unserved/outside-network
  vehicles" counter must be a standard output and a conservation gate.
- May's debugging tips (p. 383) are literally our method: deterministic
  inputs first, hand-calculation checks, one subroutine at a time,
  intermediate outputs.

## 7. Core-code implications (registered, not acted on)

| # | Finding | Action window |
| --- | --- | --- |
| M-1 | Node rotation `(t+i)%m` is an undocumented implicit merge rule | **RESOLVED by the DTALite paper (Zhou & Taylor 2014, Cogent Eng., sec. 3.7)**: the authoritative merge model is Daganzo (1994) priority-based allocation with lane-proportional priorities and the mid() operator — cap_out(1) = mid{d1, cap_in − d2, p1·cap_in}, cap_out(2) = mid{d2, cap_in − d1, p2·cap_in}, p_i = nlanes_i/Σnlanes; Fig. 11 point g (not f): an approach demanding less than its priority share yields the leftover to the other. Diverge needs NO special model — agents carry paths, FIFO on the incoming link governs (sec. 3.7.3; openDTA already satisfies this by construction). Origin = loading buffer respecting link-1 inflow capacity (sec. 3.7.1; openDTA loads the entrance queue directly without an inflow check — gap to note for F05). Signals: cap_out = q_sat · g/C (sec. 3.7.4 → ST10/F07). F05 implements Daganzo-mid to replace the rotation; ST06's frozen numbers (cap_in = 2400, lanes 4:1 → 1920/480) are exactly this formula. |
| M-2 | FIFO diverge throttling absent (independent per-link caps) | F05 requirement; ST07 red gate when built |
| M-3 | Spillback architecture: prefer **LTM/section-based** (exact, link-level, zero diffusion) over cell-based CTM | F05 design input |
| M-4 | Jam-outflow=Q_max and two-wave-speed invariants | add to KW-tier gates at F05 |
| M-5 | Capacity drop out-of-model for first-order engine | assert discharge==C now; Ring-2 feature later |
| M-6 | Slanted cumulative curves in HTML reports | cheap validator upgrade, any time |
| M-7 | M/D/1 = half M/M/1 wait as S4 Mode B statistical gate | S4 |
| M-8 | Entropy negative test + maximum principle | KW tier (F05) negative cases |
| M-9 | Outside-network queue counter + conservation | with entry constraints (F05) |
| M-10 | Signal/red-square-law delay family | F07 μ(t) acceptance |
| M-11 | `link.csv capacity` is **per lane** (`get_cap() = cap × lane_num`, supply.h:204) — GMNS convention vs consensus Q-1 (total per direction); caught by ST06 (2-lane link served at 2× declared total) | unit conversion in the F05/F07 supply adapter; every multi-lane case must declare per-lane values |
| M-12 | Sub-minute FFTT truncates to TT=0/speed=inf in reporting (`to_minute()` integer cast in `get_travel_time()`) — caught by ST08's 0.25-mi segments | micro-fix + short-link gate before chain-based front tracking |

**Build status (2026-08-09):** ST02f/ST02g generated and red-gated (oracle
matches the ×0.9-scaled Knoop numbers exactly: Qmax 450, TD 168.75 veh·h);
ST06/ST07/ST08 case dirs shipped with tiered READMEs and first
characterization runs (downstream merge discharge exactly 2400/h; ST08
bottleneck exactly 1800/h with KW spillback already reaching segment 7;
ST07 ramp pinned at 1200 with partial FIFO blocking of the main movement);
ST02e/ST10 ship `capacity_profile.csv` as the F07 contract preview.

**Sequencing note:** nothing here jumps the frozen ladder. ST02e/f/g run on
the current point-queue engine as soon as S2a/S2b land (they are
cumulative-curve cases like ST02a-d); the shockwave/merge/diverge/moving-
bottleneck families are the acceptance batteries for F05; signal for F07;
corridor gold for F08; stochastic targets for S4 Mode B.
