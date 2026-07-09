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

    def step(self, T_out, P_HVAC_elec, dt_hours, mode="cooling"):
        """
        Updates the indoor temperature using discrete-time thermal model:
        T_in(t+1) = T_in(t) + (dt / C_th) * ((T_out(t) - T_in(t)) / R_th - P_HVAC_thermal(t))
        For cooling: P_HVAC_thermal = P_HVAC_elec * COP
        For heating: P_HVAC_thermal = -P_HVAC_elec * COP (cooling drops temp, heating raises it)
        """
        self.P_HVAC = min(max(P_HVAC_elec, 0.0), self.P_HVAC_max)
        
        # Calculate heat gain/loss
        heat_from_outside = (T_out - self.T_in) / self.R_th
        
        if mode == "cooling":
            heat_removed_by_hvac = self.P_HVAC * self.COP
        else:
            # heating mode: HVAC adds heat (so heat removed is negative)
            heat_removed_by_hvac = -self.P_HVAC * self.COP
            
        dT = (dt_hours / self.C_th) * (heat_from_outside - heat_removed_by_hvac)
        self.T_in += dT
        return self.T_in

    def is_comfort_violated(self):
        return self.T_in < self.T_min or self.T_in > self.T_max
