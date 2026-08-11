# V1-f Mini-Spec — NeXTA exporter and VISUALIZATION_READY

Per OPENDTA_V1_MVP_SPEC.md section 8 and build-order bullet V1-f. The last
step of the v1 vertical loop. Branch `feature/v1f-nexta-export`.

**Scope discipline, verbatim from the spec: "visible in NeXTA, nothing
more."** No new GUI development in v1. This is a file-format exporter, and
`VISUALIZATION_READY = PASS` means exactly one thing: the files parse in
NeXTA and the six interactions below work. It is not a claim about the
quality of the picture.

## What NeXTA needs that we do not yet emit
NeXTA reads the classical DTALite layout. OpenDTA's native outputs are
close but not identical, so the exporter writes a parallel `nexta/`
directory rather than changing any existing file (the frozen baselines
stay byte-identical, as in V1-b through V1-d):

```
nexta/node.csv                  GMNS nodes with x/y
nexta/link.csv                  GMNS links + geometry
nexta/agent.csv                 classical agent layout (id, o/d zone,
                                departure/arrival, path node sequence)
nexta/link_performance.csv      time-dependent link table in the classical
                                column order NeXTA expects
```
`agent.csv` is a re-layout of `trajectories.csv`; `link_performance.csv`
is a re-layout of `link_time_series.csv` (which already carries mu and
spillback_flag from V1-d — the columns that make the queue visible).

## The six acceptance interactions
`VISUALIZATION_READY` flips to PASS only when all six work in NeXTA:
1. vehicles move along their paths over the simulation clock;
2. link colours change by time step;
3. queue lengths render;
4. the bottleneck location is identifiable from the display;
5. clicking a link shows lambda / mu / Q / v for that link;
6. clicking a vehicle shows its trajectory.

Items 5 and 6 are the ones that constrain the schema — they are why the
exporter must carry mu and the per-vehicle time sequence rather than a
summary.

## Readiness integration
Today `VISUALIZATION_READY` reports PASS whenever trajectories and TD link
performance are enabled — a proxy, and an honest one only because nothing
downstream consumed them. Once the exporter exists the status must mean
the export actually ran and produced parsable files:
- exporter ran, all four files written, schema check passed -> **PASS**;
- simulation or trajectory output disabled -> **WARN** (unchanged);
- exporter ran but a schema check failed -> **BLOCKED-VISUALIZATION_SCHEMA**.

Add a root `settings.yml` key `nexta_export: true | false` (default false,
so no existing case changes behaviour or gains files).

## Gate — tools/check_nexta_export.py (21st)
NeXTA itself cannot run in CI, so the gate verifies what is verifiable
without it, and does not overclaim:
- all four files written with the exact expected header order;
- `agent.csv` row count == `trajectories.csv` row count, and every agent's
  node path matches its `path.csv` link sequence resolved to nodes;
- `link_performance.csv` time steps cover the full horizon with no gaps,
  and its volume column reconciles against `link_time_series.csv`;
- coordinates are finite and inside the network bounding box.

**The gate cannot prove the six interactions.** Those need one manual pass
in NeXTA, recorded once in `dev/self_test_simulation/records/` with the
NeXTA version — and that record, not the gate, is what authorises flipping
VISUALIZATION_READY to PASS in the spec's sense. Say this plainly rather
than letting a green gate imply a verified picture.

## Files
`include/handles.h` + a new `src/export_nexta.cpp` (kept out of
`utils.cpp`, which is already large, and out of the protected kernel),
`dev/self_test_simulation/tools/check_nexta_export.py`, runner
registration, `settings.yml` key parsing.

## After V1-f
The v1 vertical loop is closed: read network + fixed paths -> query mu(t)
-> generate vehicles by profile -> fixed-path DNL -> Q(t), v(t), TT(t) ->
trajectory, VMT, VHT, P, v_T2 -> three self-tests green -> viewable.
The spec's next rungs are single period -> two periods -> corridor ->
regional, then parallel — none of which are v1.
