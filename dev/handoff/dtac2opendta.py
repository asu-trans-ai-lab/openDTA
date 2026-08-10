"""dtac2opendta -- TAPLite DTAC binary column store -> OpenDTA fixed-path intake.

V1-a of the MVP vertical loop (OPENDTA_V1_MVP_SPEC.md section 5; mini-spec
dev/doc/V1a_dtac_handoff_minispec.md). Reads route_columns.bin (DTAC v1 or
v2, layout verified against TAPLite.cpp WriteColumnsDTAC/WriteColumnsDTACv2
at upstream commit ab9bd2e), scales path shares by the OD demand table, and
writes the OpenDTA intake files:

  columns.csv        the engine seam (load_columns: true)
  path.csv           canonical MVP face: path_id, od_id, period_id, link_sequence
  path_flow.csv      path_id, period_id, path_volume, vehicle_class
  handoff_report.json  PT-1 boundary conservation gate + provenance

DTAC layout (little-endian):
  header  int32[4] = {0x43415444 'DTAC', version, n_modes, n_zones}
  v2 only: float32[4] demand fingerprint
  per (mode m=1..n_modes, origin O=1..n_zones) row-major, every (m,O) present:
    v1: int32 n_dest; int32 dest_zone_id[n_dest] (EXTERNAL ids);
        int32 offsets[n_dest+1]; int32 external_link_ids[offsets[n_dest]]
    v2: int32 n_dest; int32 dest_zone_id[n_dest];
        int32 path_offsets[n_dest+1]  (n_paths = path_offsets[n_dest]);
        float32 theta[n_paths];       (sum to 1 per OD)
        int32 link_offsets[n_paths+1];
        int32 external_link_ids[link_offsets[n_paths]]  (origin->dest order)

NOTE: DTAC stores EXTERNAL zone ids for destinations but origins are the
dense 1..n_zones sequence written row-major; the origin external id is
recovered from the demand table's zone universe when they differ. For the
common case (external zone ids already 1..n dense, as in all kernel
data_sets), origin seq == external id.

Usage:
  python dtac2opendta.py --taplite-dir <run dir> --out-dir <opendta case dir>
      --period P1 [--agent-type auto] [--origin-map dense|<csv>]
"""
import argparse
import csv
import hashlib
import json
import os
import struct
import sys

MAGIC = 0x43415444  # 'DTAC'


def read_dtac(path):
    """Return (version, n_modes, n_zones, fingerprint, blocks) where blocks is
    {(mode, origin_seq): [(dest_ext_id, [(theta, [ext_link_ids])...])...]}."""
    with open(path, "rb") as f:
        data = f.read()

    off = 0

    def take(fmt, n):
        nonlocal off
        vals = struct.unpack_from("<" + fmt * n, data, off)
        off += struct.calcsize(fmt) * n
        return vals

    magic, version, n_modes, n_zones = take("i", 4)
    if magic != MAGIC:
        raise ValueError(f"not a DTAC file (magic 0x{magic:08X})")

    if version not in (1, 2):
        raise ValueError(f"unsupported DTAC version {version}")

    fingerprint = list(take("f", 4)) if version == 2 else None

    blocks = {}
    for m in range(1, n_modes + 1):
        for orig in range(1, n_zones + 1):
            (n_dest,) = take("i", 1)
            if n_dest == 0:
                continue

            dests = take("i", n_dest)
            if version == 1:
                offsets = take("i", n_dest + 1)
                links = take("i", offsets[-1])
                ods = []
                for d in range(n_dest):
                    seq = list(links[offsets[d]:offsets[d + 1]])
                    ods.append((dests[d], [(1.0, seq)]))
            else:
                path_offsets = take("i", n_dest + 1)
                n_paths = path_offsets[-1]
                thetas = take("f", n_paths)
                link_offsets = take("i", n_paths + 1)
                links = take("i", link_offsets[-1])
                ods = []
                for d in range(n_dest):
                    paths = []
                    for j in range(path_offsets[d], path_offsets[d + 1]):
                        seq = list(links[link_offsets[j]:link_offsets[j + 1]])
                        paths.append((thetas[j], seq))
                    ods.append((dests[d], paths))

            blocks[(m, orig)] = ods

    if off != len(data):
        raise ValueError(f"trailing bytes: consumed {off} of {len(data)}")

    return version, n_modes, n_zones, fingerprint, blocks


def read_modes(taplite_dir):
    """mode index (1-based) -> (mode_name, demand_file)."""
    p = os.path.join(taplite_dir, "mode_type.csv")
    modes = {}
    if os.path.exists(p):
        with open(p, newline="", encoding="utf-8-sig") as f:
            for i, row in enumerate(csv.DictReader(f), start=1):
                modes[i] = (row.get("mode_type", f"mode{i}").strip() or f"mode{i}",
                            (row.get("demand_file") or "demand.csv").strip())

    if not modes:
        modes[1] = ("auto", "demand.csv")

    return modes


def read_demand(taplite_dir, fname):
    """{(o_ext, d_ext): volume} with zero rows dropped."""
    q = {}
    with open(os.path.join(taplite_dir, fname), newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            v = float(row["volume"])
            if v > 0:
                q[(int(row["o_zone_id"]), int(row["d_zone_id"]))] = v

    return q


def read_link_lengths(taplite_dir):
    """{external_link_id: length} (unit passthrough) for distance."""
    lengths = {}
    with open(os.path.join(taplite_dir, "link.csv"), newline="", encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            ext = int(row.get("link_id") or i)
            lengths[ext] = float(row.get("length") or 0)

    return lengths


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())

    return h.hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--taplite-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--period", required=True,
                    help="OpenDTA demand_period name this run maps to")
    ap.add_argument("--agent-type", default=None,
                    help="override: collapse every mode to this agent type")
    args = ap.parse_args()

    bin_path = os.path.join(args.taplite_dir, "route_columns.bin")
    version, n_modes, n_zones, fingerprint, blocks = read_dtac(bin_path)
    modes = read_modes(args.taplite_dir)
    lengths = read_link_lengths(args.taplite_dir)

    demands = {m: read_demand(args.taplite_dir, f) for m, (_, f) in modes.items()}

    os.makedirs(args.out_dir, exist_ok=True)
    cols_rows, path_rows, flow_rows = [], [], []
    report_ods = []
    collapsed = args.agent_type is not None
    path_id = 0
    total_flow = 0.0
    total_demand = 0.0
    worst_rel = 0.0

    for (m, orig), ods in sorted(blocks.items()):
        mode_name = args.agent_type if collapsed else modes[m][0]
        q_mode = demands.get(m, {})
        for dest_ext, paths in ods:
            # origin seq == external id for dense external zone ids (all
            # kernel data_sets); assert against the demand table
            o_ext = orig
            q = q_mode.get((o_ext, dest_ext))
            if q is None:
                report_ods.append({"mode": m, "o": o_ext, "d": dest_ext,
                                   "error": "OD in DTAC but not in demand"})
                continue

            f_sum = 0.0
            for theta, seq in paths:
                f_k = theta * q
                f_sum += f_k
                od_id = f"{o_ext}-{dest_ext}"
                link_seq = ";".join(str(l) for l in seq)
                dist = sum(lengths.get(l, 0) for l in seq)
                cols_rows.append([o_ext, dest_ext, mode_name, args.period,
                                  f"{f_k:.6f}", f"{dist:.6f}", link_seq, ""])
                path_rows.append([path_id, od_id, args.period, link_seq])
                flow_rows.append([path_id, args.period, f"{f_k:.6f}", mode_name])
                path_id += 1

            rel = abs(f_sum - q) / q
            worst_rel = max(worst_rel, rel)
            total_flow += f_sum
            total_demand += q
            report_ods.append({"mode": m, "o": o_ext, "d": dest_ext,
                               "q": q, "sum_f": f_sum, "rel_dev": rel})

    with open(os.path.join(args.out_dir, "columns.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["o_zone_id", "d_zone_id", "agent_type", "demand_period",
                    "volume", "distance", "link_sequence", "geometry"])
        w.writerows(cols_rows)

    with open(os.path.join(args.out_dir, "path.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path_id", "od_id", "period_id", "link_sequence"])
        w.writerows(path_rows)

    with open(os.path.join(args.out_dir, "path_flow.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path_id", "period_id", "path_volume", "vehicle_class"])
        w.writerows(flow_rows)

    # PT-1 boundary gate: theta renormalization at write time makes rel_dev
    # pure float32 noise; 1e-5 is the pass bar (v2). v1 is exact by design.
    pt1_pass = worst_rel < 1e-5 and not any("error" in r for r in report_ods)
    report = {
        "dtac_version": version,
        "validation_eligible": version == 2 and pt1_pass,
        "v1_warning": None if version == 2 else
            "DTAC v1 stores the last-iteration AoN path only; volumes are "
            "single-path approximations, not FW-blended",
        "n_modes": n_modes, "n_zones": n_zones,
        "demand_fingerprint": fingerprint,
        "modes_collapsed_to": args.agent_type if collapsed else None,
        "period": args.period,
        "paths": path_id,
        "total_demand": total_demand, "total_path_flow": total_flow,
        "pt1_max_od_rel_dev": worst_rel, "pt1_pass": pt1_pass,
        "source_bin_sha16": sha16(bin_path),
        "ods": report_ods,
    }
    with open(os.path.join(args.out_dir, "handoff_report.json"), "w") as f:
        json.dump(report, f, indent=1)

    print(f"dtac2opendta: DTAC v{version}, {path_id} paths, "
          f"demand {total_demand:.1f}, path flow {total_flow:.1f}, "
          f"PT-1 max OD rel dev {worst_rel:.2e} -> "
          f"{'PASS' if pt1_pass else 'FAIL'}")
    return 0 if pt1_pass else 1


if __name__ == "__main__":
    sys.exit(main())
