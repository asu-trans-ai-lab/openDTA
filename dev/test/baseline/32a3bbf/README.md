# F01 Baseline — frozen reference outputs at commit `32a3bbf`

Regression reference (Gate G10) for the OpenDTA C++ engine **before any DTA-Lite
feature work**. Any future change must reproduce these outputs (subject to the
known-nondeterminism rule below) or explain the difference in its completion
report.

## Provenance

| Item | Value |
| --- | --- |
| Engine commit | `32a3bbf` ("fix Windows and Linux compilation issues", upstream jdlph/OpenDTA main, mirrored to asu-trans-ai-lab main + asu-dta-lite) |
| Toolchain | CMake 4.3.2, Visual Studio 18 2026 (MSVC), x64 Release, OpenMP on, vendored `lib/yaml-cpp.lib` |
| Date | 2026-08-08 |
| Command | `OpenDTA.exe <input_dir> <output_dir>` |

Note: MinGW g++ cannot link the vendored MSVC `yaml-cpp.lib` — build with the
Visual Studio generator (`cmake -G "Visual Studio 18 2026" -A x64`).

## Runs

| Run | Input | Settings | Notes |
| --- | --- | --- | --- |
| `Two_Corridor_default` | `data/Two_Corridor` as-is | UE only (`simulation.enable: false`) | rel. gap 0.00923% |
| `Two_Corridor_sim_kinematic_wave` | copy in `input/` | simulation on, `traffic_flow_model: kinematic_wave` | modified settings.yml stored beside output |
| `Two_Corridor_sim_point_queue` | copy in `input/` | simulation on, `traffic_flow_model: point_queue` | Phase-1 acceptance model |
| `Chicago_Sketch_default` | `data/Chicago_Sketch` as-is | UE only, 4 threads | rel. gap 0.03125% |

## Determinism check (two independent runs, sha256 comparison)

| Output | Result |
| --- | --- |
| UE `columns.csv` (Two_Corridor + Chicago Sketch) | **byte-identical** |
| UE `link_performance_ue.csv` | **byte-identical** |
| DTA `trajectories.csv` (point queue) | **byte-identical** |
| DTA `link_performance_dta.csv` | **NOT byte-identical** — see below |

### F-5/F-6 resolution (waiver expired at S0)

History: the F01 audit observed `travel_time`/`speed` drift on `volume == 0`
rows; F03c regression showed the same drift on `volume > 0` rows (three
same-exe reruns, 5 unstable lines), while every other column stayed
byte-stable. A temporary waiver excluded the two columns from comparison.

Root cause (fixed in S0, feature/simulation-self-test): `get_travel_time()`
passed the simulation interval `i` — not the demand-period index `k` — into
the period-indexed `vdfps` fftt lookup: an out-of-bounds heap read
([supply.h] F-5, the visible F-6 symptom), plus `cum_arr[i + delta]` running
past the horizon end in `get_avg_waiting_time()`. The self-test case
`dev/self_test_simulation` ST00 reproduced the defect RED (59/60 rows wrong,
run 3 drift) and turned GREEN with the fix.

**S0b follow-up (same branch):** the analytical self-test bank
(dev/self_test_simulation ST02 cases) caught `get_flow_cap()` inflating every
whole-number per-interval capacity by one vehicle (F-3 integer branch: a
1200/h link was served at 1800/h). Fixed to serve declared capacity exactly;
`link_performance_dta.csv` references re-frozen once more (Two_Corridor link
3, cap 3000/h, now discharges 50/min instead of the inflated 60/min).
UE outputs and trajectories.csv were byte-unchanged by S0b.

**S0c/S0d re-freeze (approved mini-spec, feature/simulation-self-test):**
the terminal-link branch now records the actual departure
(`set_dep_interval(t)`) and accounts waiting time, and
`output_trajectories()` emits every agent (the (dep_time, OD) dedup silently
suppressed same-minute vehicles — Two_Corridor trajectories grew from 61 to
7001 rows). Both sim variants' `trajectories.csv` and
`link_performance_dta.csv` re-frozen accordingly; UE outputs byte-unchanged;
determinism re-verified (2× byte-identical). Gate evidence: ST00c micro case
(gold per-agent TT 1.0/1.1/1.2 min) RED→GREEN; the oracle-based S0c
diagnostic passes on ST02a (0 of 115 congested minutes report free-flow TT).

**Comparison rule (waiver deleted):** ALL columns of every output file,
including `travel_time` and `speed`, compare **byte-exact**. The
`link_performance_dta.csv` references below were re-frozen with the S0
engine (previous stored values in those two columns were garbage; UE
outputs and trajectories.csv were unaffected by S0 and keep their original
frozen bytes). S0-engine determinism verified: point queue 3×, kinematic
wave 2×, byte-identical.

## File hashes (sha256, first 16 hex chars)

```
61D4680475E7240D  21508084  Chicago_Sketch_default/columns.csv   (NOT committed - regenerate & compare hash)
BB277B8C66F0B879    145096  Chicago_Sketch_default/link_performance_ue.csv
C69F13AC21A1D545       223  Two_Corridor_default/columns.csv
9701BD5B430DB436       280  Two_Corridor_default/link_performance_ue.csv
7A5007EAC248FD49       175  Two_Corridor_sim_kinematic_wave/output/columns.csv
D8F9B047EA85FF21      4400  Two_Corridor_sim_kinematic_wave/output/link_performance_dta.csv  (re-frozen at S0c)
D6328AAA96C77AB6    766068  Two_Corridor_sim_kinematic_wave/output/trajectories.csv          (re-frozen at S0d: all 7000 agents)
1D54E57A8162EC0B       254  Two_Corridor_sim_kinematic_wave/output/link_performance_ue.csv
492CE066581BF70C      6657  Two_Corridor_sim_kinematic_wave/output/trajectories.csv
7A5007EAC248FD49       175  Two_Corridor_sim_point_queue/output/columns.csv
D8F9B047EA85FF21      4400  Two_Corridor_sim_point_queue/output/link_performance_dta.csv     (re-frozen at S0c; identical to KW in this case)
D6328AAA96C77AB6    766068  Two_Corridor_sim_point_queue/output/trajectories.csv             (re-frozen at S0d: all 7000 agents)
1D54E57A8162EC0B       254  Two_Corridor_sim_point_queue/output/link_performance_ue.csv
492CE066581BF70C      6657  Two_Corridor_sim_point_queue/output/trajectories.csv
```

`Chicago_Sketch_default/columns.csv` (21.5 MB) is deliberately not committed;
UE is deterministic, so regenerate with the engine at `32a3bbf` and verify the
hash above.
