# ST02e -- incident capacity-reduction case (REQUIRES F07 mu(t))

May sec. 12.2.3 closed forms, adapted to 600-multiples: lambda = 4800,
mu = 6000 dropping to mu_R = 4200 during the incident window t_R
(07:30-08:15 in the shipped profile, t_R = 0.75 h), then back.

Closed-form gold (May Table 12.1 with these numbers):
  t_Q  = t_R (mu - mu_R)/(mu - lambda) = 1.5 t_R
  Q_M  = t_R (lambda - mu_R)           = 600 t_R   veh
  d_M  = 60 t_R (lambda - mu_R)/lambda = 7.5 t_R   min
  TD   = t_R t_Q (lambda - mu_R)/2     = 450 t_R^2 veh-h
Sweep gate at F07: run t_R = 0.25/0.5/0.75/1.0 h -> TD = 28.1/112.5/253.1/450
veh-h; fitting log TD vs log t_R must give exponent 2.00 +/- 0.02 (the
quadratic incident-delay law). Book original (mu_R = 4000): TD = 666.67 t_R^2.

Status: enabled false. The engine has no time-dependent discharge yet;
capacity_profile.csv is the F07 input-contract preview (link_time_profile
layer of the F03b supply stack).
