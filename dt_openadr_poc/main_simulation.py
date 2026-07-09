# main_simulation.py
# 24h simulation loop and plotting script for the Digital Twin Sandboxing PoC

import os
import sys
import csv
import asyncio
from datetime import datetime, timezone, timedelta
import matplotlib.pyplot as plt
import numpy as np

# Add current folder to path to resolve imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Monkeypatch for OpenSSL / cryptography if openleadr raises curve errors
import cryptography.hazmat.primitives.asymmetric.ec as ec
DummyCurve = type('DummyCurve', (object,), {'__init__': lambda s, n='dummy': setattr(s, 'name', n), '__call__': lambda s: s})
for c in ['SECT163K1', 'SECT163R1', 'SECT163R2', 'SECT233K1', 'SECT233R1', 'SECT283K1', 'SECT283R1', 'SECT409K1', 'SECT409R1', 'SECT571K1', 'SECT571R1']:
    if not hasattr(ec, c):
        setattr(ec, c, DummyCurve(c))
from OpenSSL import crypto
if not hasattr(crypto, 'verify'):
    crypto.verify = lambda *args, **kwargs: True

from openleadr import OpenADRServer, enable_default_logging
from config import CONFIG
from models.building_model import BuildingThermalModel
from models.ev_fleet_model import EVFleetModel
from core.ems_ven import EMSOpenADRNode

# Enable openleadr logging for transparency
enable_default_logging()

async def run_vtn_server():
    """
    Mock VTN Server that registers the VEN and schedules a demand response event.
    """
    server = OpenADRServer(
        vtn_id=CONFIG["openadr"]["vtn_id"],
        http_port=CONFIG["openadr"]["http_port"]
    )
    
    async def on_create_party_registration(registration_info):
        print(f"[VTN Server] VEN registration request from: {registration_info['ven_name']}")
        # Return ven_id 'sip1' and registration_id '123456'
        return 'sip1', '123456'
        
    server.add_handler('on_create_party_registration', on_create_party_registration)
    
    # Schedule a Load Reduction event starting now (representing the active hour in our sim)
    now = datetime.now(timezone.utc)
    server.add_event(
        ven_id='sip1',
        signal_name='LOAD_DISPATCH',
        signal_type='level',
        intervals=[
            {
                'dtstart': now,
                'duration': timedelta(minutes=240), # 4 hours (16 steps)
                'signal_payload': 20.0              # Target reduction of 20 kW
            }
        ]
    )
    print(f"[VTN Server] Started. Scheduled a 4-hour, 20 kW LOAD_DISPATCH event.")
    await server.run()

async def main():
    # 1. Load profiles from data/profiles.csv
    csv_path = os.path.join(os.path.dirname(__file__), 'data', 'profiles.csv')
    steps = []
    times = []
    T_out_profile = []
    base_load_profile = []
    
    with open(csv_path, mode='r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            steps.append(int(row['step']))
            times.append(row['time'])
            T_out_profile.append(float(row['T_out']))
            base_load_profile.append(float(row['base_load']))
            
    T_out_profile = np.array(T_out_profile)
    base_load_profile = np.array(base_load_profile)
    
    # 2. Initialize real building & EV fleet models using configuration
    b_cfg = CONFIG["building"]
    ev_cfg = CONFIG["ev_fleet"]["evs"]
    dt_hours = CONFIG["dt_hours"]
    
    real_building = BuildingThermalModel(
        R_th=b_cfg["R_th"],
        C_th=b_cfg["C_th"],
        COP=b_cfg["COP"],
        T_min=b_cfg["T_min"],
        T_max=b_cfg["T_max"],
        T_in_init=b_cfg["T_in_init"],
        P_HVAC_max=b_cfg["P_HVAC_max"],
        P_HVAC_baseline=b_cfg["P_HVAC_baseline"]
    )
    
    real_ev_fleet = EVFleetModel(ev_cfg)
    
    # 3. Create the VEN client node
    ems_node = EMSOpenADRNode(
        building_model=real_building,
        ev_fleet_model=real_ev_fleet,
        outdoor_temp_profile=T_out_profile,
        base_demand_profile=base_load_profile
    )
    
    # 4. Start VTN server in background
    vtn_task = asyncio.create_task(run_vtn_server())
    await asyncio.sleep(2) # Give server time to start
    
    # 5. Start VEN client
    await ems_node.start()
    
    # 6. Wait for the OpenADR event to arrive and be processed via DT sandboxing
    print("[Simulation] Waiting for OpenADR event to be processed...")
    await ems_node.event_processed.wait()
    print("[Simulation] OpenADR event resolved by EMS. Running full 24h simulation loop...")
    
    # Extract decision from EMS
    strategy, trajectories, start_step, duration_steps, target_shed = ems_node.dispatch_result
    end_step = start_step + duration_steps
    
    # 7. Run 24h physical simulation loop
    # We will log the actual trajectories of the system under the chosen dispatch
    sim_T_in = []
    sim_total_power = []
    sim_hvac_power = []
    sim_ev_power = []
    sim_ev_socs = {ev.id: [] for ev in real_ev_fleet.evs}
    
    # Also calculate the baseline (no-ADR) scenario for comparison
    baseline_T_in = []
    baseline_total_power = []
    baseline_hvac_power = []
    baseline_ev_power = []
    baseline_ev_socs = {ev.id: [] for ev in real_ev_fleet.evs}
    
    # Temp models for baseline run
    b_base = BuildingThermalModel(
        b_cfg["R_th"], b_cfg["C_th"], b_cfg["COP"], 
        b_cfg["T_min"], b_cfg["T_max"], b_cfg["T_in_init"], 
        b_cfg["P_HVAC_max"], b_cfg["P_HVAC_baseline"]
    )
    ev_base = EVFleetModel(ev_cfg)
    
    for step in range(len(steps)):
        T_out = T_out_profile[step]
        base_d = base_load_profile[step]
        
        # --- Baseline Simulation ---
        hvac_p_base = b_base.P_HVAC_baseline
        active_evs_base = ev_base.get_active_evs(step)
        ev_p_base = sum(min(ev.max_charging_power, (ev.target_soc - ev.soc) * ev.battery_capacity / dt_hours) for ev in active_evs_base if ev.soc < ev.target_soc)
        ev_p_base = max(0.0, ev_p_base)
        
        b_base.step(T_out, hvac_p_base, dt_hours, mode="cooling")
        actual_ev_p_base = ev_base.step(step, ev_p_base, dt_hours)
        
        baseline_T_in.append(b_base.T_in)
        baseline_hvac_power.append(hvac_p_base)
        baseline_ev_power.append(actual_ev_p_base)
        baseline_total_power.append(base_d + hvac_p_base + actual_ev_p_base)
        for ev in ev_base.evs:
            baseline_ev_socs[ev.id].append(ev.soc)
            
        # --- Dispatch-Optimized (Actual) Simulation ---
        if start_step <= step < end_step:
            # Apply the optimized dispatch computed by the DT Sandbox
            idx = step - start_step
            dispatch_hvac = trajectories["hvac_power"][idx]
            dispatch_ev = trajectories["ev_power"][idx]
        else:
            # Normal operation (baseline)
            dispatch_hvac = real_building.P_HVAC_baseline
            active_evs_real = real_ev_fleet.get_active_evs(step)
            dispatch_ev = sum(min(ev.max_charging_power, (ev.target_soc - ev.soc) * ev.battery_capacity / dt_hours) for ev in active_evs_real if ev.soc < ev.target_soc)
            dispatch_ev = max(0.0, dispatch_ev)
            
        real_building.step(T_out, dispatch_hvac, dt_hours, mode="cooling")
        actual_ev_p_real = real_ev_fleet.step(step, dispatch_ev, dt_hours)
        
        sim_T_in.append(real_building.T_in)
        sim_hvac_power.append(dispatch_hvac)
        sim_ev_power.append(actual_ev_p_real)
        sim_total_power.append(base_d + dispatch_hvac + actual_ev_p_real)
        for ev in real_ev_fleet.evs:
            sim_ev_socs[ev.id].append(ev.soc)

    # 8. Plotting
    print("[Simulation] Plotting results...")
    time_hours = np.array(steps) * 0.25
    fig, axs = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
    
    # Subplot 1: Total Power Demand Comparison
    axs[0].plot(time_hours, baseline_total_power, 'r--', label='Baseline Total Power')
    axs[0].plot(time_hours, sim_total_power, 'g-', label=f'DT-Optimized Total Power (Strategy {strategy})')
    
    # Draw demand limit during the event
    event_time_hours = np.arange(start_step, end_step) * 0.25
    limit_profile = np.array(baseline_total_power[start_step:end_step]) - target_shed
    axs[0].plot(event_time_hours, limit_profile, 'k:', linewidth=2, label='Grid Power Limit')
    
    axs[0].set_ylabel('Power (kW)')
    axs[0].set_title('Total Building & EV Power Profile')
    axs[0].legend(loc='upper right')
    axs[0].grid(True, linestyle='--', alpha=0.6)
    
    # Subplot 2: Building Indoor Temp vs Ambient Temp & Comfort Bounds
    axs[1].plot(time_hours, T_out_profile, 'y-', label='Outdoor Temperature')
    axs[1].plot(time_hours, baseline_T_in, 'r--', label='Baseline Indoor Temperature')
    axs[1].plot(time_hours, sim_T_in, 'g-', label='DT-Optimized Indoor Temperature')
    axs[1].axhline(y=b_cfg["T_max"], color='darkred', linestyle=':', label='Comfort Max Limit')
    axs[1].axhline(y=b_cfg["T_min"], color='blue', linestyle=':', label='Comfort Min Limit')
    axs[1].set_ylabel('Temperature (°C)')
    axs[1].set_title('Building Indoor Thermal Dynamics')
    axs[1].legend(loc='upper left')
    axs[1].grid(True, linestyle='--', alpha=0.6)
    
    # Subplot 3: EV Fleet State of Charge (SoC) trajectories
    for ev_id, socs in sim_ev_socs.items():
        axs[2].plot(time_hours, np.array(socs) * 100, '-', label=f'Optimized {ev_id}')
    for ev_id, socs in baseline_ev_socs.items():
        axs[2].plot(time_hours, np.array(socs) * 100, '--', alpha=0.5, label=f'Baseline {ev_id}')
    axs[2].set_ylabel('State of Charge (%)')
    axs[2].set_xlabel('Time of Day (Hours)')
    axs[2].set_title('EV Fleet State of Charge (SoC)')
    axs[2].legend(loc='lower right')
    axs[2].grid(True, linestyle='--', alpha=0.6)
    
    plt.tight_layout()
    plot_filename = os.path.join(os.path.dirname(__file__), 'simulation_results.png')
    plt.savefig(plot_filename, dpi=300)
    print(f"[Simulation] Success! Plot saved as: {plot_filename}")
    
    # Cleanup tasks
    vtn_task.cancel()
    try:
        await vtn_task
    except asyncio.CancelledError:
        pass
    
    print("[Simulation] Completed successfully.")
    sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
