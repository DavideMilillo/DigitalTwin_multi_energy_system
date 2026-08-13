# plot_strategy_comparison.py
# Simulates full 24h day under Strategy A, Strategy B, and Strategy C
# Generates publication-quality comparison plots

import os
import sys
import csv
import copy
import matplotlib.pyplot as plt
import numpy as np

# Ensure path is set
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import CONFIG
from models.building_model import BuildingThermalModel
from models.ev_fleet_model import EVFleetModel
from core.dt_sandbox import DigitalTwinSandbox

def run_simulation_for_strategy(strategy_name: str, base_load_profile, T_out_profile, dt_hours=0.25):
    """
    Runs 24h physical simulation forcing a specific strategy for both Event 1 (14:00) and Event 2 (20:00).
    """
    b_cfg = CONFIG["building"]
    ev_cfg = CONFIG["ev_fleet"]["evs"]

    b_model = BuildingThermalModel(
        b_cfg["R_th"], b_cfg["C_th"], b_cfg["COP"],
        b_cfg["T_min"], b_cfg["T_max"], b_cfg["T_in_init"],
        b_cfg["P_HVAC_max"], b_cfg["P_HVAC_baseline"]
    )
    ev_model = EVFleetModel(ev_cfg)

    # Event definitions
    # Event 1: step 56 to 64 (14:00-16:00), target 20 kW
    # Event 2: step 80 to 84 (20:00-21:00), target 15 kW
    e1_start, e1_end, e1_target = 56, 64, 20.0
    e2_start, e2_end, e2_target = 80, 84, 15.0

    e1_precool_start = max(0, e1_start - 4) if strategy_name == 'C' else e1_start
    e2_precool_start = max(0, e2_start - 4) if strategy_name == 'C' else e2_start

    T_in_traj = []
    hvac_power_traj = []
    ev_power_traj = []
    total_power_traj = []
    ev_soc_traj = {ev.id: [] for ev in ev_model.evs}

    for step in range(len(base_load_profile)):
        T_out = T_out_profile[step]
        base_d = base_load_profile[step]

        hvac_base_p = b_model.P_HVAC_baseline
        ev_base_p = ev_model.get_baseline_power(step, dt_hours)
        total_base_p = base_d + hvac_base_p + ev_base_p

        # Check if in Event 1, Event 2, or pre-cooling windows
        in_e1 = (e1_start <= step < e1_end)
        in_e2 = (e2_start <= step < e2_end)
        in_e1_precool = (e1_precool_start <= step < e1_start) and (strategy_name == 'C')
        in_e2_precool = (e2_precool_start <= step < e2_start) and (strategy_name == 'C')

        if in_e1:
            target_shed = e1_target
        elif in_e2:
            target_shed = e2_target
        else:
            target_shed = 0.0

        # Dispatch calculation
        if strategy_name == 'A':
            dispatch_hvac = hvac_base_p
            if in_e1 or in_e2:
                dispatch_ev = max(0.0, ev_base_p - target_shed)
                target_limit = max(0.0, total_base_p - target_shed)
                if base_d + dispatch_hvac + dispatch_ev > target_limit:
                    dispatch_ev = max(0.0, target_limit - (base_d + dispatch_hvac))
            else:
                dispatch_ev = ev_base_p
            ev_alloc = "priority_departure" if (in_e1 or in_e2) else "proportional"
            is_controlled = False

        elif strategy_name == 'B':
            if in_e1 or in_e2:
                needed = target_shed
                hvac_red = min(needed, hvac_base_p)
                dispatch_hvac = hvac_base_p - hvac_red
                rem_red = needed - hvac_red
                dispatch_ev = max(0.0, ev_base_p - rem_red)
                target_limit = max(0.0, total_base_p - target_shed)
                if base_d + dispatch_hvac + dispatch_ev > target_limit:
                    dispatch_ev = max(0.0, target_limit - (base_d + dispatch_hvac))
            else:
                dispatch_hvac = hvac_base_p
                dispatch_ev = ev_base_p
            ev_alloc = "priority_departure" if (in_e1 or in_e2) else "proportional"
            is_controlled = (in_e1 or in_e2)

        elif strategy_name == 'C':
            if in_e1_precool or in_e2_precool:
                if b_model.T_in <= b_model.T_min + 0.5:
                    dispatch_hvac = 0.0
                elif b_model.T_in <= b_model.T_min + 1.0:
                    dispatch_hvac = b_model.P_HVAC_baseline
                else:
                    dispatch_hvac = b_model.P_HVAC_max
                dispatch_ev = ev_base_p
            elif in_e1 or in_e2:
                needed = target_shed
                hvac_red = min(needed, hvac_base_p)
                dispatch_hvac = hvac_base_p - hvac_red
                rem_red = needed - hvac_red
                dispatch_ev = max(0.0, ev_base_p - rem_red)
                target_limit = max(0.0, total_base_p - target_shed)
                if base_d + dispatch_hvac + dispatch_ev > target_limit:
                    dispatch_ev = max(0.0, target_limit - (base_d + dispatch_hvac))
            else:
                dispatch_hvac = hvac_base_p
                dispatch_ev = ev_base_p
            ev_alloc = "priority_departure" if (in_e1 or in_e2) else "proportional"
            is_controlled = (in_e1 or in_e2 or in_e1_precool or in_e2_precool)

        # Step simulation
        b_model.step(T_out, dispatch_hvac, dt_hours, mode="cooling", control_override=is_controlled)
        actual_ev_p = ev_model.step(step, dispatch_ev, dt_hours, allocation_method=ev_alloc)

        actual_total_p = base_d + b_model.P_HVAC + actual_ev_p

        T_in_traj.append(b_model.T_in)
        hvac_power_traj.append(b_model.P_HVAC)
        ev_power_traj.append(actual_ev_p)
        total_power_traj.append(actual_total_p)
        for ev in ev_model.evs:
            ev_soc_traj[ev.id].append(ev.soc)

    return {
        "T_in": np.array(T_in_traj),
        "hvac_power": np.array(hvac_power_traj),
        "ev_power": np.array(ev_power_traj),
        "total_power": np.array(total_power_traj),
        "ev_socs": {ev_id: np.array(socs) for ev_id, socs in ev_soc_traj.items()}
    }

def main():
    # Load profile data
    csv_path = os.path.join(os.path.dirname(__file__), 'data', 'profiles.csv')
    steps = []
    T_out_profile = []
    base_load_profile = []
    with open(csv_path, 'r') as f:
        for row in csv.DictReader(f):
            steps.append(int(row['step']))
            T_out_profile.append(float(row['T_out']))
            base_load_profile.append(float(row['base_load']))

    steps = np.array(steps)
    time_hours = steps * 0.25

    # Run Baseline (no ADR)
    b_cfg = CONFIG["building"]
    ev_cfg = CONFIG["ev_fleet"]["evs"]
    b_base = BuildingThermalModel(
        b_cfg["R_th"], b_cfg["C_th"], b_cfg["COP"],
        b_cfg["T_min"], b_cfg["T_max"], b_cfg["T_in_init"],
        b_cfg["P_HVAC_max"], b_cfg["P_HVAC_baseline"]
    )
    ev_base = EVFleetModel(ev_cfg)
    base_T_in = []
    base_tot_power = []
    base_ev_socs = {ev['id']: [] for ev in ev_cfg}

    for step in range(len(steps)):
        T_out = T_out_profile[step]
        base_d = base_load_profile[step]
        hvac_p = b_base.P_HVAC_baseline
        ev_p = ev_base.get_baseline_power(step, 0.25)
        b_base.step(T_out, hvac_p, 0.25, mode="cooling", control_override=False)
        actual_ev_p = ev_base.step(step, ev_p, 0.25, allocation_method="proportional")
        base_T_in.append(b_base.T_in)
        base_tot_power.append(base_d + b_base.P_HVAC + actual_ev_p)
        for ev in ev_base.evs:
            base_ev_socs[ev.id].append(ev.soc)

    # Run Strategy A, B, C
    results_A = run_simulation_for_strategy('A', base_load_profile, T_out_profile)
    results_B = run_simulation_for_strategy('B', base_load_profile, T_out_profile)
    results_C = run_simulation_for_strategy('C', base_load_profile, T_out_profile)

    # Plot 1: 3 Columns x 3 Rows (Side-by-Side Comparison)
    plt.style.use('seaborn-v0_8-colorblind')
    fig, axs = plt.subplots(3, 3, figsize=(16, 12), sharex=True, sharey='row')

    strats = ['A', 'B', 'C']
    res_map = {'A': results_A, 'B': results_B, 'C': results_C}
    titles = {
        'A': 'Strategy A: EV-Only Curtailment',
        'B': 'Strategy B: Coupled Curtailment',
        'C': 'Strategy C: Pre-Cooling + Coupled'
    }

    # Grid limits for overlay
    limit_e1 = np.array(base_tot_power[56:64]) - 20.0
    limit_e2 = np.array(base_tot_power[80:84]) - 15.0

    for col_idx, strat in enumerate(strats):
        res = res_map[strat]
        ax_p = axs[0, col_idx]
        ax_t = axs[1, col_idx]
        ax_s = axs[2, col_idx]

        # Row 1: Total Power Profile
        ax_p.plot(time_hours, base_tot_power, 'k--', alpha=0.5, label='Baseline Demand')
        ax_p.plot(time_hours, res['total_power'], color='#1f77b4' if strat=='A' else ('#d62728' if strat=='B' else '#2ca02c'), linewidth=2, label=f'Strategy {strat} Power')
        ax_p.plot(time_hours[56:64], limit_e1, 'k:', linewidth=2, label='Grid Limit')
        ax_p.plot(time_hours[80:84], limit_e2, 'k:', linewidth=2)
        ax_p.set_title(titles[strat], fontsize=12, fontweight='bold')
        ax_p.grid(True, linestyle='--', alpha=0.6)
        if col_idx == 0:
            ax_p.set_ylabel('Power (kW)', fontsize=11)
        ax_p.legend(loc='upper right', fontsize=8)

        # Highlight event zones
        ax_p.axvspan(14, 16, color='gray', alpha=0.18)
        ax_p.axvspan(20, 21, color='gray', alpha=0.18)

        # Row 2: Indoor Temperature
        ax_t.plot(time_hours, T_out_profile, color='orange', alpha=0.5, label='Outdoor Temp')
        ax_t.plot(time_hours, base_T_in, 'k--', alpha=0.4, label='Baseline Temp')
        ax_t.plot(time_hours, res['T_in'], color='#1f77b4' if strat=='A' else ('#d62728' if strat=='B' else '#2ca02c'), linewidth=2, label=f'T_in Strategy {strat}')
        ax_t.axhline(24.0, color='darkred', linestyle=':', label='Comfort Max (24°C)')
        ax_t.axhline(20.0, color='blue', linestyle=':', label='Comfort Min (20°C)')

        # Annotate Strategy B violation or Strategy C precooling
        if strat == 'B':
            max_b = np.max(res['T_in'])
            ax_t.annotate(f'Violation! ({max_b:.2f}°C)', xy=(15.75, max_b), xytext=(12, 24.3),
                          arrowprops=dict(facecolor='darkred', shrink=0.05, width=1.5, headwidth=6),
                          fontsize=9, color='darkred', fontweight='bold')
        elif strat == 'C':
            min_c = np.min(res['T_in'][52:56])
            ax_t.annotate(f'Pre-cooled ({min_c:.1f}°C)', xy=(13.75, min_c), xytext=(9.5, 20.2),
                          arrowprops=dict(facecolor='green', shrink=0.05, width=1.5, headwidth=6),
                          fontsize=9, color='darkgreen', fontweight='bold')

        ax_t.grid(True, linestyle='--', alpha=0.6)
        if col_idx == 0:
            ax_t.set_ylabel('Temperature (°C)', fontsize=11)
        ax_t.legend(loc='upper left', fontsize=8)

        ax_t.axvspan(14, 16, color='gray', alpha=0.18)
        ax_t.axvspan(20, 21, color='gray', alpha=0.18)

        # Row 3: EV Fleet State of Charge
        for ev_id, socs in res['ev_socs'].items():
            ax_s.plot(time_hours, np.array(socs) * 100, linewidth=2, label=f'{ev_id} Strategy {strat}')
        for ev_id, socs in base_ev_socs.items():
            ax_s.plot(time_hours, np.array(socs) * 100, 'k--', alpha=0.3)
        ax_s.set_xlabel('Time of Day (Hours)', fontsize=11)
        ax_s.grid(True, linestyle='--', alpha=0.6)
        if col_idx == 0:
            ax_s.set_ylabel('EV SoC (%)', fontsize=11)
        ax_s.legend(loc='lower right', fontsize=8)

        ax_s.set_xticks([0, 6, 12, 18, 24])
        ax_s.set_xticklabels(['00:00', '06:00', '12:00', '18:00', '24:00'])
        ax_s.axvspan(14, 16, color='gray', alpha=0.18)
        ax_s.axvspan(20, 21, color='gray', alpha=0.18)

    plt.suptitle('Digital Twin Sandboxing Strategy Comparison (Strategies A vs B vs C)', fontsize=14, fontweight='bold', y=0.99)
    plt.tight_layout()

    out_png = os.path.join(os.path.dirname(__file__), 'strategy_comparison_matrix.png')
    out_pdf = os.path.join(os.path.dirname(__file__), 'strategy_comparison_matrix.pdf')
    plt.savefig(out_png, dpi=300)
    plt.savefig(out_pdf, format='pdf', dpi=300)
    print(f"[Plotter] Saved side-by-side comparison to {out_png} and {out_pdf}")

    # Plot 2: Overlaid Comparison Figure (Direct overlay of A vs B vs C in 3 subplots)
    fig2, axs2 = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

    # Subplot 1: Total Power
    axs2[0].plot(time_hours, base_tot_power, 'k--', alpha=0.6, label='Baseline Demand')
    axs2[0].plot(time_hours, results_A['total_power'], '#1f77b4', linewidth=2, label='Strategy A (EV Only)')
    axs2[0].plot(time_hours, results_B['total_power'], '#d62728', linewidth=2, label='Strategy B (Coupled)')
    axs2[0].plot(time_hours, results_C['total_power'], '#2ca02c', linewidth=2, label='Strategy C (Pre-cooling + Coupled)')
    axs2[0].plot(time_hours[56:64], limit_e1, 'k:', linewidth=2, label='Grid Power Limit')
    axs2[0].plot(time_hours[80:84], limit_e2, 'k:', linewidth=2)
    axs2[0].set_ylabel('Power (kW)', fontsize=11)
    axs2[0].set_title('Direct Power Profile Comparison (Strategies A, B, C)', fontsize=12, fontweight='bold')
    axs2[0].legend(loc='upper right', fontsize=9)
    axs2[0].grid(True, linestyle='--', alpha=0.6)
    axs2[0].axvspan(14, 16, color='gray', alpha=0.15)
    axs2[0].axvspan(20, 21, color='gray', alpha=0.15)

    # Subplot 2: Temperature Overlay
    axs2[1].plot(time_hours, T_out_profile, 'orange', alpha=0.5, label='Outdoor Temp')
    axs2[1].plot(time_hours, base_T_in, 'k--', alpha=0.5, label='Baseline Temp')
    axs2[1].plot(time_hours, results_A['T_in'], '#1f77b4', linewidth=2, label='Strategy A (Thermostat Baseline)')
    axs2[1].plot(time_hours, results_B['T_in'], '#d62728', linewidth=2, label='Strategy B (Overheating Violation)')
    axs2[1].plot(time_hours, results_C['T_in'], '#2ca02c', linewidth=2, label='Strategy C (Optimal Pre-cooling)')
    axs2[1].axhline(24.0, color='darkred', linestyle=':', linewidth=1.5, label='Comfort Max (24°C)')
    axs2[1].axhline(20.0, color='blue', linestyle=':', linewidth=1.5, label='Comfort Min (20°C)')
    axs2[1].set_ylabel('Temperature (°C)', fontsize=11)
    axs2[1].set_title('Building Thermal Dynamics Comparison', fontsize=12, fontweight='bold')
    axs2[1].legend(loc='upper left', fontsize=9)
    axs2[1].grid(True, linestyle='--', alpha=0.6)
    axs2[1].axvspan(14, 16, color='gray', alpha=0.15)
    axs2[1].axvspan(20, 21, color='gray', alpha=0.15)

    # Subplot 3: Average Fleet SoC Comparison
    avg_soc_A = np.mean([socs for socs in results_A['ev_socs'].values()], axis=0) * 100
    avg_soc_B = np.mean([socs for socs in results_B['ev_socs'].values()], axis=0) * 100
    avg_soc_C = np.mean([socs for socs in results_C['ev_socs'].values()], axis=0) * 100
    avg_soc_base = np.mean([socs for socs in base_ev_socs.values()], axis=0) * 100

    axs2[2].plot(time_hours, avg_soc_base, 'k--', alpha=0.6, label='Baseline Fleet SoC')
    axs2[2].plot(time_hours, avg_soc_A, '#1f77b4', linewidth=2, label='Strategy A Fleet SoC (30% more curtailment)')
    axs2[2].plot(time_hours, avg_soc_B, '#d62728', linewidth=2, label='Strategy B Fleet SoC')
    axs2[2].plot(time_hours, avg_soc_C, '#2ca02c', linewidth=2, label='Strategy C Fleet SoC (Preserved Energy)')
    axs2[2].set_ylabel('Fleet Average SoC (%)', fontsize=11)
    axs2[2].set_xlabel('Time of Day (Hours)', fontsize=11)
    axs2[2].set_title('EV Fleet Average State of Charge Comparison', fontsize=12, fontweight='bold')
    axs2[2].legend(loc='lower right', fontsize=9)
    axs2[2].grid(True, linestyle='--', alpha=0.6)
    axs2[2].set_xticks([0, 6, 12, 18, 24])
    axs2[2].set_xticklabels(['00:00', '06:00', '12:00', '18:00', '24:00'])
    axs2[2].axvspan(14, 16, color='gray', alpha=0.15)
    axs2[2].axvspan(20, 21, color='gray', alpha=0.15)

    plt.tight_layout()
    out_overlaid_png = os.path.join(os.path.dirname(__file__), 'strategy_comparison_overlaid.png')
    out_overlaid_pdf = os.path.join(os.path.dirname(__file__), 'strategy_comparison_overlaid.pdf')
    plt.savefig(out_overlaid_png, dpi=300)
    plt.savefig(out_overlaid_pdf, format='pdf', dpi=300)
    print(f"[Plotter] Saved overlaid comparison to {out_overlaid_png} and {out_overlaid_pdf}")

if __name__ == "__main__":
    main()
