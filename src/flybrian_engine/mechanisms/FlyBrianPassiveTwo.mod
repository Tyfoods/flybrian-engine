TITLE Public compartmental.passive_two.v1 exact coupled update
NEURON {
    POINT_PROCESS FlyBrianPassiveTwo
    RANGE initial_v_soma, initial_v_dendrite, v_soma, v_dendrite, v_rest
    RANGE capacitance_soma, capacitance_dendrite, coupling_conductance
    RANGE leak_conductance_soma, leak_conductance_dendrite, dendrite_current
}
PARAMETER {
    initial_v_soma = -65 initial_v_dendrite = -65 v_rest = -65
    capacitance_soma = 10 capacitance_dendrite = 10
    coupling_conductance = 0.5
    leak_conductance_soma = 1 leak_conductance_dendrite = 1
    dendrite_current = 0
}
ASSIGNED { dt v_soma v_dendrite eq_soma eq_dendrite e11 e12 e21 e22 }
INITIAL {
    LOCAL a, b, c, d, midpoint, delta, slow, fast, mean_exp, divided_exp, drive, determinant
    v_soma = initial_v_soma
    v_dendrite = initial_v_dendrite
    a = -(leak_conductance_soma+coupling_conductance)/capacitance_soma
    b = coupling_conductance/capacitance_soma
    c = coupling_conductance/capacitance_dendrite
    d = -(leak_conductance_dendrite+coupling_conductance)/capacitance_dendrite
    drive = 1000*dendrite_current/capacitance_dendrite
    determinant = a*d-b*c
    eq_soma = v_rest+b*drive/determinant
    eq_dendrite = v_rest-a*drive/determinant
    midpoint = (a+d)/2
    delta = sqrt((a-d)*(a-d)/4+b*c)
    slow = exp((midpoint+delta)*dt)
    fast = exp((midpoint-delta)*dt)
    mean_exp = (slow+fast)/2
    if (delta == 0) { divided_exp = dt*slow }
    else { divided_exp = (slow-fast)/(2*delta) }
    e11 = mean_exp+(a-midpoint)*divided_exp
    e12 = b*divided_exp
    e21 = c*divided_exp
    e22 = mean_exp+(d-midpoint)*divided_exp
}
BREAKPOINT { SOLVE advance }
PROCEDURE advance() {
    LOCAL soma, dendrite
    soma = v_soma-eq_soma
    dendrite = v_dendrite-eq_dendrite
    v_soma = eq_soma+e11*soma+e12*dendrite
    v_dendrite = eq_dendrite+e21*soma+e22*dendrite
}
