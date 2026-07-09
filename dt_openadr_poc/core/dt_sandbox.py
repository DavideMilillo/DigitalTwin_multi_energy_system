# core/dt_sandbox.py
# The Digital Twin simulation engine for "What-If" sandboxing

import copy
import numpy as np

class DigitalTwinSandbox:
    def __init__(self):
        pass

    def simulate_scenario(self, building_model, ev_fleet_model, strategy, start_step, duration_steps, power_reduction_target, base_demand_profile, outdoor_temp_profile, dt_hours):
        """
        Simulates the demand response event using deep copies of the physical models.
        
        Parameters:
        - building_model: BuildingThermalModel instance
        - ev_fleet_model: EVFleetModel instance
        - strategy: 'A' (EV only) or 'B' (Coupled building + EV)
        - start_step: step index when the event starts
        - duration_steps: how many steps the event lasts
        - power_reduction_target: total kW to reduce from baseline
        - base_demand_profile: baseline non-HVAC electrical demand (array or list)
        - outdoor_temp_profile: outdoor temperature profile (array or list)
        - dt_hours: step size in hours (e.g. 0.25)
        
        Returns:
        - feasible: bool (True if no violations occurred)
        - trajectories: dict of historical states during the simulation period
        """
        # Take copies of the models to avoid mutating current states
        b_sim = copy.deepcopy(building_model)
        ev_sim = copy.deepcopy(ev_fleet_model)

        # We will record the trajectories during the event
        t_in_history = []
        ev_soc_history = {ev.id: [] for ev in ev_sim.evs}
        hvac_power_history = []
        ev_power_history = []
        total_power_history = []
        violation_details = []

        feasible = True
        
        for k in range(duration_steps):
            step = start_step + k
            T_out = outdoor_temp_profile[step]
            base_d = base_demand_profile[step]

            # Calculate baseline powers (what we WOULD consume without ADR)
            # HVAC baseline
            hvac_base_power = b_sim.P_HVAC_baseline
            
            # EV baseline charging power (max possible for active EVs that need charge)
            active_evs = ev_sim.get_active_evs(step)
            ev_base_power = sum(min(ev.max_charging_power, (ev.target_soc - ev.soc) * ev.battery_capacity / dt_hours) for ev in active_evs if ev.soc < ev.target_soc)
            ev_base_power = max(0.0, ev_base_power)
            
            total_baseline_power = base_d + hvac_base_power + ev_base_power
            target_limit = max(0.0, total_baseline_power - power_reduction_target)

            # Determine dispatch under strategy
            if strategy == 'A':
                # Strategy A: EV only reduction. HVAC stays at baseline.
                dispatch_hvac = hvac_base_power
                
                # EV charging must be reduced by the full power_reduction_target (limited to 0)
                dispatch_ev = max(0.0, ev_base_power - power_reduction_target)
                
            elif strategy == 'B':
                # Strategy B: Coupled Building + EV.
                # First try to reduce HVAC power. How much can we reduce it?
                # We can shut off HVAC completely or reduce it. Let's see how much reduction is needed.
                needed_reduction = power_reduction_target
                
                # Reduce HVAC first (up to the full HVAC baseline power)
                hvac_reduction = min(needed_reduction, hvac_base_power)
                dispatch_hvac = hvac_base_power - hvac_reduction
                
                # Remaining reduction target falls on EVs
                remaining_reduction = needed_reduction - hvac_reduction
                dispatch_ev = max(0.0, ev_base_power - remaining_reduction)
            else:
                raise ValueError("Invalid strategy name. Choose 'A' or 'B'.")

            # Run physical steps
            b_sim.step(T_out, dispatch_hvac, dt_hours, mode="cooling")
            actual_ev_power = ev_sim.step(step, dispatch_ev, dt_hours)
            
            # Check for comfort violations at this step
            if b_sim.is_comfort_violated():
                feasible = False
                violation_details.append(f"Step {step}: Temp {b_sim.T_in:.2f}°C out of comfort bounds [{b_sim.T_min}, {b_sim.T_max}]")

            # Save state trajectories
            t_in_history.append(b_sim.T_in)
            hvac_power_history.append(dispatch_hvac)
            ev_power_history.append(actual_ev_power)
            total_power_history.append(base_d + dispatch_hvac + actual_ev_power)
            for ev in ev_sim.evs:
                ev_soc_history[ev.id].append(ev.soc)

            # Check for departure SoC violations
            departing_violations = ev_sim.check_soc_violations(step + 1) # checking next step departure
            if departing_violations:
                feasible = False
                for ev_id, soc, target in departing_violations:
                    violation_details.append(f"Step {step+1}: EV {ev_id} departed with SoC {soc:.2f} (target {target:.2f})")

        # Let's verify final SoC for any EVs that depart during the event or after the event
        # If their schedule departure is within or at the end of the simulation horizon, check it
        for ev in ev_sim.evs:
            if ev.departure_step <= start_step + duration_steps and ev.soc < ev.target_soc:
                feasible = False

        trajectories = {
            "T_in": np.array(t_in_history),
            "hvac_power": np.array(hvac_power_history),
            "ev_power": np.array(ev_power_history),
            "total_power": np.array(total_power_history),
            "ev_socs": {ev_id: np.array(socs) for ev_id, socs in ev_soc_history.items()},
            "violation_details": violation_details
        }
        
        return feasible, trajectories
