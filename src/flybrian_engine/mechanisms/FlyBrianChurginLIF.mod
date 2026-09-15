TITLE Retained Figure 8 Churgin conductance LIF
NEURON {
    POINT_PROCESS FlyBrianChurginLIF
    RANGE vm, g_ace, g_gab, g_glu, I_ext, spike_out, tau_m, refractory_until
    RANGE v_rest, v_reset, v_threshold, capacitance, refractory
    RANGE e_ace, e_gab, e_glu, tau_ace, tau_gab, tau_glu
    RANGE sampled_vm, sampled_g_ace, sampled_g_gab, sampled_g_glu, sampled_I_ext
}
PARAMETER {
    v_rest = -55
    v_reset = -55
    v_threshold = -40
    capacitance = 72
    tau_m = 21.6
    refractory = 2
    e_ace = 0
    e_gab = -60
    e_glu = -60
    tau_ace = 1.1
    tau_gab = 5.4
    tau_glu = 5
}
ASSIGNED {
    dt
    spike_out
    refractory_until
    I_ext
    active
    sampled_vm
    sampled_g_ace
    sampled_g_gab
    sampled_g_glu
    sampled_I_ext
}
STATE { vm g_ace g_gab g_glu }
INITIAL {
    vm = v_rest
    g_ace = 0
    g_gab = 0
    g_glu = 0
    I_ext = 0
    spike_out = 0
    refractory_until = -1
    sampled_vm = v_rest
    sampled_g_ace = 0
    sampled_g_gab = 0
    sampled_g_glu = 0
    sampled_I_ext = 0
}
BREAKPOINT { SOLVE states METHOD euler }
DERIVATIVE states {
    : Capture the state consumed by Euler, before decay, threshold and reset.
    : Ordinary MANC recordings use this same observation point as Brian2 start.
    sampled_vm = vm
    sampled_g_ace = g_ace
    sampled_g_gab = g_gab
    sampled_g_glu = g_glu
    sampled_I_ext = I_ext
    active = 0
    : Compare fixed-step indices, as Brian2 does for refractory intervals.
    : The rounding guard prevents floating-point drift adding a refractory step.
    if (floor(t/dt + 0.001) >= floor(refractory_until/dt + 0.001)) { active = 1 }
    vm' = active * (-(vm-v_rest)/tau_m + (g_ace*(e_ace-vm)+g_gab*(e_gab-vm)+g_glu*(e_glu-vm)+1000*I_ext)/capacitance)
    g_ace' = -g_ace/tau_ace
    g_gab' = -g_gab/tau_gab
    g_glu' = -g_glu/tau_glu
}
AFTER SOLVE {
    spike_out = 0
    if (floor(t/dt + 0.001) >= floor(refractory_until/dt + 0.001) && vm > v_threshold) {
        vm = v_reset
        refractory_until = t + refractory
        spike_out = 1
    }
}
NET_RECEIVE (ace, gab, glu, current) {
    INITIAL { }
    g_ace = g_ace + ace
    g_gab = g_gab + gab
    g_glu = g_glu + glu
    I_ext = I_ext + current
}
