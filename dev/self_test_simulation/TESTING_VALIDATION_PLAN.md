# OpenDTA Testing & Validation Plan

The consolidated, permanent record of every gate protecting the simulation
engine, and the policy for running them. One command runs everything and
writes a commit-keyed record:

```bash
cd dev/self_test_simulation
python tools/run_all_gates.py        # -> records/gate_run_<sha>.md (tracked)
```

Or through the build system (registers the same battery as ctest targets):

```bash
cmake -S . -B build -G "Visual Studio 18 2026" -A x64 -DSELF_TEST=ON
cmake --build build --config Release
ctest --test-dir build -C Release    # runs opendta_self_test + opendta_gates
```

Principle (unchanged since TST0): analytical truth → small case →
production engine → numerical comparison → human visualization. Engine
output is never frozen into gold; every red must carry a diagnosed owner.

## Gate registry (12 gates, 3 layers)

| Gate ID | Layer | Tool | Proves | Tolerance |
|---|---|---|---|---|
| ST00_free_flow_determinism | A (C++ harness) | `OpenDTA_self_test.exe` | free-flow TT/speed exact; 3× byte-identical reruns; F-5/F-6 stay dead | exact / byte |
| ST00c_terminal_agent_timestamps | B | `check_agent_timestamps.py` | per-agent TD−TA ladder (30 veh, 1/interval service); S0c/S0d stay dead; S2b staggering | 0.01 min |
| S1_departure_bin_demand | B | `check_bin_demand.py` | D_k = D·p̃_k projection; conservation | 1e-9 |
| S2c_profile_loading_and_equivalence | B | `check_profile_loading.py` | inverse-CDF loading tracks n·F(t); **period-pieces ≡ profile representation** | ≤1 veh |
| S3_cumulative_departure_audit | B | `check_cumulative_audit.py` | engine's own A_sim vs n·F(t) artifact, all cohorts | ≤1 veh, finals exact |
| ST02_ST04_analytical_bank | B | `validate_case.py --all` | 7 cases × 10 checks vs exact 6-s-grid oracle: conservation, CA/CD/Q curves, T0/T3 events, Qmax, delay, S0c diagnostic | exact / ≤1 veh / ≤1 min / 1% |
| ST05_spatial_and_kw_receiving | B | `check_two_link.py` | SQ occupancy cap & spillback; KW backwave reservation (LTM); cross-model ordering | ≤2 veh strict |
| F02_bad_time_rejected | B2 | exit-code fixture | malformed time_period is a named hard error | exit 1 |
| F02_dup_id_rejected | B2 | exit-code fixture | duplicate period_id rejected | exit 1 |
| F03_transims_profile_audit | B2 | exit-code fixture | G5 audit reproduces approved S_r values on real TRANSIMS profiles | exit 0 |
| GOLD_dataset_v2_161_assertions | C | `dev/test/gold/tools/check_gold.py` | the frozen 5-case / 161-assertion contract suite | frozen |
| BASELINE_byte_exact_regression | C | hash compare vs `dev/test/baseline/32a3bbf` | UE + sim outputs byte-identical to the frozen references (all columns — no waivers) | byte |

Per-case HTML reports with run manifests: `validate_case.py` →
`reports/<case>.html` (regenerable, untracked). The theory/expectation
catalog: `TEST_CATALOG.md` + `test_catalog.html`.

## Records policy

- `records/gate_run_<sha>.md` is **tracked in git** — one file per commit
  actually gated, overwritten deterministically on re-run at the same sha.
  It carries the executable hash, verdict, and the per-gate detail line.
- A kernel-touching PR is mergeable only with a green record at its head
  commit. Baseline re-freezes must be justified in
  `dev/test/baseline/32a3bbf/README.md` in the same commit (S0/S0b/S0c/S2b
  precedent).
- Waivers are temporary by construction (F-6 precedent: waiver text must
  name the defect and its expiry condition; deleted at the fix).

## Release policy (three tiers, from the S0c-era agreement)

1. **Fast PR gate** — `run_all_gates.py` (≈ minutes). Blocks merge.
2. **Sanitizer gate** — for `simulation.cpp`/`supply.h` PRs additionally
   build with `/fsanitize=address` and rerun layer A+B
   (heap-buffer-overflow = 0; the F-5 OOB class stays dead).
3. **Release gate** — from a clean directory, the shipped binary runs the
   bundled tiny fixtures: `opendta --self-test simulation` (planned CLI;
   today: `OpenDTA_self_test.exe <root>`), proving the *delivered* binary
   passes physics gold, not just the source tree.

## Growth map (where the next steps' gates plug in)

| Upcoming step | New/activated gates |
|---|---|
| S4 ServiceDiscretizer | Mode-B unit gate: frozen first-20 LCG sequence (yml §service-discretizer), mean→c, no starvation, accumulator-oracle cross-check; integer-capacity byte-invariance |
| S5a–d TT/speed/SQM | dual-path TT consistency (agent vs D⁻¹(A(t)) ≤ 1 interval); dual speed strips (reported vs reconstructed, mismatch = FAIL); ST04a SQM layer (t_Q 2.6667 / t_F 0.3333 / d_Q 0.6667) |
| S6 tandem | ST03 via frozen gold G2/G2b (CD₁==CQ₂ ≤1 veh, boundary continuity) |
| F05 nodes | ST06 Daganzo-mid (1920/480), ST07 diverge-FIFO, ST08 lane-drop chain; M-13 supply-contract migration precondition |
| F06 PCE/allowed-use | PCE gold (truck=2 explicit accounting), illegal-trajectory count = 0, gold I4 dynamic negative goes live |
| F07 μ(t) | ST02e incident (TD = 450·t_R² sweep), ST10 Webster signal (d₁ = 13.5 s/veh) |
| F08 outputs | output-schema gold + VMT/VHT re-derivation from trajectories |
| P01–P03 parallel | thread_invariance {1,2,4,8}: CA/CD/Q/N/trajectories identical to serial gold (blocking) |
| L0/L1 3-corridor | legacy trajectory replay (RMSE(TT), onset, discharge) / corrected benchmark |
