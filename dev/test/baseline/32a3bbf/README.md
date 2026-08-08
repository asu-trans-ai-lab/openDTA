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

### Known nondeterminism (defect F-6 evidence, do not "fix" silently)

`link_performance_dta.csv` differs between reruns in the `travel_time` and
`speed` fields (garbage values, e.g. `travel_time` 0 vs 41130 vs 8738;
`speed` `inf` vs 0.0146) — reads of uninitialized state, live evidence of
audit defects F-6 (waiting-time underflow/OOB) / F-3 family.

**Rule history:** the F01 audit observed drift only on `volume == 0` rows
(one rerun pair). During F03c regression (2026-08-08), three same-exe reruns
showed the same travel_time/speed drift on `volume > 0` rows as well
(5 unstable lines across 3 runs); every other column (volume, waiting_time,
CA, CD, density, queue) is byte-stable across reruns. The rule below reflects
that fuller evidence.

**Regression comparison rule (corrected in F03c):** compare
`link_performance_dta.csv` excluding the `travel_time` and `speed` columns on
**all** rows. All other columns and all other files compare byte-exact
(`trajectories.csv` is fully deterministic and remains the agent-level
regression signal).

## File hashes (sha256, first 16 hex chars)

```
61D4680475E7240D  21508084  Chicago_Sketch_default/columns.csv   (NOT committed - regenerate & compare hash)
BB277B8C66F0B879    145096  Chicago_Sketch_default/link_performance_ue.csv
C69F13AC21A1D545       223  Two_Corridor_default/columns.csv
9701BD5B430DB436       280  Two_Corridor_default/link_performance_ue.csv
7A5007EAC248FD49       175  Two_Corridor_sim_kinematic_wave/output/columns.csv
D39CA49BEA1FFA60      4232  Two_Corridor_sim_kinematic_wave/output/link_performance_dta.csv  (zero-volume rows nondeterministic)
1D54E57A8162EC0B       254  Two_Corridor_sim_kinematic_wave/output/link_performance_ue.csv
492CE066581BF70C      6657  Two_Corridor_sim_kinematic_wave/output/trajectories.csv
7A5007EAC248FD49       175  Two_Corridor_sim_point_queue/output/columns.csv
E9C607F531BC31ED      4225  Two_Corridor_sim_point_queue/output/link_performance_dta.csv     (zero-volume rows nondeterministic)
1D54E57A8162EC0B       254  Two_Corridor_sim_point_queue/output/link_performance_ue.csv
492CE066581BF70C      6657  Two_Corridor_sim_point_queue/output/trajectories.csv
```

`Chicago_Sketch_default/columns.csv` (21.5 MB) is deliberately not committed;
UE is deterministic, so regenerate with the engine at `32a3bbf` and verify the
hash above.
