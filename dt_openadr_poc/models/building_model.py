# models/building_model.py
# Simulates the building thermal dynamics based on an Equivalent RC network

class BuildingThermalModel:
    """
    Simulates the building thermal dynamics based on an Equivalent RC network.
    """

    def __init__(self, R_th: float, C_th: float, COP: float, T_min: float, T_max: float, T_in_init: float, P_HVAC_max: float, P_HVAC_baseline: float) -> None:
        """
        Initializes the building thermal model.

        Args:
            R_th (float): Thermal resistance (°C/kW).
            C_th (float): Thermal capacitance (kWh/°C).
            COP (float): Coefficient of Performance (Cooling/HP).
            T_min (float): Min comfort temperature (°C).
            T_max (float): Max comfort temperature (°C).
            T_in_init (float): Initial indoor temperature (°C).
            P_HVAC_max (float): Max HVAC electrical power (kW).
            P_HVAC_baseline (float): Baseline/standard HVAC electrical power (kW).
        """
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
        
        # Instantiate converter efficiency curve from the old codebase
        from models.eta_model import ConverterEfficiency
        self.eta_calculator = ConverterEfficiency()
        self.eta_hvac = 1.0

    def step(self, T_out: float, P_HVAC_elec: float, dt_hours: float, mode: str = "cooling", control_override: bool = False) -> float:
        """
        Updates the indoor temperature using discrete-time thermal model.

        Equation:
        T_in(t+1) = T_in(t) + (dt / C_th) * ((T_out(t) - T_in(t)) / R_th + Q_internal - P_HVAC_thermal(t))
        For cooling: P_HVAC_thermal = P_HVAC_elec * COP
        For heating: P_HVAC_thermal = -P_HVAC_elec * COP (cooling drops temp, heating raises it)

        Args:
            T_out (float): Outdoor temperature (°C).
            P_HVAC_elec (float): Requested HVAC electrical power (kW).
            dt_hours (float): Time step in hours.
            mode (str): Mode of operation (default: "cooling").
            control_override (bool): If True, bypass deadband controls and apply commanded power directly.

        Returns:
            float: Updated indoor temperature (°C).
        """
        # Dynamic mode based on T_out and T_in
        if T_out > self.T_setpoint:
            dynamic_mode = "cooling"
        else:
            dynamic_mode = "heating"

        # Deadband control
        if control_override:
            actual_P_HVAC_elec = P_HVAC_elec
        else:
            # If the temperature is within the deadband, HVAC does not activate
            if abs(self.T_in - self.T_setpoint) <= self.deadband:
                actual_P_HVAC_elec = 0.0
            else:
                # Check if HVAC is working in the "right" direction to restore setpoint
                if dynamic_mode == "cooling" and self.T_in < self.T_setpoint - self.deadband:
                    actual_P_HVAC_elec = 0.0
                elif dynamic_mode == "heating" and self.T_in > self.T_setpoint + self.deadband:
                    actual_P_HVAC_elec = 0.0
                else:
                    actual_P_HVAC_elec = P_HVAC_elec

        self.P_HVAC = min(max(actual_P_HVAC_elec, 0.0), self.P_HVAC_max)
        
        # Calculate dynamic HVAC converter efficiency based on compressor loading ratio
        ratio = self.P_HVAC / self.P_HVAC_max if self.P_HVAC_max > 0 else 0.0
        self.eta_hvac = self.eta_calculator.calculate_efficiency(ratio)
        
        # Calculate heat gain/loss
        heat_from_outside = (T_out - self.T_in) / self.R_th
        heat_internal = self.internal_heat_gain
        
        if dynamic_mode == "cooling":
            heat_removed_by_hvac = self.P_HVAC * self.COP * self.eta_hvac
        else:
            # heating mode: HVAC adds heat (so heat removed is negative)
            heat_removed_by_hvac = -self.P_HVAC * self.COP * self.eta_hvac
            
        dT = (dt_hours / self.C_th) * (heat_from_outside + heat_internal - heat_removed_by_hvac)
        self.T_in += dT
        return self.T_in

    def is_comfort_violated(self) -> bool:
        """
        Checks if the current indoor temperature violates the comfort bounds.

        Returns:
            bool: True if comfort is violated, False otherwise.
        """
        return self.T_in < self.T_min or self.T_in > self.T_max
