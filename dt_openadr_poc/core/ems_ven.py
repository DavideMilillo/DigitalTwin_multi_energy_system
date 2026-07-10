# core/ems_ven.py
# OpenADR Virtual End Node (VEN) and Energy Management System integration

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from openleadr import OpenADRClient
from core.dt_sandbox import DigitalTwinSandbox
from models.building_model import BuildingThermalModel
from models.ev_fleet_model import EVFleetModel
from config import CONFIG
import numpy as np

class EMSOpenADRNode:
    """
    OpenADR Virtual End Node (VEN) and Energy Management System (EMS).
    """
    def __init__(self, building_model: BuildingThermalModel, ev_fleet_model: EVFleetModel, outdoor_temp_profile: List[float], base_demand_profile: List[float]) -> None:
        """
        Initializes the EMS Node.

        Args:
            building_model (BuildingThermalModel): The building thermal model instance.
            ev_fleet_model (EVFleetModel): The EV fleet model instance.
            outdoor_temp_profile (List[float]): Outdoor temperature profile.
            base_demand_profile (List[float]): Baseline non-HVAC electrical demand.
        """
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
        self.dispatch_results: List[Tuple[str, Dict[str, Any], int, int, int, float]] = []
        self.event_processed = asyncio.Event()

    async def start(self) -> None:
        """
        Starts the OpenADR Client asynchronously.
        """
        print(f"[EMS VEN] Starting OpenADR Client: {self.ven_name} connecting to {self.vtn_url}")
        asyncio.create_task(self.client.run())

    async def handle_event(self, event: Dict[str, Any]) -> str:
        """
        OpenADR event handler. Triggered when the VTN sends an event.
        Extracts peak load reduction requests and uses the Digital Twin Sandbox to evaluate options.

        Args:
            event (Dict[str, Any]): The OpenADR event payload.

        Returns:
            str: Response to the VTN ('optIn' or 'optOut').
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
            
            if not intervals:
                print("[EMS VEN] No intervals in signal.")
                return 'optOut'
                
            # Process multiple intervals if present (e.g. ramp-up, max shed, ramp-down)
            # Find the max shed requirement to simplify the simulation scenario
            max_shed_kW = max(interval.get('signal_payload', 0.0) for interval in intervals)
            
            # Sum up total duration
            total_duration_minutes = sum(interval.get('duration').total_seconds() / 60 for interval in intervals)
            total_duration_steps = int(total_duration_minutes / 15)
            
            # Use the start time of the first interval
            start_time = intervals[0].get('dtstart')

            # Dynamically calculate the start step based on the event's start time hour/minute
            # Assuming the simulation starts at midnight (00:00) with 15-minute steps
            if start_time:
                start_hour = start_time.hour
                start_minute = start_time.minute
                start_step = int((start_hour * 60 + start_minute) / 15)
            else:
                # Default to step 36 (09:00 AM) if no start_time is provided
                start_step = 36
            
            print(f"[EMS VEN] Event Details (Aggregated):")
            print(f"  - Start Step: {start_step} ({start_step * 15 // 60:02d}:{start_step * 15 % 60:02d})")
            print(f"  - Total Duration: {total_duration_steps} steps ({total_duration_minutes:.1f} mins)")
            print(f"  - Max Target Shed Power: {max_shed_kW:.2f} kW")
            
            # Calculate current_step (start of pre-cooling / lookahead window)
            current_step = max(0, start_step - 4)

            # Invoke Digital Twin Sandboxing
            sandbox = DigitalTwinSandbox()
            
            # Evaluate Strategy A (EV Only)
            print("[EMS VEN] Digital Twin simulating Strategy A (EV Only)...")
            feasible_a, traj_a, score_a = sandbox.simulate_scenario(
                self.building, self.ev_fleet, 'A', current_step, start_step, total_duration_steps,
                max_shed_kW, self.base_demand_profile, self.outdoor_temp_profile, self.dt_hours
            )
            
            # Evaluate Strategy B (Coupled HVAC + EV)
            print("[EMS VEN] Digital Twin simulating Strategy B (Coupled Building-EV)...")
            feasible_b, traj_b, score_b = sandbox.simulate_scenario(
                self.building, self.ev_fleet, 'B', current_step, start_step, total_duration_steps,
                max_shed_kW, self.base_demand_profile, self.outdoor_temp_profile, self.dt_hours
            )
            
            # Evaluate Strategy C (Pre-cooling + Coupled)
            print("[EMS VEN] Digital Twin simulating Strategy C (Pre-cooling + Coupled Building-EV)...")
            feasible_c, traj_c, score_c = sandbox.simulate_scenario(
                self.building, self.ev_fleet, 'C', current_step, start_step, total_duration_steps,
                max_shed_kW, self.base_demand_profile, self.outdoor_temp_profile, self.dt_hours
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
                best_strategy = min(feasible_strategies, key=lambda x: x[2])
                print(f"[EMS VEN] Strategy {best_strategy[0]} is feasible with best score. Activating Strategy {best_strategy[0]}.")
                self.dispatch_results.append((best_strategy[0], best_strategy[3], current_step, start_step, total_duration_steps, max_shed_kW))
            else:
                best_strategy = min(strategies, key=lambda x: x[2])
                print(f"[EMS VEN] WARNING: All strategies violate bounds. Choosing Strategy {best_strategy[0]} with minimal impact (Score: {best_strategy[2]:.2f}).")
                self.dispatch_results.append((best_strategy[0], best_strategy[3], current_step, start_step, total_duration_steps, max_shed_kW))
                
            self.event_processed.set()
            return 'optIn'
            
        except Exception as e:
            print(f"[EMS VEN] Error processing event: {e}")
            self.event_processed.set()
            return 'optOut'
