# S0c/S0d Mini-Spec — Terminal-link actual departure, waiting accounting, and trajectory dedup

Per rules §15. Branch: continues `feature/simulation-self-test` (or its own
branch after PR #2 review — reviewer's choice). **Blocks S1/S2: no other
feature work until these land.**

## Feature IDs
S0c-1, S0c-2, S0d (three separate minimal diffs, gated by the same micro case)

## Existing behavior (verified at d138a6f)

`run_simulation()` terminal branch ([simulation.cpp:273](../../src/simulation.cpp)):

```cpp
if (agent.reaches_last_link())
{
    link_que.increment_cum_dep(t);
    ++cum_dep;
}
```

1. **S0c-1 — the actual departure timestamp is never written back.** On
   entrance→exit transfer the engine pre-writes the earliest departure
   (`increment_dep_interval(fftt)`); non-terminal links overwrite it with the
   real service time via `set_dep_interval(t)` — the terminal link never
   does. A vehicle with TA=10.0, FFTT=1.0, actual TD=13.0 keeps
   `dep_intvls[0] = 11.0`. Every downstream consumer (trajectory output,
   `get_travel_interval()`, future TT-by-cohort) under-reports terminal-link
   travel time by the whole queueing delay.
2. **S0c-2 — waiting time is never accounted on the terminal link.**
   `update_waiting_time()` is called only on the transfer branch
   ([simulation.cpp:304](../../src/simulation.cpp)) → `waiting_time[]` stays
   zero → `link_performance_dta.csv` reports TT = FFTT and speed = FFS under
   any queue (ST02a: 103 congested minutes, all free-flow green).
3. **S0d — trajectory output dedups by (dep_time, OD)**
   ([utils.cpp:1759](../../src/utils.cpp)): agents sharing origin departure
   minute and OD are silently skipped. With minute-batched departures this
   suppresses most of the fleet (ST00c: 1 of 3 vehicles appears; Two_Corridor:
   7000 vehicles → a handful of rows). The audit trail is structurally
   incomplete.

## Requested behavior

- **S0c-1:** terminal branch records the actual departure:
  `agent.set_dep_interval(t)` before `increment_cum_dep(t)`.
- **S0c-2:** terminal branch accounts waiting time exactly as the transfer
  branch does: `link_que.update_waiting_time(t, agent.get_arr_interval(), <k>)`.
- **S0d:** `output_trajectories()` emits **every** agent (drop the
  dep_time/OD dedup). If output size is a concern for regional runs, gate the
  dedup behind an explicit settings flag defaulting to full output — silent
  suppression is never acceptable for an audit trail.

## Semantic decision to freeze BEFORE coding (do not default silently)

The `<k>` (period index) passed to `update_waiting_time(t, arr, k)`:

| Option | Meaning | Assessment |
| --- | --- | --- |
| current simulation `dp_no` | the period the clock has advanced into | matches the transfer branch today; consistent-by-construction with the loop |
| `agent.get_demand_period_no()` | the vehicle's demand label | violates the F03b rule (demand label must not select supply) |
| period containing the **arrival clock time** | F03b supply-lookup rule | the contract-correct choice once μ(t) arrives |

**Proposal:** use the current simulation `dp_no` now (identical to the
transfer branch — no new semantics introduced by S0c), and record that both
call sites migrate together to arrival-clock lookup when F05/F07 wire μ(t).
The reviewer approves or overrides this row.

Also frozen: `waiting_time[]` becomes a **derived/check quantity**; the
primary TT truth is per-agent `TD − TA` (TEST_CATALOG §1). `get_travel_time()`
remains the aggregated reporter.

## Files to modify
`src/simulation.cpp` (terminal branch: +2 lines), `src/utils.cpp`
(`output_trajectories` dedup removal / flag). Nothing else; queue physics,
loading, UE untouched.

## Gold case & gate (already committed, RED)

`cases/ST00c_terminal_three_vehicles` + `tools/check_agent_timestamps.py`:
1-mile 60-mph link (FFTT = 1.0 min), μ = 600/h = exactly 1 veh/interval,
three vehicles entering interval 0.

| Agent | TA | earliest TD | actual TD | TT (min) | delay |
| --- | --- | --- | --- | --- | --- |
| 1 | 0 | interval 10 | interval 10 | 1.0 | 0 |
| 2 | 0 | interval 10 | interval 11 | 1.1 | 0.1 |
| 3 | 0 | interval 10 | interval 12 | 1.2 | 0.2 |

Current RED: 1 of 3 vehicles visible (S0d); once visible, TT must read
1.0/1.1/1.2 (S0c-1) and total delay 0.30 min. Additional gates: the
oracle-based S0c diagnostic in `validate_case.py` (TT > FFTT whenever oracle
wait > 1 min) must flip ST02a's speed/TT panels from flat-green to honest;
ST00 stays 9/9; all baselines re-frozen only where trajectories/TT legitimately
change (S0c corrects under-reported values — same justification discipline as
S0/S0b re-freezes, documented in the baseline README).

## Explicitly NOT done here
No tolerance widening; no capacity/λ edits; no SQM reconstruction; no spatial
queue; no μ(t); no S2 batching fix (the +18 family stays red until S2a/S2b).

## Expected diff size / risk
Small (~10 lines). Touches the protected simulation kernel — justification:
the gold micro case proves the recorded trajectory contradicts the served
schedule; the fix writes the timestamp the engine already computed.
