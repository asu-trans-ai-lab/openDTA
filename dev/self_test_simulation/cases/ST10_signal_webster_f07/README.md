# ST10 -- Webster signal delay case (REQUIRES F07 mu(t))

Elefteriadou Ex. 9.2 / May 12.2.1 / Treiber 8.5.9.1: V = 800 veh/h,
saturation flow S = 1800, C = 60 s, g/C = 0.5 -> capacity 900 veh/h,
v/c = 0.89.

Gold (frozen):
  uniform delay d1 = 0.5 C (1-g/C)^2 / (1 - V/S) = 13.5 s/veh
  per-cycle: Q_M = lambda r = 6.67 veh; t_Q = s r /(s-lambda) = 54 s < g (OK)
  total delay per red grows with r^2 (Treiber Problem 8.4) - a red-duration
  sweep (r = 20/30/40 s at fixed lambda) must fit exponent 2.
  Non-oversaturation condition: V <= C_link * g/C (Treiber 8.49).

Status: enabled false until F07; capacity_profile.csv sketches the red/green
discharge representation.
