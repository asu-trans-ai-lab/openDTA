# V1-b Mini-Spec — nine READY statuses + Smoke/Validation run modes

Per OPENDTA_V1_MVP_SPEC.md sections 1 and 3. Branch `feature/v1b-readiness`.

## Requested behavior
Before any computation (after input loading, before find_ue) every run
prints the nine readiness statuses, each PASS | PASS_WITH_DEFAULT | WARN |
BLOCKED, and writes `readiness_report.json` to the output folder:

NETWORK / SUPPLY_MU / PATH_COLUMN / PATH_FLOW / DEPARTURE_PROFILE /
VEHICLE_GENERATION / DNL_LOADING / RESULT_OUTPUT / VISUALIZATION

Any BLOCKED aborts the run (nonzero exit) AFTER all nine are printed, so
the user sees where they stand without reading configuration.

`settings.yml` gains optional root key `run_mode: smoke | validation`
(default smoke). v1-b rules:

| status | smoke | validation |
|---|---|---|
| NETWORK | PASS / BLOCKED-NETWORK_EMPTY | same |
| SUPPLY_MU | PASS_WITH_DEFAULT (constant mu from link capacity) | BLOCKED-MU_T_NOT_VALIDATED (until SupplyProvider/SLC, V1-c) |
| PATH_COLUMN | PASS (frozen, load_columns) / PASS_WITH_DEFAULT (generated in-run) / BLOCKED-PATH_COLUMNS_EMPTY | generated-in-run -> BLOCKED-PATH_NOT_FROZEN |
| PATH_FLOW | PASS / BLOCKED-NO_DEMAND | same |
| DEPARTURE_PROFILE | PASS (F03c binding) / PASS_WITH_DEFAULT (uniform S2b) | unbound -> BLOCKED-PROFILE_SOURCE_MISSING |
| VEHICLE_GENERATION | PASS (mirrors PATH_FLOW + periods) | same |
| DNL_LOADING | PASS / WARN (simulation disabled) | same |
| RESULT_OUTPUT | PASS / WARN (outputs disabled) | same |
| VISUALIZATION | PASS (trajectory + TD link outputs on) / WARN | same |

`readiness_report.json`: run_mode, per-status {status, note}, blocked[],
used_default_mu, used_default_profile, validation_eligible
(= validation mode, zero BLOCKED, zero defaults - structurally false in
v1-b, honest until V1-c).

## Gate (red-first) — tools/check_readiness.py, 17th battery gate
1. ST00 case (smoke default): exit 0; stdout carries all nine names;
   SUPPLY_MU and DEPARTURE_PROFILE report PASS_WITH_DEFAULT;
   readiness_report.json written, validation_eligible false.
2. Fixture dev/test/v1b/validation_blocked (ST00 copy + run_mode:
   validation): exit nonzero; stdout carries BLOCKED-MU_T_NOT_VALIDATED
   and BLOCKED-PROFILE_SOURCE_MISSING; all nine still printed.

## Files
include/global.h (RunMode enum), include/handles.h (member + decl),
src/utils.cpp (run_mode parse + report_readiness impl), src/main.cpp (one
call), NEW tools/check_readiness.py, NEW dev/test/v1b/validation_blocked/,
runner registration. Protected kernel untouched (simulation.cpp untouched);
full battery must stay green and baselines byte-identical (readiness adds
stdout lines + a new output file only - baseline comparisons hash specific
csvs, unaffected).
