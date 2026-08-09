"""OpenDTA master gate runner — one command, every gate, a permanent record.

Runs the complete regression & validation battery in dependency order,
collects PASS/FAIL per gate, and writes a timestamp-free, commit-keyed
record to dev/self_test_simulation/records/gate_run_<sha>.md (tracked in
git — the audit trail the release plan requires; regenerating for the same
commit overwrites the same file, keeping records deterministic).

Usage:
    python tools/run_all_gates.py            # run everything, write record
    python tools/run_all_gates.py --no-record

Exit 0 = every gate PASS, 1 = any FAIL.
"""
import csv
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.abspath(os.path.join(ROOT, "..", ".."))
EXE = os.path.join(REPO, "build", "Release", "OpenDTA.exe")
SELF_TEST_EXE = os.path.join(REPO, "build", "Release", "OpenDTA_self_test.exe")
BASELINE = os.path.join(REPO, "dev", "test", "baseline", "32a3bbf")
GOLD = os.path.join(REPO, "dev", "test", "gold")


def sh(cmd, cwd=None, timeout=1200):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr)


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())

    return h.hexdigest()[:16]


def file_hash_equal(a, b):
    return os.path.exists(a) and os.path.exists(b) and sha16(a) == sha16(b)


results = []  # (gate_id, layer, ok, detail)


def record(gate_id, layer, ok, detail):
    results.append((gate_id, layer, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  [{layer}] {gate_id}: {detail}")


def run_python_gate(gate_id, layer, script, extract=None):
    code, out = sh([sys.executable, os.path.join(HERE, script)], cwd=ROOT)
    tail = out.strip().splitlines()[-1] if out.strip() else ""
    record(gate_id, layer, code == 0, extract(out) if extract else tail)


def main():
    write_record = "--no-record" not in sys.argv
    print("==== OpenDTA master gate run ====")

    # ---- Layer A: engine self-test (C++ harness over production classes)
    code, out = sh([SELF_TEST_EXE, "."], cwd=ROOT)
    tail = next((l for l in out.splitlines() if "checks" in l), "")
    record("ST00_free_flow_determinism", "A", code == 0, tail.strip())

    # ---- Layer B: analytical / physics gates (python oracles, whole engine)
    run_python_gate("ST00c_terminal_agent_timestamps", "B", "check_agent_timestamps.py")
    run_python_gate("S1_departure_bin_demand", "B", "check_bin_demand.py")
    run_python_gate("S2c_profile_loading_and_equivalence", "B", "check_profile_loading.py")
    run_python_gate("S3_cumulative_departure_audit", "B", "check_cumulative_audit.py")

    code, out = sh([sys.executable, os.path.join(HERE, "validate_case.py"), "--all"],
                   cwd=ROOT)
    lines = [l for l in out.splitlines() if ":" in l and ("PASS" in l or "FAIL" in l)]
    record("ST02_ST04_analytical_bank", "B", code == 0,
           "; ".join(l.strip() for l in lines))

    run_python_gate("ST05_spatial_and_kw_receiving", "B", "check_two_link.py")
    run_python_gate("S4_fractional_service", "B", "check_fractional_service.py")

    # ---- Layer B2: contract fixtures (parser semantics, exit-code gates)
    for gate_id, rel, want in (
            ("F02_bad_time_rejected", "dev/test/f02/bad_time", 1),
            ("F02_dup_id_rejected", "dev/test/f02/dup_id", 1),
            ("F03_transims_profile_audit", "dev/test/f03/transims", 0)):
        case = os.path.join(REPO, rel)
        outd = os.path.join(ROOT, "output", "_fixture_" + gate_id)
        os.makedirs(outd, exist_ok=True)
        code, _ = sh([EXE, case + os.sep, outd + os.sep])
        record(gate_id, "B2", code == want, f"exit {code} (expected {want})")

    # ---- Layer C: frozen references
    code, out = sh([sys.executable, os.path.join(GOLD, "tools", "check_gold.py")],
                   cwd=GOLD)
    tail = out.strip().splitlines()[-1] if out.strip() else ""
    record("GOLD_dataset_v2_161_assertions", "C", code == 0, tail)

    # baseline byte-exact regression (UE + sim)
    scratch = os.path.join(ROOT, "output", "_baseline_rerun")
    checks = [
        ("Two_Corridor_default", os.path.join(REPO, "data", "Two_Corridor"),
         ["columns.csv", "link_performance_ue.csv"]),
        ("Two_Corridor_sim_point_queue",
         os.path.join(BASELINE, "Two_Corridor_sim_point_queue", "input"),
         ["columns.csv", "link_performance_ue.csv", "trajectories.csv",
          "link_performance_dta.csv"]),
        ("Two_Corridor_sim_kinematic_wave",
         os.path.join(BASELINE, "Two_Corridor_sim_kinematic_wave", "input"),
         ["trajectories.csv", "link_performance_dta.csv"]),
    ]
    all_ok = True
    details = []
    for name, inp, files in checks:
        outd = os.path.join(scratch, name)
        os.makedirs(outd, exist_ok=True)
        sh([EXE, inp + os.sep, outd + os.sep])
        base = os.path.join(BASELINE, name)
        if not os.path.isdir(os.path.join(base, "output")) and name != "Two_Corridor_default":
            base = os.path.join(base, "output")

        refdir = os.path.join(BASELINE, name, "output")
        if not os.path.isdir(refdir):
            refdir = os.path.join(BASELINE, name)

        bad = [f for f in files if not file_hash_equal(os.path.join(refdir, f),
                                                       os.path.join(outd, f))]
        if bad:
            all_ok = False
            details.append(f"{name}: DIFFERS {bad}")
        else:
            details.append(f"{name}: identical")

    record("BASELINE_byte_exact_regression", "C", all_ok, "; ".join(details))

    # ---- summary + record file
    n_pass = sum(1 for _, _, ok, _ in results if ok)
    verdict = "PASS" if n_pass == len(results) else "FAIL"
    print(f"\n==== {verdict}: {n_pass}/{len(results)} gates ====")

    if write_record:
        code, sha = 0, "unknown"
        try:
            sha = subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True).stdout.strip()
        except Exception:
            pass

        rec_dir = os.path.join(ROOT, "records")
        os.makedirs(rec_dir, exist_ok=True)
        path = os.path.join(rec_dir, f"gate_run_{sha}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Gate run @ {sha}\n\n"
                    f"- executable sha256/16: `{sha16(EXE)}`\n"
                    f"- verdict: **{verdict}** ({n_pass}/{len(results)})\n\n"
                    f"| gate | layer | result | detail |\n|---|---|---|---|\n")
            for gid, layer, ok, detail in results:
                f.write(f"| {gid} | {layer} | {'PASS' if ok else 'FAIL'} | "
                        f"{detail.replace('|', '/')} |\n")

        print(f"record written: {os.path.relpath(path, REPO)}")

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
