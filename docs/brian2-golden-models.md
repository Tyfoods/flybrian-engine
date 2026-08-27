# E3-A Brian2 golden scientific oracle

Status: **frozen oracle for the first public biological adapter**

This document defines the dependency-independent scientific expectations for
`examples/brian2-golden-experiment.json`. It is written before the public adapter and is not
generated from adapter output. The fixture is intentionally embedded and offline: no Janelia,
FlyWire, hosted service, or private FlyBrian module supplies its network.

## Execution identity

- Backend ID: `brian2`
- Supported Brian range for this oracle: `>=2.7,<3`
- Integration time step: `0.1 ms`
- Duration: `100 ms`
- Seed: `6172`
- Integration method for linear state equations: exact/exponential
- Fixed model-definition IDs: `lif.basic.v1`, `rate.first_order.v1`, and
  `compartmental.passive_two.v1`

The adapter must report its exact installed Brian version in the manifest. The engine version,
Brian version, canonical FES hash, seed, and fixture dataset identity together identify an
attempt. This oracle does not assert byte-identical floating-point artifacts across different
Brian releases; it asserts the tolerances below.

## Model equations

All voltage symbols use volts internally, time uses seconds, current uses amperes, resistance
uses ohms, capacitance uses farads, conductance uses siemens, and rate uses hertz. The fixture
expresses scaled units explicitly and the adapter performs dimensional conversion.

### `lif.basic.v1`

For a non-refractory neuron:

```text
dv/dt = (v_rest - v + resistance * external_current) / tau_m
spike when v >= v_threshold
on spike: v = v_reset; hold reset during refractory_period
```

Fixture parameters: `tau_m=20 ms`, `v_rest=-65 mV`, `v_reset=-65 mV`,
`v_threshold=-50 mV`, `resistance=100 Mohm`, `refractory_period=2 ms`, and
`initial_v=-65 mV`. A constant `0.3 nA` current is active for the full attempt.

The continuous-time threshold interval from reset is:

```text
v_inf = v_rest + resistance * current = -35 mV
t_cross = -tau_m * ln((v_threshold - v_inf) / (v_reset - v_inf))
        = 13.8629436112 ms
```

The expected ideal spike sequence is `t_cross + n * (t_cross + 2 ms)` while it remains below
`100 ms`, yielding six spikes. Simulator event scheduling may quantize each event to the
declared step.

### `rate.first_order.v1`

```text
dr/dt = (-r + gain * input_rate) / tau
```

Fixture parameters: `tau=10 ms`, `gain=1`, `initial_rate=0 Hz`, with constant
`input_rate=50 Hz`. Therefore:

```text
r(t) = 50 Hz * (1 - exp(-t / 10 ms))
```

Analytic checkpoints are `31.6060279414 Hz` at `10 ms`, `43.2332358382 Hz` at `20 ms`, and
`49.6631026500 Hz` at `50 ms`.

### `compartmental.passive_two.v1`

Two named compartments, `soma` and `dendrite`, use:

```text
C_s * dv_s/dt = g_leak_s * (v_rest - v_s) + g_couple * (v_d - v_s)
C_d * dv_d/dt = g_leak_d * (v_rest - v_d) + g_couple * (v_s - v_d) + I_d
```

Fixture parameters: `C_s=C_d=10 pF`, `g_leak_s=g_leak_d=1 nS`,
`g_couple=0.5 nS`, `v_rest=-65 mV`, both initial voltages `-65 mV`, and constant dendritic
current `I_d=10 pA`.

Writing `x = v - v_rest` in mV and time in ms gives:

```text
dx/dt = [[-0.15, 0.05], [0.05, -0.15]] x + [0, 1]
x_s(t) = 5(1 - exp(-0.1t)) - 2.5(1 - exp(-0.2t))
x_d(t) = 5(1 - exp(-0.1t)) + 2.5(1 - exp(-0.2t))
```

Expected voltages:

| Time | Soma | Dendrite |
| --- | --- | --- |
| `10 ms` | `-64.0010589978 mV` | `-59.6777354139 mV` |
| `20 ms` | `-63.1308873190 mV` | `-58.2224655134 mV` |
| `50 ms` | `-62.5335762352 mV` | `-57.5338032348 mV` |

The compartmental fixture has no event mechanism and therefore must not advertise or emit
spikes for that model.

## Golden acceptance and tolerance

- Global neuron IDs, model IDs, compartment IDs, units, sample ordering, spike count, and
  artifact disposition are exact.
- LIF spike count is exactly six. The first observed spike must be within `0.11 ms` (one
  `0.1 ms` step plus `0.01 ms` numeric allowance) of the continuous threshold crossing. Each
  subsequent inter-spike interval must be within `0.11 ms` of
  `t_cross + refractory_period`. This interval oracle permits expected phase accumulation when
  every refractory cycle is independently quantized; it does not loosen the per-cycle bound.
- Rate checkpoints allow absolute error `0.0001 Hz` and relative error `0.00001`.
- Compartment voltages allow absolute error `0.0001 mV` and relative error `0.00001`.
- Recorded sample time may differ from the named checkpoint by at most `0.11 ms`; comparison
  uses the nearest emitted sample and does not interpolate silently.
- Repeating on one installed engine/Brian version and seed must produce the same spike/event
  identities and values within the tighter floating-point repeatability bound of absolute
  `1e-12` in artifact base units.

These tolerances are scientific assertions, not performance targets. Runtime performance is
measured after implementation; any later blocking runtime target requires target/soft/hard
bands with a hard limit at least 20% above target.

## Explicit non-claims

This oracle does not establish MANC connectivity, morphology ingestion, private historical
model equivalence, neuron-to-muscle mapping, DigiFly physics, video rendering, local/cloud
equivalence, or all-platform runtime acceptance. It establishes the smallest independently
scrutable biological execution path on which those later extractions can safely build.
