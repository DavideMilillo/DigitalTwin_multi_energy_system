# models/ev_fleet_model.py
# Simulates the EV Fleet State of Charge and availability

class EV:
    def __init__(self, ev_id, arrival_step, departure_step, battery_capacity, soc_init, target_soc, max_charging_power):
        self.id = ev_id
        self.arrival_step = arrival_step
        self.departure_step = departure_step
        self.battery_capacity = battery_capacity # kWh
        self.soc = soc_init
        self.target_soc = target_soc
        self.max_charging_power = max_charging_power # kW
        self.current_charging_power = 0.0 # kW

    def is_present(self, step):
        return self.arrival_step <= step < self.departure_step

    def charge(self, power_kw, dt_hours):
        # Charge if present and not fully charged
        power = min(power_kw, self.max_charging_power)
        energy_added = power * dt_hours
        self.current_charging_power = power
        
        # Update SoC
        max_energy = self.battery_capacity * 1.0
        current_energy = self.soc * self.battery_capacity
        new_energy = min(current_energy + energy_added, max_energy)
        self.soc = new_energy / self.battery_capacity
        return self.soc


class EVFleetModel:
    def __init__(self, ev_configs):
        self.evs = [EV(
            ev["id"],
            ev["arrival_step"],
            ev["departure_step"],
            ev["battery_capacity"],
            ev["soc_init"],
            ev["target_soc"],
            ev["max_charging_power"]
        ) for ev in ev_configs]

    def get_active_evs(self, step):
        return [ev for ev in self.evs if ev.is_present(step)]

    def get_max_charging_power(self, step):
        active = self.get_active_evs(step)
        return sum(ev.max_charging_power for ev in active)

    def step(self, step, allocated_power, dt_hours):
        """
        Distributes allocated power proportionally to active EVs that are not yet fully charged.
        """
        active = [ev for ev in self.get_active_evs(step) if ev.soc < 1.0]
        if not active:
            for ev in self.evs:
                ev.current_charging_power = 0.0
            return 0.0
            
        total_max_p = sum(ev.max_charging_power for ev in active)
        if total_max_p == 0:
            for ev in self.evs:
                ev.current_charging_power = 0.0
            return 0.0
            
        actual_power_delivered = 0.0
        for ev in active:
            # allocate proportionally
            share = ev.max_charging_power / total_max_p
            allocated = allocated_power * share
            ev.charge(allocated, dt_hours)
            actual_power_delivered += ev.current_charging_power
            
        # For non-active or fully charged EVs, power is 0
        for ev in self.evs:
            if ev not in active:
                ev.current_charging_power = 0.0
                
        return actual_power_delivered

    def check_soc_violations(self, step):
        """
        Checks if any EV departing at the current step has violated its target SoC.
        """
        violations = []
        for ev in self.evs:
            if ev.departure_step == step:
                if ev.soc < ev.target_soc:
                    violations.append((ev.id, ev.soc, ev.target_soc))
        return violations
