import re

with open('dt_openadr_poc/core/ems_ven.py', 'r') as f:
    content = f.read()

new_handle_event = """            # Invoke Digital Twin Sandboxing
            sandbox = DigitalTwinSandbox()

            # Evaluate Strategy A (EV Only)
            print("[EMS VEN] Digital Twin simulating Strategy A (EV Only)...")
            feasible_a, traj_a, score_a = sandbox.simulate_scenario(
                self.building, self.ev_fleet, 'A', start_step, duration_steps,
                shed_kW, self.base_demand_profile, self.outdoor_temp_profile, self.dt_hours
            )

            # Evaluate Strategy B (Coupled HVAC + EV)
            print("[EMS VEN] Digital Twin simulating Strategy B (Coupled Building-EV)...")
            feasible_b, traj_b, score_b = sandbox.simulate_scenario(
                self.building, self.ev_fleet, 'B', start_step, duration_steps,
                shed_kW, self.base_demand_profile, self.outdoor_temp_profile, self.dt_hours
            )

            # Evaluate Strategy C (Pre-cooling + Coupled)
            print("[EMS VEN] Digital Twin simulating Strategy C (Pre-cooling + Coupled Building-EV)...")
            feasible_c, traj_c, score_c = sandbox.simulate_scenario(
                self.building, self.ev_fleet, 'C', start_step, duration_steps,
                shed_kW, self.base_demand_profile, self.outdoor_temp_profile, self.dt_hours
            )

            print(f"[EMS VEN] DT Sandbox Results:")
            print(f"  - Strategy A (EV Only) Feasible: {feasible_a}, Score: {score_a:.2f}")
            if not feasible_a:
                print(f"    Violations: {traj_a['violation_details']}")
            print(f"  - Strategy B (Coupled) Feasible: {feasible_b}, Score: {score_b:.2f}")
            if not feasible_b:
                print(f"    Violations: {traj_b['violation_details']}")
            print(f"  - Strategy C (Pre-cooling + Coupled) Feasible: {feasible_c}, Score: {score_c:.2f}")
            if not feasible_c:
                print(f"    Violations: {traj_c['violation_details']}")

            # Decision Logic: Rank strategies and choose the best one
            strategies = [
                ('C', feasible_c, score_c, traj_c),
                ('B', feasible_b, score_b, traj_b),
                ('A', feasible_a, score_a, traj_a)
            ]

            feasible_strategies = [s for s in strategies if s[1]]

            if feasible_strategies:
                # Prioritize feasible strategy with the lowest score.
                # If scores are equal (e.g., 0.0), it will prefer C > B > A due to the order in the list.
                best_strategy = min(feasible_strategies, key=lambda x: x[2])
                print(f"[EMS VEN] Strategy {best_strategy[0]} is feasible with best score. Activating Strategy {best_strategy[0]}.")
                self.dispatch_result = (best_strategy[0], best_strategy[3], start_step, duration_steps, shed_kW)
            else:
                # If all are infeasible, pick the one with the lowest violation score
                best_strategy = min(strategies, key=lambda x: x[2])
                print(f"[EMS VEN] WARNING: All strategies violate bounds. Choosing Strategy {best_strategy[0]} with minimal impact (Score: {best_strategy[2]:.2f}).")
                self.dispatch_result = (best_strategy[0], best_strategy[3], start_step, duration_steps, shed_kW)

            self.event_processed.set()
            return 'optIn'"""

content = re.sub(r'            # Invoke Digital Twin Sandboxing[\s\S]*?return \'optIn\'', new_handle_event, content)

with open('dt_openadr_poc/core/ems_ven.py', 'w') as f:
    f.write(content)
