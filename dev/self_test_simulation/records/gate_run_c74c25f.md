# Gate run @ c74c25f

- executable sha256/16: `4c4a3e35879eb1a2`
- verdict: **PASS** (19/19)

| gate | layer | result | detail |
|---|---|---|---|
| ST00_free_flow_determinism | A | PASS | 14 checks, 0 failed: PASS |
| ST00c_terminal_agent_timestamps | B | PASS | PASS (0 failing checks) |
| S1_departure_bin_demand | B | PASS | PASS (0 failing checks) |
| S2c_profile_loading_and_equivalence | B | PASS | PASS (0 failing checks) |
| S3_cumulative_departure_audit | B | PASS | PASS (0 failing checks) |
| ST02_ST04_analytical_bank | B | PASS | ST02a_step_gold: PASS (10/10 checks); ST02b_quadratic: PASS (10/10 checks); ST02c_cubic: PASS (10/10 checks); ST02d_twin_peaks: PASS (10/10 checks); ST02f_knoop_step: PASS (10/10 checks); ST02g_trapezoid: PASS (10/10 checks); ST04a_sqm_paper: PASS (10/10 checks) |
| ST05_spatial_and_kw_receiving | B | PASS | PASS (0 failing checks) |
| S4_fractional_service | B | PASS | PASS (0 failing checks) |
| S5_tt_speed_sqm_chain | B | PASS | PASS (0 failing checks) |
| S6_tandem_gold_G2 | B | PASS | PASS (0 failing checks) |
| F05_node_models | B | PASS | PASS (0 failing checks) |
| V1b_readiness_run_modes | B | PASS | PASS (0 failing checks) |
| V1c_supply_provider_mu_t | B | PASS | PASS (0 failing checks) |
| V1d_required_outputs | B | PASS | PASS (0 failing checks) |
| F02_bad_time_rejected | B2 | PASS | exit 1 (expected 1) |
| F02_dup_id_rejected | B2 | PASS | exit 1 (expected 1) |
| F03_transims_profile_audit | B2 | PASS | exit 0 (expected 0) |
| GOLD_dataset_v2_161_assertions | C | PASS | {"overall_status": "PASS", "metric_count": 161, "pass_count": 161, "fail_count": 0} |
| BASELINE_byte_exact_regression | C | PASS | Two_Corridor_default: identical; Two_Corridor_sim_point_queue: identical; Two_Corridor_sim_kinematic_wave: identical |
