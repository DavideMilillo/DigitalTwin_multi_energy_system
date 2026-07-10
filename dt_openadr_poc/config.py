# config.py
# System parameters for the Proactive OpenADR PoC via DT Sandboxing

CONFIG = {
    # General Simulation Settings
    "dt_hours": 0.25,        # 15-minute steps (0.25 hours)
    "steps_per_day": 96,     # 24h / 15-min = 96 steps
    
    # Building Thermal Parameters (cooling/summer scenario defaults)
    "building": {
        "R_th": 1.5,         # Thermal resistance (°C/kW)
        "C_th": 6.0,         # Thermal capacitance (kWh/°C)
        "COP": 3.0,          # Coefficient of Performance (Cooling/HP)
        "T_min": 20.0,       # Comfort minimum limit (°C)
        "T_max": 24.0,       # Comfort maximum limit (°C)
        "T_in_init": 22.0,   # Initial indoor temperature (°C)
        "P_HVAC_max": 12.0,  # Max electrical power of HVAC (kW)
        "P_HVAC_baseline": 6.0, # Baseline electrical power (kW)
    },
    
    # EV Fleet Settings
    "ev_fleet": {
        "charging_efficiency": 0.92, # Default fleet charging efficiency
        "evs": [
            {
                "id": "EV1",
                "arrival_step": 32,      # 08:00
                "departure_step": 72,    # 18:00
                "battery_capacity": 50.0, # kWh
                "soc_init": 0.3,         # 30% initial SoC
                "target_soc": 0.85,      # 85% target at departure
                "max_charging_power": 11.0 # kW (standard AC charger)
            },
            {
                "id": "EV2",
                "arrival_step": 36,      # 09:00
                "departure_step": 68,    # 17:00
                "battery_capacity": 60.0, # kWh
                "soc_init": 0.2,
                "target_soc": 0.9,
                "max_charging_power": 22.0 # kW
            },
            {
                "id": "EV3",
                "arrival_step": 40,      # 10:00
                "departure_step": 80,    # 20:00
                "battery_capacity": 40.0, # kWh
                "soc_init": 0.4,
                "target_soc": 0.8,
                "max_charging_power": 7.4 # kW
            },
            {
                "id": "EV4",
                "arrival_step": 52,      # 13:00
                "departure_step": 84,    # 21:00
                "battery_capacity": 75.0, # kWh
                "soc_init": 0.1,         # 10% initial SoC
                "target_soc": 0.8,       # 80% target at departure
                "max_charging_power": 22.0 # kW
            }
        ]
    },
    
    # OpenADR configuration
    "openadr": {
        "vtn_url": "http://127.0.0.1:8080/OpenADR2/Simple/2.0b",
        "ven_name": "ProactiveBuildingVEN",
        "vtn_id": "DT_Sandbox_VTN",
        "http_port": 8080
    }
}
