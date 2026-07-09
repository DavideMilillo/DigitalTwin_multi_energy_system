# models/building_model.py
# Simulates the building thermal dynamics based on an Equivalent RC network

class BuildingThermalModel:
    def __init__(self, R_th, C_th, COP, T_min, T_max, T_in_init, P_HVAC_max, P_HVAC_baseline):
        self.R_th = R_th         # Thermal resistance (°C/kW)
        self.C_th = C_th         # Thermal capacitance (kWh/°C)
        self.COP = COP           # Coefficient of Performance (Cooling/HP)
        self.T_min = T_min       # Min comfort temperature (°C)
        self.T_max = T_max       # Max comfort temperature (°C)
        self.T_in = T_in_init     # Current indoor temperature (°C)
        self.P_HVAC_max = P_HVAC_max # Max HVAC electrical power (kW)
        self.P_HVAC_baseline = P_HVAC_baseline # Baseline/standard HVAC electrical power (kW)
        self.P_HVAC = P_HVAC_baseline # Current HVAC electrical consumption (kW)
        self.internal_heat_gain = 0.5 # Default internal heat gain in kW (e.g. from occupancy, lighting)
        self.T_setpoint = (T_min + T_max) / 2.0
        self.deadband = 0.5 # Deadband of +/- 0.5°C

    def step(self, T_out, P_HVAC_elec, dt_hours, mode="cooling"):
        """
        Updates the indoor temperature using discrete-time thermal model:
        T_in(t+1) = T_in(t) + (dt / C_th) * ((T_out(t) - T_in(t)) / R_th + Q_internal - P_HVAC_thermal(t))
        For cooling: P_HVAC_thermal = P_HVAC_elec * COP
        For heating: P_HVAC_thermal = -P_HVAC_elec * COP (cooling drops temp, heating raises it)
        """
        # Dynamic mode based on T_out and T_in
        if T_out > self.T_setpoint:
            dynamic_mode = "cooling"
        else:
            dynamic_mode = "heating"

        # Deadband control
        # If the temperature is within the deadband, HVAC does not activate
        if abs(self.T_in - self.T_setpoint) <= self.deadband:
            actual_P_HVAC_elec = 0.0
        else:
            # Check if HVAC is working in the "right" direction to restore setpoint
            # E.g., if we are in cooling mode (T_out > setpoint) but T_in is below setpoint - deadband, we don't cool
            # Actually, standard deadband just checks if we exceeded the threshold.
            if dynamic_mode == "cooling" and self.T_in < self.T_setpoint - self.deadband:
                actual_P_HVAC_elec = 0.0
            elif dynamic_mode == "heating" and self.T_in > self.T_setpoint + self.deadband:
                actual_P_HVAC_elec = 0.0
            else:
                actual_P_HVAC_elec = P_HVAC_elec

        self.P_HVAC = min(max(actual_P_HVAC_elec, 0.0), self.P_HVAC_max)
        
        # Calculate heat gain/loss
        heat_from_outside = (T_out - self.T_in) / self.R_th
        heat_internal = self.internal_heat_gain
        
        if dynamic_mode == "cooling":
            heat_removed_by_hvac = self.P_HVAC * self.COP
        else:
            # heating mode: HVAC adds heat (so heat removed is negative)
            heat_removed_by_hvac = -self.P_HVAC * self.COP
            
        dT = (dt_hours / self.C_th) * (heat_from_outside + heat_internal - heat_removed_by_hvac)
        self.T_in += dT
        return self.T_in

    def is_comfort_violated(self):
        return self.T_in < self.T_min or self.T_in > self.T_max
