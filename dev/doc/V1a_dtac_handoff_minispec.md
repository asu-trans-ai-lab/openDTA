# V1-a Mini-Spec — TAPLite DTAC binary -> OpenDTA fixed-path intake

Per rules §15 and OPENDTA_V1_MVP_SPEC.md (frozen 2026-08-09). Branch
`feature/v1a-dtac-handoff`. First rung of the MVP vertical loop: OpenDTA
accepts TAPLite's converged path set and runs the DNL on it — no kernel
change, the existing `load_columns` seam carries the whole feature.

## Requested behavior
A converter `dev/handoff/dtac2opendta.py`:

**Inputs**: `route_columns.bin` (DTAC v1 or v2, layout documented in the
MVP spec §5 and verified against TAPLite.cpp WriteColumnsDTAC/v2 at commit
ab9bd2e), the TAPLite run folder's demand csv(s) (o_zone_id, d_zone_id,
volume) and mode_type.csv (mode names), a period name + time_period string,
and the OpenDTA case folder to write into.

**Outputs** (into the OpenDTA case folder):
1. `columns.csv` — the existing OpenDTA seam: o_zone_id, d_zone_id,
   agent_type, demand_period, volume, distance, link_sequence (external
   link ids, ';'-separated), geometry (empty ok). Volume of path k =
   theta_k x q_od (v2) or q_od whole (v1, single path).
   Distance = sum of link lengths (from link.csv of the case).
2. `path.csv` (path_id, od_id, period_id, link_sequence) and
   `path_flow.csv` (path_id, period_id, path_volume, vehicle_class) — the
   canonical MVP faces of the same object.
3. `handoff_report.json` — PT-1 boundary gate: per OD
   |sum_k f_k - q_od| (must be < 1e-6 x q_od for v2; exact for v1),
   totals, path/link counts, DTAC version, demand fingerprint (v2),
   `validation_eligible` (false for v1 single-path), source SHAs.

**Gate (B2-style, red-first)**: `check_dtac_handoff.py` runs TAPLite
(column_output=1) on the 4-node network, converts, asserts PT-1
conservation, then runs OpenDTA on the produced case (load_columns: true)
and asserts: vehicle count == round(sum q_od), per-link DNL volumes
consistent with x_l = sum_k A_lk f_k (free-flow case, +-1 veh), all
agents complete (N_remaining == 0 at horizon end).

## Scope guards
- No OpenDTA C++ change in V1-a. (path.csv/path_flow.csv are written for
  the record; the engine consumes columns.csv until a later feature
  promotes the canonical pair to first-class inputs.)
- v1 DTAC accepted with WARN + validation_eligible=false (AoN parity
  only); v2 is the validated source.
- Vehicle-class collapse: per-mode DTAC blocks map to OpenDTA agent types
  by name; if the case declares only `auto`, modes collapse with a
  declared note in handoff_report.json (pitfall P13 disclosure).

## Files
NEW dev/handoff/dtac2opendta.py, dev/handoff/check_dtac_handoff.py,
dev/handoff/cases/H01_four_node/ (OpenDTA-side settings.yml + node/link/
demand mirroring TAPLite kernel/data_sets/01_4_node_network), this doc.
No kernel files touched.
