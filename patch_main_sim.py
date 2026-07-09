import re

with open('dt_openadr_poc/main_simulation.py', 'r') as f:
    content = f.read()

new_dispatch_actual_sim = """        # --- Dispatch-Optimized (Actual) Simulation ---
        if step < end_step:
            # Apply the optimized dispatch computed by the DT Sandbox (covers pre-event and event)
            dispatch_hvac = trajectories["hvac_power"][step]
            dispatch_ev = trajectories["ev_power"][step]
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
            active_evs_real = real_ev_fleet.get_active_evs(step)
            dispatch_ev = sum(min(ev.max_charging_power, (ev.target_soc - ev.soc) * ev.battery_capacity / dt_hours) for ev in active_evs_real if ev.soc < ev.target_soc)
            dispatch_ev = max(0.0, dispatch_ev)
            ev_alloc_method = "proportional"

        real_building.step(T_out, dispatch_hvac, dt_hours, mode="cooling")
        actual_ev_p_real = real_ev_fleet.step(step, dispatch_ev, dt_hours, allocation_method=ev_alloc_method)"""

content = re.sub(r'        # --- Dispatch-Optimized \(Actual\) Simulation ---[\s\S]*?actual_ev_p_real = real_ev_fleet\.step\(step, dispatch_ev, dt_hours\)', new_dispatch_actual_sim, content)


# Also need to update baseline to have allocation_method
content = content.replace('actual_ev_p_base = ev_base.step(step, ev_p_base, dt_hours)', 'actual_ev_p_base = ev_base.step(step, ev_p_base, dt_hours, allocation_method="proportional")')


with open('dt_openadr_poc/main_simulation.py', 'w') as f:
    f.write(content)
