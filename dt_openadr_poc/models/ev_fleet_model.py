# models/ev_fleet_model.py
# Simulates the EV Fleet State of Charge and availability

class EV:
    def __init__(self, ev_id, arrival_step, departure_step, battery_capacity, soc_init, target_soc, max_charging_power, charging_efficiency=0.92):
        self.id = ev_id
        self.arrival_step = arrival_step
        self.departure_step = departure_step
        self.battery_capacity = battery_capacity # kWh

        # Validate minimum SoC at arrival
        if soc_init < 0.0:
            raise ValueError(f"Initial SoC for EV {ev_id} cannot be less than 0.0")
        if soc_init > target_soc:
            print(f"Warning: EV {ev_id} arrives with SoC ({soc_init}) >= target SoC ({target_soc}).")

        self.soc = soc_init
        self.target_soc = target_soc
        self.max_charging_power = max_charging_power # kW
        self.charging_efficiency = charging_efficiency
        self.current_charging_power = 0.0 # kW
        self.is_connected = False

    def update_connection_status(self, step):
        # Determine if EV is plugged in at this step
        self.is_connected = self.arrival_step <= step < self.departure_step
        return self.is_connected

    def is_present(self, step):
        return self.update_connection_status(step)

    def get_charging_limit(self):
        # Simulates battery degradation guard: tapers charging above 80% SoC
        # We linearly taper down from max_charging_power to 20% of max_charging_power as SoC goes from 80% to 100%
        if self.soc >= 0.8:
            taper_factor = max(0.2, 1.0 - (self.soc - 0.8) / 0.2 * 0.8)
            return self.max_charging_power * taper_factor
        return self.max_charging_power

    def charge(self, power_kw, dt_hours):
        # If not connected, cannot charge and SoC is frozen
        if not self.is_connected:
            self.current_charging_power = 0.0
            return self.soc

        # Charge if present and not fully charged
        power_limit = self.get_charging_limit()
        power = min(power_kw, power_limit)

        # Apply charging efficiency
        energy_added = power * self.charging_efficiency * dt_hours
        self.current_charging_power = power  # Power drawn from grid is before efficiency loss
        
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
        return sum(ev.get_charging_limit() for ev in active)

    def get_baseline_power(self, step, dt_hours):
        """
        Calculates the baseline power needed to charge all active EVs to their target SoC.
        """
        active_evs = self.get_active_evs(step)

        baseline_power = 0.0
        for ev in active_evs:
            if ev.soc < ev.target_soc:
                # Energy needed to reach target SoC
                energy_needed = (ev.target_soc - ev.soc) * ev.battery_capacity
                # Account for charging efficiency (need to draw more power from grid to deliver energy to battery)
                energy_to_draw = energy_needed / ev.charging_efficiency
                # Power needed to deliver that energy in one step
                power_needed = energy_to_draw / dt_hours
                # Capped by current charging limit
                baseline_power += min(ev.get_charging_limit(), power_needed)

        return max(0.0, baseline_power)

    def step(self, step, allocated_power, dt_hours, allocation_method="proportional"):
        """
        Distributes allocated power to active EVs that are not yet fully charged.
        """
        active = [ev for ev in self.get_active_evs(step) if ev.soc < 1.0]
        if not active:
            for ev in self.evs:
                ev.current_charging_power = 0.0
            return 0.0
            
        actual_power_delivered = 0.0

        if allocation_method == "proportional":
            total_max_p = sum(ev.get_charging_limit() for ev in active)
            if total_max_p == 0:
                for ev in self.evs:
                    ev.current_charging_power = 0.0
                return 0.0

            for ev in active:
                # allocate proportionally
                share = ev.get_charging_limit() / total_max_p
                allocated = allocated_power * share
                ev.charge(allocated, dt_hours)
                actual_power_delivered += ev.current_charging_power

        elif allocation_method == "priority_departure":
            # Prioritize EVs departing sooner
            active.sort(key=lambda x: x.departure_step)
            remaining_power = allocated_power
            for ev in active:
                allocated = min(ev.get_charging_limit(), remaining_power)
                ev.charge(allocated, dt_hours)
                actual_power_delivered += ev.current_charging_power
                remaining_power -= ev.current_charging_power
                remaining_power = max(0.0, remaining_power)

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
