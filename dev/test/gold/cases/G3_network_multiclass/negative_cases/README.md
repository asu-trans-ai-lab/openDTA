# Negative cases - a correct loader/engine must FAIL CLOSED on each

## columns_illegal_truck.csv (static infeasibility)
Assigns a P2 truck column to R1, whose link L2 is `auto`-only in P2.
A correct checker/loader rejects this at load time (static allowed-use audit).

## vehicle_truck_boundary_entry.csv (dynamic infeasibility - the I4 trap)
A truck departing 07:59:30 on R1. Statically legal: every R1 link allows trucks
in P1, the truck's DEMAND period. But it reaches L2 at ~08:00, and L2 is
`auto`-only in the P2 SUPPLY period resolved by its arrival clock time.
An engine that checks allowed_uses only at path generation (demand period)
loads this vehicle silently - which is exactly the bug invariant I4 exists to
catch. Expected behavior: rejection at link entry with
`incomplete_reason = route_infeasible_allowed_uses` and `blocked_link = L2`,
never a silent pass and never a crash without diagnostics.
