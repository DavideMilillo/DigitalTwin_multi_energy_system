import sys, os, copy
sys.path.append(r'c:\Users\david\Desktop\PhD\progetti\Lazaroiu_special_issue_Digital_twin_energy_system\DigitalTwin_multi_energy_system\dt_openadr_poc')
import csv
from config import CONFIG
from models.building_model import BuildingThermalModel
from models.ev_fleet_model import EVFleetModel
from core.dt_sandbox import DigitalTwinSandbox

csv_path = r'c:\Users\david\Desktop\PhD\progetti\Lazaroiu_special_issue_Digital_twin_energy_system\DigitalTwin_multi_energy_system\dt_openadr_poc\data\profiles.csv'
times, T_out_profile, base_load_profile = [], [], []
with open(csv_path, 'r') as f:
    for row in csv.DictReader(f):
        times.append(row['time'])
        T_out_profile.append(float(row['T_out']))
        base_load_profile.append(float(row['base_load']))

b_cfg = CONFIG['building']
dt_hours = 0.25

# Let's test keeping EV4 = 22 kW (so Event 1 gets exactly 40 kWh vs 28 kWh = 12 kWh / 30% savings)
# And let's see what happens if EV3 and EV4 are configured so Event 2 also has a non-zero penalty:
test_cases = [
    ('EV4 22kW, Capacity 100kWh (arr 13:00, dep 21:00)', [
        {'id': 'EV1', 'arrival_step': 32, 'departure_step': 72, 'battery_capacity': 50.0, 'soc_init': 0.3, 'target_soc': 0.85, 'max_charging_power': 11.0},
        {'id': 'EV2', 'arrival_step': 36, 'departure_step': 68, 'battery_capacity': 60.0, 'soc_init': 0.2, 'target_soc': 0.9, 'max_charging_power': 22.0},
        {'id': 'EV3', 'arrival_step': 40, 'departure_step': 80, 'battery_capacity': 40.0, 'soc_init': 0.4, 'target_soc': 0.8, 'max_charging_power': 7.4},
        {'id': 'EV4', 'arrival_step': 52, 'departure_step': 84, 'battery_capacity': 100.0, 'soc_init': 0.1, 'target_soc': 0.95, 'max_charging_power': 22.0}
    ]),
    ('EV3 arr 13:00, EV4 22kW arr 13:00, cap 75kWh', [
        {'id': 'EV1', 'arrival_step': 32, 'departure_step': 72, 'battery_capacity': 50.0, 'soc_init': 0.3, 'target_soc': 0.85, 'max_charging_power': 11.0},
        {'id': 'EV2', 'arrival_step': 36, 'departure_step': 68, 'battery_capacity': 60.0, 'soc_init': 0.2, 'target_soc': 0.9, 'max_charging_power': 22.0},
        {'id': 'EV3', 'arrival_step': 52, 'departure_step': 80, 'battery_capacity': 40.0, 'soc_init': 0.4, 'target_soc': 0.8, 'max_charging_power': 7.4},
        {'id': 'EV4', 'arrival_step': 52, 'departure_step': 84, 'battery_capacity': 75.0, 'soc_init': 0.1, 'target_soc': 0.9, 'max_charging_power': 22.0}
    ]),
    ('EV4 22kW (Table 2: 75kWh, arr 13:00, dep 21:00)', [
        {'id': 'EV1', 'arrival_step': 32, 'departure_step': 72, 'battery_capacity': 50.0, 'soc_init': 0.3, 'target_soc': 0.85, 'max_charging_power': 11.0},
        {'id': 'EV2', 'arrival_step': 36, 'departure_step': 68, 'battery_capacity': 60.0, 'soc_init': 0.2, 'target_soc': 0.9, 'max_charging_power': 22.0},
        {'id': 'EV3', 'arrival_step': 40, 'departure_step': 80, 'battery_capacity': 40.0, 'soc_init': 0.4, 'target_soc': 0.8, 'max_charging_power': 7.4},
        {'id': 'EV4', 'arrival_step': 52, 'departure_step': 84, 'battery_capacity': 75.0, 'soc_init': 0.1, 'target_soc': 0.9, 'max_charging_power': 22.0}
    ]),
]

for label, evs in test_cases:
    phys_b = BuildingThermalModel(**b_cfg)
    phys_ev = EVFleetModel(evs)
    sandbox = DigitalTwinSandbox()

    for s in range(52):
        phys_b.step(T_out_profile[s], phys_b.P_HVAC_baseline, dt_hours, mode='cooling')
        ev_p = phys_ev.get_baseline_power(s, dt_hours)
        phys_ev.step(s, ev_p, dt_hours, allocation_method='proportional')

    f1_a, t1_a, sc1_a = sandbox.simulate_scenario(phys_b, phys_ev, 'A', 52, 56, 8, 20.0, base_load_profile, T_out_profile, dt_hours)
    f1_b, t1_b, sc1_b = sandbox.simulate_scenario(phys_b, phys_ev, 'B', 52, 56, 8, 20.0, base_load_profile, T_out_profile, dt_hours)
    f1_c, t1_c, sc1_c = sandbox.simulate_scenario(phys_b, phys_ev, 'C', 52, 56, 8, 20.0, base_load_profile, T_out_profile, dt_hours)

    curtail_a = sum((22.0 - t1_a['ev_power'][4+i]) * 0.25 for i in range(8))
    curtail_c = sum((22.0 - t1_c['ev_power'][4+i]) * 0.25 for i in range(8))

    # Advance physical with C
    for s in range(52, 64):
        hvac_disp = t1_c['hvac_power'][s - 52]
        ev_disp = t1_c['ev_power'][s - 52]
        phys_b.step(T_out_profile[s], hvac_disp, dt_hours, mode='cooling', control_override=True)
        phys_ev.step(s, ev_disp, dt_hours, allocation_method='priority_departure')
    for s in range(64, 76):
        phys_b.step(T_out_profile[s], phys_b.P_HVAC_baseline, dt_hours, mode='cooling')
        ev_p = phys_ev.get_baseline_power(s, dt_hours)
        phys_ev.step(s, ev_p, dt_hours, allocation_method='proportional')

    f2_a, t2_a, sc2_a = sandbox.simulate_scenario(phys_b, phys_ev, 'A', 76, 80, 4, 15.0, base_load_profile, T_out_profile, dt_hours)
    f2_b, t2_b, sc2_b = sandbox.simulate_scenario(phys_b, phys_ev, 'B', 76, 80, 4, 15.0, base_load_profile, T_out_profile, dt_hours)
    f2_c, t2_c, sc2_c = sandbox.simulate_scenario(phys_b, phys_ev, 'C', 76, 80, 4, 15.0, base_load_profile, T_out_profile, dt_hours)

    print(f'=== {label} ===')
    print(f'  Event 1: Strat A feasible={f1_a}, Strat B feasible={f1_b} (score={sc1_b:.2f}), Strat C feasible={f1_c}')
    print(f'  Event 1 Curtail: A={curtail_a:.2f} kWh, C={curtail_c:.2f} kWh, Savings={curtail_a-curtail_c:.2f} kWh ({(curtail_a-curtail_c)/curtail_a*100:.1f}%)')
    soc_strs = [f"{ev.id}:{ev.soc:.2f}" for ev in phys_ev.evs]
    print(f'  Physical SoCs at 19:00: {soc_strs}')
    print(f'  Event 2: Strat A score={sc2_a:.2f}, Strat B score={sc2_b:.2f}, Strat C score={sc2_c:.2f}')
    print(f'  Event 2 Strat A violations: {t2_a["violation_details"]}')
    print(f'  Event 2 Strat C violations: {t2_c["violation_details"]}')
    print()
