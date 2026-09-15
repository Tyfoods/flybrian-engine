TITLE Public rate.first_order.v1 exact fixed-step update
NEURON {
    POINT_PROCESS FlyBrianFirstOrderRate
    RANGE initial_rate, rate, gain, input_rate, tau
}
PARAMETER { initial_rate = 0 gain = 1 input_rate = 0 tau = 10 }
ASSIGNED { dt rate decay equilibrium }
INITIAL {
    rate = initial_rate
    decay = exp(-dt/tau)
    equilibrium = gain*input_rate
}
BREAKPOINT { SOLVE advance }
PROCEDURE advance() { rate = equilibrium + (rate-equilibrium)*decay }
