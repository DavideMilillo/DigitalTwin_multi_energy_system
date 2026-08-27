"""
verify_article_claims.py
Checks every numerical claim stated in the article draft against
the actual simulation outputs of the closed-loop DT Sandboxing PoC.
"""
import sys, csv, os, asyncio
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dt_openadr_poc'))

from config import CONFIG
from models.building_model import BuildingThermalModel
from models.ev_fleet_model import EVFleetModel
from core.dt_sandbox import DigitalTwinSandbox
from core.ems_ven import EMSOpenADRNode
from plot_strategy_comparison import run_simulation_for_strategy
from datetime import datetime, timezone, timedelta
import numpy as np

# ---- Load profiles -----------------------------------------------------------
csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dt_openadr_poc', 'data', 'profiles.csv')
times, T_out_profile, base_load_profile = [], [], []
with open(csv_path, 'r') as f:
    for row in csv.DictReader(f):
        times.append(row['time'])
        T_out_profile.append(float(row['T_out']))
        base_load_profile.append(float(row['base_load']))

T_out_profile = np.array(T_out_profile)
base_load_profile = np.array(base_load_profile)
dt_hours = CONFIG["dt_hours"]

# ---- Closed-Loop Physical Simulation & Online DT Sandboxing -------------------
b_cfg = CONFIG['building']
ev_cfg = CONFIG['ev_fleet']['evs']

real_building = BuildingThermalModel(**b_cfg)
real_ev_fleet = EVFleetModel(ev_cfg)
sandbox = DigitalTwinSandbox()

ems_node = EMSOpenADRNode(
    building_model=real_building,
    ev_fleet_model=real_ev_fleet,
    outdoor_temp_profile=T_out_profile,
    base_demand_profile=base_load_profile
)

now = datetime.now(timezone.utc).replace(hour=14, minute=0, second=0, microsecond=0)
mock_event_1 = {
    'event_descriptor': {'event_id': 'mock-event-1', 'event_status': 'active'},
    'event_signals': [{
        'signal_name': 'LOAD_DISPATCH',
        'signal_type': 'delta',
        'intervals': [{'dtstart': now, 'duration': timedelta(minutes=120), 'signal_payload': 20.0}]
    }]
}

mock_event_2 = {
    'event_descriptor': {'event_id': 'mock-event-2', 'event_status': 'active'},
    'event_signals': [{
        'signal_name': 'LOAD_DISPATCH',
        'signal_type': 'delta',
        'intervals': [{'dtstart': now + timedelta(minutes=360), 'duration': timedelta(minutes=60), 'signal_payload': 15.0}]
    }]
}

# Run step-by-step
e1_sandboxing_results = {}
e2_sandboxing_results = {}

dispatch_hvac_merged = [None] * 96
dispatch_ev_merged = [None] * 96
dispatch_strategy_merged = [None] * 96
dispatch_target_shed_merged = [0.0] * 96
dispatch_start_step_merged = [None] * 96
dispatch_end_step_merged = [None] * 96

sim_T_in = []
sim_total_power = []
sim_hvac_power = []
sim_ev_power = []
sim_ev_socs = {ev.id: [] for ev in real_ev_fleet.evs}

b_base = BuildingThermalModel(**b_cfg)
ev_base = EVFleetModel(ev_cfg)
baseline_T_in = []
baseline_total_power = []
baseline_hvac_power = []
baseline_ev_power = []
baseline_ev_socs = {ev.id: [] for ev in real_ev_fleet.evs}

async def run_online_verification():
    global e1_sandboxing_results, e2_sandboxing_results
    for step in range(96):
        if step == 52: # 13:00 (Event 1 lookahead)
            # Evaluate all 3 strategies for report
            for st in ['A', 'B', 'C']:
                feasi, traj, sc = sandbox.simulate_scenario(
                    real_building, real_ev_fleet, st, 52, 56, 8, 20.0, base_load_profile, T_out_profile, dt_hours
                )
                e1_sandboxing_results[st] = (feasi, traj, sc)

            await ems_node.handle_event(mock_event_1)
            strat, traj, c_step, s_step, dur_steps, t_shed = ems_node.dispatch_results[-1]
            e_step = s_step + dur_steps
            for s in range(c_step, e_step):
                dispatch_hvac_merged[s] = traj["hvac_power"][s - c_step]
                dispatch_ev_merged[s] = traj["ev_power"][s - c_step]
                dispatch_strategy_merged[s] = strat
                dispatch_target_shed_merged[s] = t_shed
                dispatch_start_step_merged[s] = s_step
                dispatch_end_step_merged[s] = e_step

        if step == 76: # 19:00 (Event 2 lookahead)
            # Evaluate all 3 strategies for report from true physical state
            for st in ['A', 'B', 'C']:
                feasi, traj, sc = sandbox.simulate_scenario(
                    real_building, real_ev_fleet, st, 76, 80, 4, 15.0, base_load_profile, T_out_profile, dt_hours
                )
                e2_sandboxing_results[st] = (feasi, traj, sc)

            await ems_node.handle_event(mock_event_2)
            strat, traj, c_step, s_step, dur_steps, t_shed = ems_node.dispatch_results[-1]
            e_step = s_step + dur_steps
            for s in range(c_step, e_step):
                dispatch_hvac_merged[s] = traj["hvac_power"][s - c_step]
                dispatch_ev_merged[s] = traj["ev_power"][s - c_step]
                dispatch_strategy_merged[s] = strat
                dispatch_target_shed_merged[s] = t_shed
                dispatch_start_step_merged[s] = s_step
                dispatch_end_step_merged[s] = e_step

        T_out = T_out_profile[step]
        base_d = base_load_profile[step]

        # Baseline
        hvac_p_base = b_base.P_HVAC_baseline
        ev_p_base = ev_base.get_baseline_power(step, dt_hours)
        b_base.step(T_out, hvac_p_base, dt_hours, mode="cooling")
        actual_ev_p_base = ev_base.step(step, ev_p_base, dt_hours, allocation_method="proportional")

        baseline_T_in.append(b_base.T_in)
        baseline_hvac_power.append(hvac_p_base)
        baseline_ev_power.append(actual_ev_p_base)
        baseline_total_power.append(base_d + hvac_p_base + actual_ev_p_base)
        for ev in ev_base.evs:
            baseline_ev_socs[ev.id].append(ev.soc)

        # Physical
        if dispatch_hvac_merged[step] is not None:
            dhvac = dispatch_hvac_merged[step]
            dev = dispatch_ev_merged[step]
            st = dispatch_strategy_merged[step]
            ts = dispatch_target_shed_merged[step]
            s_st = dispatch_start_step_merged[step]
            e_st = dispatch_end_step_merged[step]
            is_ctrl = True

            if s_st <= step < e_st:
                base_tot_step = base_d + real_building.P_HVAC_baseline + real_ev_fleet.get_baseline_power(step, dt_hours)
                t_lim = max(0.0, base_tot_step - ts)
                curr_unctrl = base_d + dhvac
                if curr_unctrl + dev > t_lim:
                    dev = max(0.0, t_lim - curr_unctrl)

            alloc = "priority_departure" if (st == 'C' or s_st <= step < e_st) else "proportional"
        else:
            dhvac = real_building.P_HVAC_baseline
            dev = real_ev_fleet.get_baseline_power(step, dt_hours)
            is_ctrl = False
            alloc = "proportional"

        real_building.step(T_out, dhvac, dt_hours, mode="cooling", control_override=is_ctrl)
        actual_ev_p = real_ev_fleet.step(step, dev, dt_hours, allocation_method=alloc)

        sim_T_in.append(real_building.T_in)
        sim_hvac_power.append(dhvac)
        sim_ev_power.append(actual_ev_p)
        sim_total_power.append(base_d + dhvac + actual_ev_p)
        for ev in real_ev_fleet.evs:
            sim_ev_socs[ev.id].append(ev.soc)

asyncio.run(run_online_verification())

print("=" * 75)
print("ARTICLE CLAIM VERIFICATION REPORT (CLOSED-LOOP ONLINE POc)")
print("=" * 75)

# ---- EVENT 1 LOOKAHEAD SANDBOX RESULTS ---------------------------------------
print("\n[1] EVENT 1 (14:00-16:00, 20 kW target) - DT Sandboxing at Step 52:")
for st in ['A', 'B', 'C']:
    feasi, traj, sc = e1_sandboxing_results[st]
    t_in_vals = traj['T_in']
    print(f"  Strategy {st}: Feasible={feasi}, Score={sc:.2f}, T_in range=[{min(t_in_vals):.2f}, {max(t_in_vals):.2f}] °C")
    if traj['violation_details']:
        print(f"    Violations: {traj['violation_details']}")

tin_C_precool = e1_sandboxing_results['C'][1]['T_in'][:4]
print(f"  Strategy C pre-cooling T_in values (steps 52-55): {[round(v,2) for v in tin_C_precool]} (min={min(tin_C_precool):.2f} °C)")

# EV Curtailment comparison during Event 1
# Baseline EV power in lookahead window:
ev_base_e1 = [baseline_ev_power[s] for s in range(56, 64)]
curtail_A = sum((ev_base_e1[i] - e1_sandboxing_results['A'][1]['ev_power'][4+i]) * dt_hours for i in range(8))
curtail_C = sum((ev_base_e1[i] - e1_sandboxing_results['C'][1]['ev_power'][4+i]) * dt_hours for i in range(8))
savings = curtail_A - curtail_C
savings_pct = (savings / curtail_A) * 100 if curtail_A > 0 else 0
print(f"  EV Energy Curtailed during Event 1: Strategy A = {curtail_A:.2f} kWh, Strategy C = {curtail_C:.2f} kWh")
print(f"  EV Energy Savings (A -> C): {savings:.2f} kWh ({savings_pct:.1f}%)")

# ---- EVENT 2 LOOKAHEAD SANDBOX RESULTS ---------------------------------------
print("\n[2] EVENT 2 (20:00-21:00, 15 kW target) - DT Sandboxing at Step 76:")
print(f"  Physical state at Step 76 (19:00) under committed Strategy C: T_in={sim_T_in[76]:.2f} °C")
for ev in real_ev_fleet.evs:
    print(f"    {ev.id}: SoC = {sim_ev_socs[ev.id][76]:.3f} (target {ev.target_soc:.2f})")

for st in ['A', 'B', 'C']:
    feasi, traj, sc = e2_sandboxing_results[st]
    print(f"  Strategy {st}: Feasible={feasi}, Score={sc:.2f}, Violations={traj['violation_details']}")

# ---- SHED VERIFICATION ------------------------------------------------------
print("\n[3] PHYSICAL SHED VERIFICATION:")
print("  Event 1 (steps 56-63, 14:00-16:00, target 20 kW):")
for s in range(56, 64):
    bl = baseline_total_power[s]
    act = sim_total_power[s]
    shed = bl - act
    print(f"    Step {s} ({times[s]}): baseline={bl:.2f} kW, actual={act:.2f} kW, shed={shed:.2f} kW")

print("  Event 2 (steps 80-83, 20:00-21:00, target 15 kW):")
for s in range(80, 84):
    bl = baseline_total_power[s]
    act = sim_total_power[s]
    shed = bl - act
    print(f"    Step {s} ({times[s]}): baseline={bl:.2f} kW, actual={act:.2f} kW, shed={shed:.2f} kW (short by {15.0 - shed:.2f} kW)")

# ---- CONFIG & PARAMETER VERIFICATION ----------------------------------------
print("\n[4] SYSTEM PARAMETERS VERIFICATION:")
print(f"  Building: R_th={b_cfg['R_th']}, C_th={b_cfg['C_th']}, COP={b_cfg['COP']}, T_min={b_cfg['T_min']}, T_max={b_cfg['T_max']}, T_in_0={b_cfg['T_in_init']}, P_HVAC_max={b_cfg['P_HVAC_max']}, P_HVAC_base={b_cfg['P_HVAC_baseline']}")
for ev in ev_cfg:
    print(f"  {ev['id']}: Capacity={ev['battery_capacity']} kWh, P_max={ev['max_charging_power']} kW, arr={ev['arrival_step']*0.25:.1f}h ({ev['arrival_step']*15//60:02d}:{ev['arrival_step']*15%60:02d}), dep={ev['departure_step']*0.25:.1f}h ({ev['departure_step']*15//60:02d}:{ev['departure_step']*15%60:02d}), SoC_init={ev['soc_init']}, SoC_target={ev['target_soc']}")

print("=" * 75)
