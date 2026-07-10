# core/dt_sandbox.py
# The Digital Twin simulation engine for "What-If" sandboxing

import copy
import numpy as np
from typing import Tuple, Dict, Any, List

from models.building_model import BuildingThermalModel
from models.ev_fleet_model import EVFleetModel


class DigitalTwinSandbox:
    """
    Simulation engine for analyzing and optimizing proactive demand response scenarios.
    """
    def __init__(self) -> None:
        """
        Initializes the Digital Twin Sandbox.
        """
        pass

    def simulate_scenario(self, building_model: BuildingThermalModel, ev_fleet_model: EVFleetModel, strategy: str, current_step: int, start_step: int, duration_steps: int, power_reduction_target: float, base_demand_profile: List[float], outdoor_temp_profile: List[float], dt_hours: float) -> Tuple[bool, Dict[str, Any], float]:
        """
        Simulates the demand response event using deep copies of the physical models.
        
        Args:
            building_model (BuildingThermalModel): The building thermal model instance.
            ev_fleet_model (EVFleetModel): The EV fleet model instance.
            strategy (str): Strategy to use: 'A' (EV only), 'B' (Coupled building + EV), or 'C' (Pre-cooling + Coupled).
            current_step (int): The current simulation step from which to project forward.
            start_step (int): Step index when the event starts.
            duration_steps (int): How many steps the event lasts.
            power_reduction_target (float): Total kW to reduce from baseline.
            base_demand_profile (List[float]): Baseline non-HVAC electrical demand.
            outdoor_temp_profile (List[float]): Outdoor temperature profile.
            dt_hours (float): Step size in hours (e.g., 0.25).

        Returns:
            Tuple[bool, Dict[str, Any], float]:
                - feasible (bool): True if no violations occurred.
                - trajectories (Dict[str, Any]): Dictionary of historical states during the simulation period.
                - score (float): Metric evaluating comfort violation and EV SoC shortfall (0 means perfect).
        """
        b_sim = copy.deepcopy(building_model)
        ev_sim = copy.deepcopy(ev_fleet_model)

        t_in_history = []
        ev_soc_history = {ev.id: [] for ev in ev_sim.evs}
        hvac_power_history = []
        ev_power_history = []
        total_power_history = []
        violation_details = []

        feasible = True
        score = 0.0
        
        end_step = start_step + duration_steps

        # For Strategy C, define a pre-cooling window
        pre_cool_steps = 4 if strategy == 'C' else 0
        pre_cool_start = max(0, start_step - pre_cool_steps)

        for step in range(current_step, end_step):
            T_out = outdoor_temp_profile[step]
            base_d = base_demand_profile[step]

            # Calculate baseline powers
            hvac_base_power = b_sim.P_HVAC_baseline
            ev_base_power = ev_sim.get_baseline_power(step, dt_hours)
            
            total_baseline_power = base_d + hvac_base_power + ev_base_power
            target_limit = max(0.0, total_baseline_power - power_reduction_target)

            # Determine dispatch under strategy
            if strategy == 'A':
                # Strategy A: EV only reduction. HVAC stays at baseline.
                dispatch_hvac = hvac_base_power
                if start_step <= step < end_step:
                    dispatch_ev = max(0.0, ev_base_power - power_reduction_target)
                    target_limit = max(0.0, total_baseline_power - power_reduction_target)
                    current_uncontrollable = base_d + dispatch_hvac
                    if current_uncontrollable + dispatch_ev > target_limit:
                        dispatch_ev = max(0.0, target_limit - current_uncontrollable)
                else:
                    dispatch_ev = ev_base_power
                ev_alloc_method = "priority_departure"
                
            elif strategy == 'B':
                # Strategy B: Coupled Building + EV.
                if start_step <= step < end_step:
                    needed_reduction = power_reduction_target
                    hvac_reduction = min(needed_reduction, hvac_base_power)
                    dispatch_hvac = hvac_base_power - hvac_reduction

                    remaining_reduction = needed_reduction - hvac_reduction
                    dispatch_ev = max(0.0, ev_base_power - remaining_reduction)
                    target_limit = max(0.0, total_baseline_power - power_reduction_target)
                    current_uncontrollable = base_d + dispatch_hvac
                    if current_uncontrollable + dispatch_ev > target_limit:
                        dispatch_ev = max(0.0, target_limit - current_uncontrollable)
                else:
                    dispatch_hvac = hvac_base_power
                    dispatch_ev = ev_base_power
                ev_alloc_method = "priority_departure"
                
            elif strategy == 'C':
                # Strategy C: Pre-cooling + Coupled
                if pre_cool_start <= step < start_step:
                    # Pre-cool: run HVAC at max power, but do not overcool below comfort minimum T_min
                    if b_sim.T_in <= b_sim.T_min + 0.5:
                        dispatch_hvac = 0.0
                    elif b_sim.T_in <= b_sim.T_min + 1.0:
                        dispatch_hvac = b_sim.P_HVAC_baseline
                    else:
                        dispatch_hvac = b_sim.P_HVAC_max
                    dispatch_ev = ev_base_power
                elif start_step <= step < end_step:
                    # During event: shed HVAC fully, then EV
                    needed_reduction = power_reduction_target
                    hvac_reduction = min(needed_reduction, hvac_base_power)
                    dispatch_hvac = hvac_base_power - hvac_reduction

                    remaining_reduction = needed_reduction - hvac_reduction
                    dispatch_ev = max(0.0, ev_base_power - remaining_reduction)
                    target_limit = max(0.0, total_baseline_power - power_reduction_target)
                    current_uncontrollable = base_d + dispatch_hvac
                    if current_uncontrollable + dispatch_ev > target_limit:
                        dispatch_ev = max(0.0, target_limit - current_uncontrollable)
                else:
                    dispatch_hvac = hvac_base_power
                    dispatch_ev = ev_base_power
                ev_alloc_method = "priority_departure"
                
            else:
                raise ValueError("Invalid strategy name. Choose 'A', 'B' or 'C'.")

            # For steps before the event where we don't apply anything (baseline behavior), just use proportional
            if step < start_step and (strategy != 'C' or step < pre_cool_start):
                ev_alloc_method = "proportional"

            # Determine whether building control is overridden by explicit DR strategy
            is_controlled = (start_step <= step < end_step) or (strategy == 'C' and pre_cool_start <= step < start_step)

            # Run physical steps
            b_sim.step(T_out, dispatch_hvac, dt_hours, mode="cooling", control_override=is_controlled)
            actual_ev_power = ev_sim.step(step, dispatch_ev, dt_hours, allocation_method=ev_alloc_method)
            
            # Check for comfort violations at this step
            if b_sim.is_comfort_violated():
                feasible = False
                if b_sim.T_in > b_sim.T_max:
                    score += (b_sim.T_in - b_sim.T_max)
                elif b_sim.T_in < b_sim.T_min:
                    score += (b_sim.T_min - b_sim.T_in)
                violation_details.append(f"Step {step}: Temp {b_sim.T_in:.2f}°C out of comfort bounds [{b_sim.T_min}, {b_sim.T_max}]")

            # Save state trajectories
            t_in_history.append(b_sim.T_in)
            hvac_power_history.append(dispatch_hvac)
            ev_power_history.append(actual_ev_power)
            total_power_history.append(base_d + dispatch_hvac + actual_ev_power)
            for ev in ev_sim.evs:
                ev_soc_history[ev.id].append(ev.soc)

            # Check for departure SoC violations
            departing_violations = ev_sim.check_soc_violations(step + 1)
            if departing_violations:
                feasible = False
                for ev_id, soc, target in departing_violations:
                    score += (target - soc) * 100 # weight SoC heavily
                    violation_details.append(f"Step {step+1}: EV {ev_id} departed with SoC {soc:.2f} (target {target:.2f})")

        # Verify final SoC for any EVs that depart during or after
        for ev in ev_sim.evs:
            if ev.departure_step <= end_step and ev.soc < ev.target_soc:
                feasible = False

        trajectories = {
            "T_in": np.array(t_in_history),
            "hvac_power": np.array(hvac_power_history),
            "ev_power": np.array(ev_power_history),
            "total_power": np.array(total_power_history),
            "ev_socs": {ev_id: np.array(socs) for ev_id, socs in ev_soc_history.items()},
            "violation_details": violation_details
        }
        
        return feasible, trajectories, score
