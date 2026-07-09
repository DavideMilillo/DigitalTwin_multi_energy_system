# core/ems_ven.py
# OpenADR Virtual End Node (VEN) and Energy Management System integration

import asyncio
from openleadr import OpenADRClient
from core.dt_sandbox import DigitalTwinSandbox
from config import CONFIG
import numpy as np

class EMSOpenADRNode:
    def __init__(self, building_model, ev_fleet_model, outdoor_temp_profile, base_demand_profile):
        self.building = building_model
        self.ev_fleet = ev_fleet_model
        self.outdoor_temp_profile = outdoor_temp_profile
        self.base_demand_profile = base_demand_profile
        self.dt_hours = CONFIG["dt_hours"]
        self.steps_per_day = CONFIG["steps_per_day"]
        
        # OpenADR configuration
        self.ven_name = CONFIG["openadr"]["ven_name"]
        self.vtn_url = CONFIG["openadr"]["vtn_url"]
        
        self.client = OpenADRClient(
            ven_name=self.ven_name,
            vtn_url=self.vtn_url,
            debug=False
        )
        self.client.add_handler('on_event', self.handle_event)
        
        # Result log of the chosen dispatch strategy
        self.dispatch_result = None
        self.event_processed = asyncio.Event()

    async def start(self):
        print(f"[EMS VEN] Starting OpenADR Client: {self.ven_name} connecting to {self.vtn_url}")
        asyncio.create_task(self.client.run())

    async def handle_event(self, event):
        """
        OpenADR event handler. Triggered when the VTN sends an event.
        Extracts peak load reduction requests and uses the Digital Twin Sandbox to evaluate options.
        """
        print("\n[EMS VEN] RECEIVED OPENADR EVENT!")
        try:
            signals = event.get('event_signals', [])
            if not signals:
                print("[EMS VEN] No signals in event.")
                return 'optOut'
                
            signal = signals[0]
            intervals = signal.get('intervals', [])
            print(f"[EMS VEN] Signal Name: {signal.get('signal_name')}, Type: {signal.get('signal_type')}")
            
            # For simplicity, we assume the first interval is the demand response event
            # We map its time to our simulation step (15-min intervals starting at 00:00)
            if not intervals:
                print("[EMS VEN] No intervals in signal.")
                return 'optOut'
                
            # Get event start and duration
            start_time = intervals[0]['dtstart']
            duration = intervals[0]['duration']
            shed_kW = intervals[0]['signal_payload']
            
            # Map start time to simulation steps (each step is 15 minutes / 0.25 hours)
            # For this PoC, we will simulate the event window starting at step 36 (09:00) for 16 steps (4 hours)
            # as a standard scenario. Let's parse actual start index from config or hardcode the mapping.
            # In our main simulation, we will trigger it for a specific window.
            # Let's say the event is 4 hours (16 steps), starting at step 48 (12:00 PM).
            # We'll map the duration to simulation step count.
            duration_minutes = duration.total_seconds() / 60
            duration_steps = int(duration_minutes / 15)
            
            # Assume starting step is 44 (11:00 AM) for this event
            start_step = 44
            
            print(f"[EMS VEN] Event Details:")
            print(f"  - Start Step: {start_step} ({start_step * 15 // 60:02d}:{start_step * 15 % 60:02d})")
            print(f"  - Duration: {duration_steps} steps ({duration_minutes:.1f} mins)")
            print(f"  - Target Shed Power: {shed_kW:.2f} kW")
            
            # Invoke Digital Twin Sandboxing
            sandbox = DigitalTwinSandbox()
            
            # Evaluate Strategy A (EV Only)
            print("[EMS VEN] Digital Twin simulating Strategy A (EV Only)...")
            feasible_a, traj_a = sandbox.simulate_scenario(
                self.building, self.ev_fleet, 'A', start_step, duration_steps, 
                shed_kW, self.base_demand_profile, self.outdoor_temp_profile, self.dt_hours
            )
            
            # Evaluate Strategy B (Coupled HVAC + EV)
            print("[EMS VEN] Digital Twin simulating Strategy B (Coupled Building-EV)...")
            feasible_b, traj_b = sandbox.simulate_scenario(
                self.building, self.ev_fleet, 'B', start_step, duration_steps, 
                shed_kW, self.base_demand_profile, self.outdoor_temp_profile, self.dt_hours
            )
            
            print(f"[EMS VEN] DT Sandbox Results:")
            print(f"  - Strategy A (EV Only) Feasible: {feasible_a}")
            if not feasible_a:
                print(f"    Violations: {traj_a['violation_details']}")
            print(f"  - Strategy B (Coupled) Feasible: {feasible_b}")
            if not feasible_b:
                print(f"    Violations: {traj_b['violation_details']}")

            # Decision Logic: Prioritize Coupled Strategy B if feasible to protect EV mobility
            selected_strategy = 'B'
            if feasible_b:
                print("[EMS VEN] Strategy B (Coupled) is feasible. Activating Sector Coupling.")
                self.dispatch_result = ('B', traj_b, start_step, duration_steps, shed_kW)
            elif feasible_a:
                print("[EMS VEN] Strategy B failed comfort/SoC bounds. Strategy A is feasible. Activating EV Only.")
                selected_strategy = 'A'
                self.dispatch_result = ('A', traj_a, start_step, duration_steps, shed_kW)
            else:
                print("[EMS VEN] WARNING: Both strategies violate bounds. Choosing Strategy B with minimal impact.")
                self.dispatch_result = ('B', traj_b, start_step, duration_steps, shed_kW)
                
            self.event_processed.set()
            return 'optIn'
            
        except Exception as e:
            print(f"[EMS VEN] Error processing event: {e}")
            self.event_processed.set()
            return 'optOut'
