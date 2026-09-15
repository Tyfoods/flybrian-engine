TITLE Public lif.basic.v1 exact fixed-step update
NEURON {
    POINT_PROCESS FlyBrianBasicLIF
    RANGE initial_v, vm, v_rest, v_reset, v_threshold, tau_m, resistance
    RANGE refractory_period, external_current, spike_out
}
PARAMETER {
    initial_v = -65
    v_rest = -65
    v_reset = -65
    v_threshold = -50
    tau_m = 20
    resistance = 100
    refractory_period = 2
    external_current = 0
}
ASSIGNED { dt vm spike_out tick next_active decay equilibrium }
INITIAL {
    vm = initial_v
    spike_out = 0
    tick = 0
    next_active = 0
    decay = exp(-dt/tau_m)
    equilibrium = v_rest + resistance*external_current
}
BREAKPOINT { SOLVE advance }
PROCEDURE advance() {
    spike_out = 0
    if (tick >= next_active) {
        vm = equilibrium + (vm-equilibrium)*decay
        if (vm >= v_threshold) {
            vm = v_reset
            spike_out = 1
            next_active = tick + floor(refractory_period/dt + 0.001)
        }
    }
    tick = tick + 1
}
