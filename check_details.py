import sys, os
sys.path.append('dt_openadr_poc')
from config import CONFIG
from plot_strategy_comparison import run_simulation_for_strategy
from models.building_model import BuildingThermalModel
from models.ev_fleet_model import EVFleetModel
import csv
import numpy as np

csv_path = os.path.join('dt_openadr_poc', 'data', 'profiles.csv')
times, T_out_profile, base_load_profile = [], [], []
with open(csv_path) as f:
    for row in csv.DictReader(f):
        times.append(row['time'])
        T_out_profile.append(float(row['T_out']))
        base_load_profile.append(float(row['base_load']))

res_A = run_simulation_for_strategy('A', base_load_profile, T_out_profile)
res_B = run_simulation_for_strategy('B', base_load_profile, T_out_profile)
res_C = run_simulation_for_strategy('C', base_load_profile, T_out_profile)

bcfg = CONFIG['building']
evcfg = CONFIG['ev_fleet']['evs']

b_base_m = BuildingThermalModel(**bcfg)
ev_base_m = EVFleetModel(evcfg)
baseline_ev_power = []
for step in range(len(times)):
    ev_p = ev_base_m.get_baseline_power(step, 0.25)
    b_base_m.step(T_out_profile[step], b_base_m.P_HVAC_baseline, 0.25, mode='cooling', control_override=False)
    ev_base_m.step(step, ev_p, 0.25, allocation_method='proportional')
    baseline_ev_power.append(ev_p)

print('--- EV configs ---')
for ev in evcfg:
    print(ev['id'], 'battery:', ev['battery_capacity'], 'P_max:', ev['max_charging_power'],
          'arr:', ev['arrival_step']*0.25, 'dep:', ev['departure_step']*0.25,
          'SoC_init:', ev['soc_init'], 'SoC_tgt:', ev['target_soc'])

print('\n--- Strategy B T_in steps 56-63 (Event 1 window) ---')
for s in range(56, 64):
    tin = res_B['T_in'][s]
    hvac = res_B['hvac_power'][s]
    print('  step', s, times[s], 'T_in =', round(tin, 3), 'HVAC =', hvac)

print('\n--- Strategy A EV power vs baseline steps 52-64 ---')
for s in range(52, 65):
    bl_tot = base_load_profile[s] + 6.0 + baseline_ev_power[s]
    hvac_a = res_A['hvac_power'][s]
    ev_a = res_A['ev_power'][s]
    total_a = res_A['total_power'][s]
    print('  step', s, times[s], 'bl_total =', round(bl_tot, 2), 'hvac_a =', hvac_a, 'ev_a =', round(ev_a, 2), 'total_a =', round(total_a, 2))

print('\n--- EV SoC at departure (step 79-80 for EV3, step 83-84 for EV4) ---')
for strat, res in [('A', res_A), ('B', res_B), ('C', res_C)]:
    e3_79 = res['ev_socs']['EV3'][79]
    e3_80 = res['ev_socs']['EV3'][80]
    e4_83 = res['ev_socs']['EV4'][83]
    e4_84 = res['ev_socs']['EV4'][84]
    print('  Strategy', strat, '-- EV3 step79:', round(e3_79, 3), 'step80:', round(e3_80, 3),
          '| EV4 step83:', round(e4_83, 3), 'step84:', round(e4_84, 3))

print('\n--- Outdoor temp profile stats ---')
peak_val = max(T_out_profile)
peak_step = T_out_profile.index(peak_val)
min_val = min(T_out_profile)
min_step = T_out_profile.index(min_val)
print('Peak:', peak_val, 'at step', peak_step, times[peak_step])
print('Min:', min_val, 'at step', min_step, times[min_step])
print('T_out step 60 (15:00):', T_out_profile[60])
