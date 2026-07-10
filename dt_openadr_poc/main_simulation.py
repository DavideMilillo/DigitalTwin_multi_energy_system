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
    now = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
    server.add_event(
        ven_id='sip1',
        signal_name='LOAD_DISPATCH',
        signal_type='delta', # More realistic standard for load reduction
        intervals=[
            {
                'dtstart': now,
                'duration': timedelta(minutes=15),  # 15 min ramp-up
                'signal_payload': 10.0              # Target reduction of 10 kW (ramp up)
            },
            {
                'dtstart': now + timedelta(minutes=15),
                'duration': timedelta(minutes=90),  # 90 min max shed
                'signal_payload': 20.0              # Target reduction of 20 kW
            },
            {
                'dtstart': now + timedelta(minutes=105),
                'duration': timedelta(minutes=15),  # 15 min ramp-down
                'signal_payload': 10.0              # Target reduction of 10 kW (ramp down)
            }
        ]
    )

    server.add_event(
        ven_id='sip1',
        signal_name='LOAD_DISPATCH',
        signal_type='delta',
        intervals=[
            {
                'dtstart': now + timedelta(minutes=360), # 6 hours later
                'duration': timedelta(minutes=60), # 1 hour
                'signal_payload': 15.0             # Target reduction of 15 kW
            }
        ]
    )
    print(f"[VTN Server] Started. Scheduled multiple events with ramp periods.")
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
        ev_p_base = ev_base.get_baseline_power(step, dt_hours)
        
        b_base.step(T_out, hvac_p_base, dt_hours, mode="cooling")
        actual_ev_p_base = ev_base.step(step, ev_p_base, dt_hours, allocation_method="proportional")
        
        baseline_T_in.append(b_base.T_in)
        baseline_hvac_power.append(hvac_p_base)
        baseline_ev_power.append(actual_ev_p_base)
        baseline_total_power.append(base_d + hvac_p_base + actual_ev_p_base)
        for ev in ev_base.evs:
            baseline_ev_socs[ev.id].append(ev.soc)
            
        # --- Dispatch-Optimized (Actual) Simulation ---
        if step < end_step:
            # Apply the optimized dispatch computed by the DT Sandbox (covers pre-event and event)
            dispatch_hvac = trajectories["hvac_power"][step]
            dispatch_ev = trajectories["ev_power"][step]

            # Dynamically enforce target shed if in event window
            if start_step <= step < end_step:
                target_limit = max(0.0, baseline_total_power[-1] - target_shed)
                current_uncontrollable = base_d + dispatch_hvac
                if current_uncontrollable + dispatch_ev > target_limit:
                    dispatch_ev = max(0.0, target_limit - current_uncontrollable)
            # determine alloc method if we are simulating the strategy
            # for simplicity we use the same fallback logic if we need to manually step it,
            # but wait, the actual sim should use the DT's decision!
            # The trajectories dictionary gives us the *total* EV power dispatch. We need to allocate it here.
            # Strategy C pre-cool logic applies before start_step.
            # We can use priority_departure for C, and proportional otherwise?
            # It's safer to just use priority_departure anytime we are applying the DT trajectory
            if strategy == 'C' or start_step <= step < end_step:
                ev_alloc_method = "priority_departure"
            else:
                ev_alloc_method = "proportional"
        else:
            # Normal operation (baseline) after event
            dispatch_hvac = real_building.P_HVAC_baseline
            dispatch_ev = real_ev_fleet.get_baseline_power(step, dt_hours)
            ev_alloc_method = "proportional"
            
        real_building.step(T_out, dispatch_hvac, dt_hours, mode="cooling")
        actual_ev_p_real = real_ev_fleet.step(step, dispatch_ev, dt_hours, allocation_method=ev_alloc_method)
        
        sim_T_in.append(real_building.T_in)
        sim_hvac_power.append(dispatch_hvac)
        sim_ev_power.append(actual_ev_p_real)
        sim_total_power.append(base_d + dispatch_hvac + actual_ev_p_real)
        for ev in real_ev_fleet.evs:
            sim_ev_socs[ev.id].append(ev.soc)

    # 7.5 Quantitative Verification of Shed
    print("\n--- Quantitative Verification of Shed ---")
    print(f"Target Shed: {target_shed:.2f} kW from step {start_step} to {end_step-1}")
    total_shed_missed = 0.0
    for step in range(start_step, end_step):
        base_p = baseline_total_power[step]
        sim_p = sim_total_power[step]
        actual_shed = base_p - sim_p

        # Determine if target shed is met, allowing a small floating point tolerance
        is_met = actual_shed >= target_shed - 1e-6
        if not is_met:
            total_shed_missed += (target_shed - actual_shed)
        status = "MET" if is_met else f"MISSED (Short by {target_shed - actual_shed:.2f} kW)"
        print(f"  Step {step}: Baseline {base_p:.2f} kW | Actual {sim_p:.2f} kW | Shed {actual_shed:.2f} kW | Status: {status}")
    print("-----------------------------------------\n")

    # 8. Plotting
    print("[Simulation] Plotting results...")
    plt.style.use('seaborn-v0_8-colorblind') # Colorblind-friendly palette
    time_hours = np.array(steps) * 0.25
    fig, axs = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
    
    event_start_hour = start_step * 0.25
    event_end_hour = end_step * 0.25

    # Calculate summary statistics for text box
    total_energy_shifted = np.sum(np.array(baseline_total_power) - np.array(sim_total_power)) * dt_hours
    max_temp = np.max(sim_T_in)

    soc_at_departure_str = []
    for ev in real_ev_fleet.evs:
        dep_step = min(ev.departure_step, len(sim_ev_socs[ev.id]) - 1)
        soc_at_dep = sim_ev_socs[ev.id][dep_step]
        soc_at_departure_str.append(f"{ev.id}: {soc_at_dep*100:.1f}%")

    stats_text = (
        f"--- PoC Summary ---\n"
        f"Energy Shifted: {total_energy_shifted:.2f} kWh\n"
        f"Max Indoor Temp: {max_temp:.1f} °C\n"
        f"SoC at Departure:\n" + "\n".join(soc_at_departure_str)
    )

    # Subplot 1: Total Power Demand Comparison
    axs[0].plot(time_hours, baseline_total_power, linestyle='--', linewidth=1.5, label='Baseline Total Power')
    axs[0].plot(time_hours, sim_total_power, linestyle='-', linewidth=2, label=f'DT-Optimized Total Power (Strategy {strategy})')
    
    # Draw demand limit during the event
    event_time_hours = np.arange(start_step, end_step) * 0.25
    limit_profile = np.array(baseline_total_power[start_step:end_step]) - target_shed
    axs[0].plot(event_time_hours, limit_profile, 'k:', linewidth=2, label='Grid Power Limit')
    
    axs[0].set_ylabel('Power (kW)')
    axs[0].set_title('Total Building & EV Power Profile')
    axs[0].legend(loc='upper right')
    axs[0].grid(True, linestyle='--', alpha=0.6)
    
    # Subplot 2: Building Indoor Temp vs Ambient Temp & Comfort Bounds
    axs[1].plot(time_hours, T_out_profile, linestyle='-', alpha=0.7, label='Outdoor Temperature')
    axs[1].plot(time_hours, baseline_T_in, linestyle='--', linewidth=1.5, label='Baseline Indoor Temperature')
    axs[1].plot(time_hours, sim_T_in, linestyle='-', linewidth=2, label='DT-Optimized Indoor Temperature')
    axs[1].axhline(y=b_cfg["T_max"], color='darkred', linestyle=':', linewidth=2, label='Comfort Max Limit')
    axs[1].axhline(y=b_cfg["T_min"], color='blue', linestyle=':', linewidth=2, label='Comfort Min Limit')
    axs[1].set_ylabel('Temperature (°C)')
    axs[1].set_title('Building Indoor Thermal Dynamics')
    axs[1].legend(loc='upper left')
    axs[1].grid(True, linestyle='--', alpha=0.6)
    
    # Subplot 3: EV Fleet State of Charge (SoC) trajectories
    for ev_id, socs in sim_ev_socs.items():
        axs[2].plot(time_hours, np.array(socs) * 100, '-', linewidth=2, label=f'Optimized {ev_id}')
    for ev_id, socs in baseline_ev_socs.items():
        axs[2].plot(time_hours, np.array(socs) * 100, '--', linewidth=1.5, alpha=0.6, label=f'Baseline {ev_id}')
    axs[2].set_ylabel('State of Charge (%)')
    axs[2].set_xlabel('Time of Day')
    axs[2].set_title('EV Fleet State of Charge (SoC)')
    axs[2].legend(loc='lower right')
    axs[2].grid(True, linestyle='--', alpha=0.6)
    
    # Annotations and shaded regions
    for ax in axs:
        # Shaded region for OpenADR event window
        ax.axvspan(event_start_hour, event_end_hour, color='gray', alpha=0.2, label='OpenADR Event' if ax == axs[0] else "")

    # OpenADR Event Annotation
    axs[0].text(event_start_hour + (event_end_hour - event_start_hour)/2, axs[0].get_ylim()[1]*0.85,
                'OpenADR\nEvent', horizontalalignment='center', verticalalignment='top',
                fontsize=10, bbox=dict(facecolor='white', alpha=0.8, edgecolor='none', pad=2.0))

    # Add statistics text box to the first subplot
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    axs[0].text(0.02, 0.95, stats_text, transform=axs[0].transAxes, fontsize=9,
                verticalalignment='top', bbox=props)

    # Annotate EV arrivals/departures in subplot 3
    # Find suitable y-position for annotations
    y_min_soc = 20
    for ev in real_ev_fleet.evs:
        arr_hour = ev.arrival_step * 0.25
        dep_hour = ev.departure_step * 0.25
        axs[2].annotate(f'{ev.id} Arr', xy=(arr_hour, y_min_soc), xytext=(arr_hour, y_min_soc - 10),
                        arrowprops=dict(facecolor='black', shrink=0.05, width=1, headwidth=5),
                        fontsize=8, horizontalalignment='center', zorder=5)
        axs[2].annotate(f'{ev.id} Dep', xy=(dep_hour, y_min_soc), xytext=(dep_hour, y_min_soc - 10),
                        arrowprops=dict(facecolor='black', shrink=0.05, width=1, headwidth=5),
                        fontsize=8, horizontalalignment='center', zorder=5)

    # X-axis time-of-day labels
    axs[2].set_xticks([0, 6, 12, 18, 24])
    axs[2].set_xticklabels(['00:00', '06:00', '12:00', '18:00', '24:00'])
    axs[2].set_xlim([0, 24])

    plt.tight_layout()
    plot_filename_png = os.path.join(os.path.dirname(__file__), 'simulation_results.png')
    plot_filename_pdf = os.path.join(os.path.dirname(__file__), 'simulation_results.pdf')
    plt.savefig(plot_filename_png, dpi=300)
    plt.savefig(plot_filename_pdf, format='pdf', dpi=300)
    print(f"[Simulation] Success! Plots saved as: {plot_filename_png} and {plot_filename_pdf}")
    
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
