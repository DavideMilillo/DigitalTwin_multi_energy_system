"""
verify_article_claims.py
Checks every numerical claim stated in the article draft against
the actual simulation outputs of run_simulation_for_strategy().
"""
import sys, csv, os
sys.path.append('dt_openadr_poc')

from config import CONFIG
from plot_strategy_comparison import run_simulation_for_strategy
from models.building_model import BuildingThermalModel
from models.ev_fleet_model import EVFleetModel
import numpy as np

# ---- Load profiles -----------------------------------------------------------
csv_path = os.path.join('dt_openadr_poc', 'data', 'profiles.csv')
times, T_out_profile, base_load_profile = [], [], []
with open(csv_path, 'r') as f:
    for row in csv.DictReader(f):
        times.append(row['time'])
        T_out_profile.append(float(row['T_out']))
        base_load_profile.append(float(row['base_load']))

# ---- Simulate all strategies -------------------------------------------------
res_A = run_simulation_for_strategy('A', base_load_profile, T_out_profile)
res_B = run_simulation_for_strategy('B', base_load_profile, T_out_profile)
res_C = run_simulation_for_strategy('C', base_load_profile, T_out_profile)

# ---- Baseline EV power (no DR) -----------------------------------------------
b_cfg = CONFIG['building']
ev_cfg = CONFIG['ev_fleet']['evs']
b_base_m = BuildingThermalModel(**b_cfg)
ev_base_m = EVFleetModel(ev_cfg)
baseline_ev_power = []
for step in range(len(times)):
    ev_p = ev_base_m.get_baseline_power(step, 0.25)
    b_base_m.step(T_out_profile[step], b_base_m.P_HVAC_baseline, 0.25, mode='cooling', control_override=False)
    ev_base_m.step(step, ev_p, 0.25, allocation_method='proportional')
    baseline_ev_power.append(ev_p)

print("=" * 70)
print("ARTICLE CLAIM VERIFICATION REPORT")
print("=" * 70)

# ---- STRATEGY A: HVAC cycles normally during event 1 -------------------------
print("\n[1] Strategy A - T_in range during Event 1 (steps 56-63):")
tin_A_e1 = [res_A['T_in'][s] for s in range(56, 64)]
hvac_A_e1 = [res_A['hvac_power'][s] for s in range(56, 64)]
print(f"    T_in min={min(tin_A_e1):.2f} max={max(tin_A_e1):.2f} (Article claims: 22.10-22.71)")
print(f"    HVAC powers: {[round(v,1) for v in hvac_A_e1]}")
print(f"    Article claim OK: {19.5 < min(tin_A_e1) < 24.0 and max(tin_A_e1) < 24.0}")

# ---- STRATEGY B: infeasible, T_in exceeds 24 at steps 62-63 -----------------
print("\n[2] Strategy B - Thermal violation during Event 1:")
tin_B_e1 = [res_B['T_in'][s] for s in range(56, 64)]
max_B = max(tin_B_e1)
violation_steps = [s for s in range(56, 64) if res_B['T_in'][s] > 24.0]
print(f"    Peak T_in={max_B:.3f} at steps {violation_steps} (Article claims: 24.35 at steps 62-63)")
print(f"    Article claim OK: {abs(max_B - 24.35) < 0.05 and 62 in violation_steps and 63 in violation_steps}")

# ---- STRATEGY C: pre-cooling temperature ------------------------------------
print("\n[3] Strategy C - Pre-cooling temperature:")
tin_C_precool = [res_C['T_in'][s] for s in range(52, 56)]
min_C = min(tin_C_precool)
print(f"    Pre-cooling T_in range: {[round(v,2) for v in tin_C_precool]}")
print(f"    Min pre-cool T_in={min_C:.2f} (Article claims: 20.3 degrees -> 'T_min + 0.3')")
print(f"    Note: Article says 'pre-cooled to near T_min+0.3 = 20.3', actual minimum = {min_C:.2f}")

# ---- STRATEGY C: max T_in during Event 1 (must stay below 24) ---------------
tin_C_e1 = [res_C['T_in'][s] for s in range(56, 64)]
print(f"\n[4] Strategy C - T_in during Event 1 (max must < 24):")
print(f"    T_in values: {[round(v,2) for v in tin_C_e1]}")
print(f"    Max T_in={max(tin_C_e1):.3f} (Article claims stays within comfort band)")
print(f"    Article claim OK: {max(tin_C_e1) < 24.0}")

# ---- EV Curtailment energy ---------------------------------------------------
print("\n[5] EV Energy Curtailed during Event 1:")
ev_curtail_A = sum((baseline_ev_power[s] - res_A['ev_power'][s]) * 0.25 for s in range(56, 64))
ev_curtail_C = sum((baseline_ev_power[s] - res_C['ev_power'][s]) * 0.25 for s in range(56, 64))
savings = ev_curtail_A - ev_curtail_C
savings_pct = savings / ev_curtail_A * 100 if ev_curtail_A > 0 else 0
print(f"    Strategy A EV curtailed: {ev_curtail_A:.2f} kWh (Article claims: 40.0 kWh)")
print(f"    Strategy C EV curtailed: {ev_curtail_C:.2f} kWh (Article claims: 28.0 kWh)")
print(f"    Savings A->C: {savings:.2f} kWh = {savings_pct:.1f}% (Article claims: 12.0 kWh, 30%)")

# Check article: "EV curtailment reduced to 14 kW" - this is kW not kWh!
ev_pwr_A_e1 = [res_A['ev_power'][s] for s in range(56, 64)]
ev_pwr_C_e1 = [res_C['ev_power'][s] for s in range(56, 64)]
print(f"    Strategy A EV powers per step: {[round(v,2) for v in ev_pwr_A_e1]}")
print(f"    Strategy C EV powers per step: {[round(v,2) for v in ev_pwr_C_e1]}")
print(f"    Article says 'required EV curtailment to 14.0 kW, total EV energy curtailed to 28.0 kWh'")

# ---- EV SoC at departure for Event 2 ----------------------------------------
print("\n[6] EV SoC at departure before Event 2:")
# EV3 departs at step 80 (20:00) - SoC measured at step 79 (end of step 79)
ev3_soc_A = res_A['ev_socs']['EV3'][79]
ev4_soc_A = res_A['ev_socs']['EV4'][83]
ev3_soc_B = res_B['ev_socs']['EV3'][79]
ev4_soc_B = res_B['ev_socs']['EV4'][83]
ev3_soc_C = res_C['ev_socs']['EV3'][79]
ev4_soc_C = res_C['ev_socs']['EV4'][83]
print(f"    EV3 (target=0.80, departs step 80): A={ev3_soc_A:.3f}, B={ev3_soc_B:.3f}, C={ev3_soc_C:.3f}")
print(f"    EV4 (target=0.90, departs step 84): A={ev4_soc_A:.3f}, B={ev4_soc_B:.3f}, C={ev4_soc_C:.3f}")
print(f"    Article: EV3 SoC=0.58 (all), EV4 SoC=0.47 (A) / 0.55 (C)")

# ---- Event 2 shed verification -----------------------------------------------
print("\n[7] Event 2 Shed Verification (steps 80-83):")
for s in range(80, 84):
    bl = base_load_profile[s]
    hvac_bl = 6.0
    ev_bl = baseline_ev_power[s]
    baseline_tot = bl + hvac_bl + ev_bl
    actual_C = res_C['total_power'][s]
    shed = baseline_tot - actual_C
    print(f"    Step {s} ({times[s]}): baseline={baseline_tot:.2f} kW, actual={actual_C:.2f} kW, shed={shed:.2f} kW (target 15 kW)")
print(f"    Article: baseline=14.0 kW, actual=8.0 kW, shed=6.0 kW, short by 9.0 kW")

# ---- Building parameters confirm model values --------------------------------
print("\n[8] Config parameter verification:")
bcfg = CONFIG['building']
print(f"    R_th={bcfg['R_th']} (Article: 1.5)")
print(f"    C_th={bcfg['C_th']} (Article: 6.0)")
print(f"    COP={bcfg['COP']} (Article: 3.0)")
print(f"    T_min={bcfg['T_min']} (Article: 20.0)")
print(f"    T_max={bcfg['T_max']} (Article: 24.0)")
print(f"    T_in_init={bcfg['T_in_init']} (Article: 22.0)")
print(f"    P_HVAC_max={bcfg['P_HVAC_max']} (Article: 12.0)")
print(f"    P_HVAC_baseline={bcfg['P_HVAC_baseline']} (Article: 6.0)")

evs = CONFIG['ev_fleet']['evs']
print(f"\n[9] EV fleet config verification:")
for ev in evs:
    print(f"    {ev['id']}: E={ev['capacity_kwh']}, P_max={ev['P_max_kw']}, arr={ev['arrival_step']*0.25:.1f}h, dep={ev['departure_step']*0.25:.1f}h, SoC_init={ev['soc_init']}, SoC_tgt={ev['soc_target']}")
print("    Article Table 2: EV1(50kWh,11kW,08:00,18:00,0.30,0.85) EV2(60kWh,22kW,09:00,17:00,0.20,0.90)")
print("                     EV3(40kWh,7.4kW,10:00,20:00,0.40,0.80) EV4(75kWh,22kW,13:00,21:00,0.10,0.90)")

# ---- Temperature profile: outdoor peak and range ----------------------------
print("\n[10] Outdoor temperature profile:")
print(f"    Peak T_out={max(T_out_profile):.1f}C at step {T_out_profile.index(max(T_out_profile))} ({times[T_out_profile.index(max(T_out_profile))]})")
print(f"    Min T_out={min(T_out_profile):.1f}C")
print(f"    T_out at step 60 (15:00)={T_out_profile[60]:.1f}C")
print(f"    Article claims: peak 31.8C at 15:00, min 16.3C at 04:00/midnight")
