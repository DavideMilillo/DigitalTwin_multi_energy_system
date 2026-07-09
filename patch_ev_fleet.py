import re

with open('dt_openadr_poc/models/ev_fleet_model.py', 'r') as f:
    content = f.read()

new_step_method = """    def step(self, step, allocated_power, dt_hours, allocation_method="proportional"):
        \"\"\"
        Distributes allocated power to active EVs that are not yet fully charged.
        \"\"\"
        active = [ev for ev in self.get_active_evs(step) if ev.soc < 1.0]
        if not active:
            for ev in self.evs:
                ev.current_charging_power = 0.0
            return 0.0

        actual_power_delivered = 0.0

        if allocation_method == "proportional":
            total_max_p = sum(ev.max_charging_power for ev in active)
            if total_max_p == 0:
                for ev in self.evs:
                    ev.current_charging_power = 0.0
                return 0.0

            for ev in active:
                # allocate proportionally
                share = ev.max_charging_power / total_max_p
                allocated = allocated_power * share
                ev.charge(allocated, dt_hours)
                actual_power_delivered += ev.current_charging_power

        elif allocation_method == "priority_departure":
            # Prioritize EVs departing sooner
            active.sort(key=lambda x: x.departure_step)
            remaining_power = allocated_power
            for ev in active:
                allocated = min(ev.max_charging_power, remaining_power)
                ev.charge(allocated, dt_hours)
                actual_power_delivered += ev.current_charging_power
                remaining_power -= ev.current_charging_power
                remaining_power = max(0.0, remaining_power)

        # For non-active or fully charged EVs, power is 0
        for ev in self.evs:
            if ev not in active:
                ev.current_charging_power = 0.0

        return actual_power_delivered"""

content = re.sub(r'    def step\(self, step, allocated_power, dt_hours\):[\s\S]*?return actual_power_delivered\n', new_step_method + '\n', content)

with open('dt_openadr_poc/models/ev_fleet_model.py', 'w') as f:
    f.write(content)
