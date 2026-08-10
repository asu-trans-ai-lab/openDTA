# TAPLite -> OpenDTA handoff (V1-a of the MVP vertical loop)

**What this is.** OpenDTA accepts a converged TAPLite assignment (the
binary column store `route_columns.bin`) as its FIXED path set, generates
vehicles by departure profile, and runs the dynamic network loading. No
route choice happens in OpenDTA; paths are frozen upstream. This folder is
the complete, self-contained handoff toolchain + its gate.

## User guide (three commands)

```bash
# 1. run TAPLite with the binary column store enabled
#    (settings.csv: column_output=2  -> DTAC v2, theta-share column set)
cd <taplite_run_dir> && DTALite_exe.exe

# 2. convert to OpenDTA intake (writes columns.csv, path.csv,
#    path_flow.csv, handoff_report.json into the OpenDTA case folder)
python dev/handoff/dtac2opendta.py \
    --taplite-dir <taplite_run_dir> --out-dir <opendta_case> --period P1

# 3. run OpenDTA (settings.yml: load_columns: true, column_gen_num: 0,
#    column_opd_num: 0 -> frozen paths; simulation: enable: true)
OpenDTA.exe <opendta_case>/ <output_dir>/
```

Then read: `trajectories.csv` (per-vehicle), `link_performance_dta.csv`
(per-link per-minute CA/CD/queue/speed/TT), `handoff_report.json` (the
PT-1 conservation verdict — if `pt1_pass` is false, STOP: the path flows
do not reproduce the OD table and nothing downstream is trustworthy).

Gate: `python dev/handoff/check_dtac_handoff.py` (H01 four-node, 6 checks:
DTAC write, PT-1, DNL completion, path->link incidence, N accounting,
trajectory completeness). TAPLite exe resolved via `TAPLITE_EXE` env var
or the sibling `../TAPLite4MPO/kernel/build/Release/DTALite_exe.exe`.

## Data schema guide (for AI agents and humans)

### Input: `route_columns.bin` (DTAC, little-endian binary)
| part | layout |
|---|---|
| header | `int32[4] = {0x43415444 'DTAC', version (1 or 2), n_modes, n_zones}` |
| v2 only | `float32[4]` demand fingerprint |
| per (mode 1..n_modes, origin 1..n_zones), row-major, EVERY pair present | one block |
| block v1 | `int32 n_dest; int32 dest_zone_id[n_dest]; int32 offsets[n_dest+1]; int32 external_link_ids[offsets[n_dest]]` |
| block v2 | `int32 n_dest; int32 dest_zone_id[n_dest]; int32 path_offsets[n_dest+1]; float32 theta[n_paths]; int32 link_offsets[n_paths+1]; int32 external_link_ids[...]` |

Notes: destination zone ids are EXTERNAL; origins are the dense 1..n_zones
sequence (external == sequence for dense zone ids). Link ids are EXTERNAL
`link_id` values from TAPLite's link.csv — **the TAPLite link.csv MUST have
a `link_id` column** (absent -> ids are all 0 and the file is unusable).
thetas sum to 1 per OD (renormalized at write). v1 = last-iteration
all-or-nothing path only: accepted with a warning, never validation-
eligible. Path volume: `f_k = theta_k x q_od(mode)` with q from the mode's
demand csv.

### Output 1: `columns.csv` (the OpenDTA engine seam)
```
o_zone_id, d_zone_id, agent_type, demand_period, volume, distance,
link_sequence, geometry
```
- `agent_type` must name an agent_type in the OpenDTA settings.yml
  (modes can be collapsed with --agent-type, disclosed in the report);
- `demand_period` must name a demand_period in settings.yml (--period);
- `link_sequence` = ';'-joined EXTERNAL link ids, origin->destination;
- `volume` real-valued path flow (OpenDTA integerizes by largest
  remainder, S2a); `distance` = sum of link lengths (unit passthrough).

### Output 2/3: canonical MVP pair (record; engine reads columns.csv today)
`path.csv`: `path_id, od_id, period_id, link_sequence`
`path_flow.csv`: `path_id, period_id, path_volume, vehicle_class`

### Output 4: `handoff_report.json`
`dtac_version, validation_eligible, v1_warning, n_modes, n_zones,
demand_fingerprint, modes_collapsed_to, period, paths, total_demand,
total_path_flow, pt1_max_od_rel_dev, pt1_pass, source_bin_sha16, ods[]`
— the PT-1 boundary gate record (per-OD |sum_k f_k - q_od| relative
deviations; bar 1e-5, float32 theta noise).

### OpenDTA case folder requirements
- `settings.yml`: `load_columns: true`, `column_gen_num: 0`,
  `column_opd_num: 0` (frozen paths), `simulation: enable: true`,
  demand_period entries matching --period (+ a CLEAR period so the
  network drains; vehicles still in the network at horizon end are a
  reported condition, not a silent loss);
- `node.csv` / `link.csv`: same external node/link ids as the TAPLite
  network (GMNS style, `link_id` column required);
- csv/yml files must be UTF-8 WITHOUT BOM (a BOM breaks header lookup).

### Fixture: `cases/H01_four_node/`
`taplite/` (4 nodes, 4 links, 7000 veh 1 OD, settings column_output=2) and
`opendta/` (same network GMNS-style, P1 0700-0800 + CLEAR hour, point
queue, 6 s). Frozen expectation: DTAC v2 theta split 78.125% / 21.875% ->
5468.75 / 1531.25 -> S2a integerization 5469 / 1531; DNL completes all
7000 (entered == exited, remaining 0).
