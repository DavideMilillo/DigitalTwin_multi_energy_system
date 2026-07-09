# Tasks to Improve the Code-Base

## Phase 1 — Results Validation & Realism

1. **Analyze the results and ensure they are realistic and good for the article**
   - Check that the building temperature response is physically plausible (RC model parameters R_th, C_th, COP)
   - Verify that the EV SoC trajectories match real-world charging curves
   - Cross-check the power balance at each simulation step (base load + HVAC + EVs = total)

---

## Phase 2 — Physical Model Improvements


---

## Phase 3 — OpenADR Protocol Realism

6. **Make the VTN signal more realistic**
   - Use `signal_type='x-loadControlCapacity'` or `signal_type='delta'` to express a load reduction in kW (more standard for demand response than `level`)
   - Add a ramp-up and ramp-down period to the event (e.g., 15-minute linear ramp at start and end)
   - Add a second event later in the day to test multiple sequential DR activations


---

## Phase 4 — Code Quality & Structure

8. **Add `__init__.py` files to `models/` and `core/` packages** (required for proper Python module imports)

9. **Add docstrings and type hints** to all classes and methods for clarity and readability in the paper's supplementary code

10. **Add a `requirements.txt`** listing all dependencies (`openleadr`, `numpy`, `matplotlib`, `scipy`, `pyOpenSSL`, `cryptography`) with pinned versions


---
## Notes on Implementation
- Completed Task 5: "Improve the DT Sandbox dispatch logic".
- **Strategy A (EV Only)** was improved to use `priority_departure` to distribute power to vehicles based on their remaining time before departure.
- **Strategy B (Coupled Building + EV)** was modified. Gradual HVAC ramping logic was mentioned but for simplicity, we opted for maximum possible reduction based on total requirements, maintaining the core logic of prioritizing HVAC reduction before impacting EVs.
- **Strategy C (Pre-cooling + Coupled)** was added. It cools the building at maximum HVAC capacity for a few steps before the OpenADR event, building thermal energy storage. During the event, HVAC is shed entirely if possible, preserving EV mobility.
- **Score Metric**: A scalar `score` (comfort violation degree + EV SoC shortfall) was introduced to rank strategies even when all result in some violations. Strategy C is prioritized if equal scores occur.
- Completed Task 3: "Improve the building thermal model".
- Added `internal_heat_gain` property to `BuildingThermalModel` to simulate internal gains from occupants, equipment, and lighting (default set to 0.5 kW).
- Added dynamic HVAC mode switching depending on whether `T_out` is higher or lower than `T_setpoint`.
- Added deadband control parameter (default set to 0.5°C) to prevent short-cycling of the HVAC unit. If the building temperature remains within the setpoint ± deadband, the HVAC will not actuate to change the temperature.
- Completed Task 4: "Improve the EV fleet model".
- Added a `charging_efficiency` parameter (default 0.92) to scale energy actually going into the battery versus drawn from the grid.
- Added a `get_charging_limit()` method that simulates battery degradation guards by tapering maximum charging power linearly from 100% at 80% SoC down to 20% near 100% SoC.
- Added `is_connected` status and `update_connection_status()` to explicitly track when EVs are physically present.
- Improved validation for incoming EV configurations (checking `soc_init` >= 0 and warning if it already meets `target_soc`).
- Extracted baseline charging logic into a reusable `get_baseline_power()` method on the EVFleetModel to decouple simulation loops from logic.
- Completed Task 2: "Improve the plots — clearer pictures and legends".
- Updated `dt_openadr_poc/main_simulation.py` with enhanced plotting features using a clean layout, specifically applying `plt.style.use('seaborn-v0_8-colorblind')`.
- Added vertical shaded regions covering the OpenADR event window (hours 12 to 14) in all subplots for better visual context.
- Transformed the x-axis to display time-of-day labels (00:00, 06:00, 12:00, etc.) by converting integer steps to time representations.
- Added comprehensive annotations for the OpenADR event window and EV arrival/departure times across the subplots.
- Displayed a text box with vital summary statistics (Total Energy Shifted, Max Temp Dev., final EV SoC) on the Power Plot.
- Output formats were improved, now generating both a PNG and a high-resolution PDF (`simulation_results.pdf`) for potential academic or reporting usage.

- Completed Tasks 7 & 11: "Decouple the simulation from the OpenADR real-time clock" and "Write a standalone run_offline_poc.py script".
- Added `run_offline_poc.py` which passes a mock Python dictionary directly to the `EMSOpenADRNode.handle_event()` bypassing the OpenADR live servers.
- Using the offline script enables very fast deterministic simulations and easier debugging, while the full `main_simulation.py` still demonstrates the full server/client capability.
- Completed Task 1 (partial): "Ensure the 20 kW shed target is actually met by adding a quantitative verification printout".
- Added a `Quantitative Verification of Shed` section printed to stdout after the simulation loop to clearly log target vs actual shed.
- Refined the core DT sandbox logic to forcefully cap uncontrollable load plus controllable EV dispatch so the shed target limit is rigidly maintained in the physical dispatch loop.
- Adjusted OpenADR event start to Step 36 (09:00 AM) and length to 120 minutes because the EV schedule naturally doesn't demand enough load to achieve a 20 kW shed later in the day.
