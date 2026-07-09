# Tasks to Improve the Code-Base

## Phase 1 — Results Validation & Realism

1. **Analyze the results and ensure they are realistic and good for the article**
   - Check that the building temperature response is physically plausible (RC model parameters R_th, C_th, COP)
   - Verify that the EV SoC trajectories match real-world charging curves
   - Cross-check the power balance at each simulation step (base load + HVAC + EVs = total)
   - Ensure the 20 kW shed target is actually met (not just "approximately" reduced) by adding a quantitative verification printout

2. **Improve the plots — clearer pictures and legends**
   - Add vertical shaded region to highlight the OpenADR event window in all subplots
   - Use better color palette (colorblind-friendly, e.g. seaborn or matplotlib style sheets)
   - Add time-of-day labels on the x-axis (00:00, 06:00, 12:00, 18:00, 24:00)
   - Annotate the plots with key events: EV arrival/departure times, OpenADR event start/end
   - Add a text box showing the PoC summary statistics (total energy shifted, max temp deviation, EV SoC at departure)
   - Export plots as high-resolution PDF (for the article) alongside the PNG

---

## Phase 2 — Physical Model Improvements


---

## Phase 3 — OpenADR Protocol Realism

6. **Make the VTN signal more realistic**
   - Use `signal_type='x-loadControlCapacity'` or `signal_type='delta'` to express a load reduction in kW (more standard for demand response than `level`)
   - Add a ramp-up and ramp-down period to the event (e.g., 15-minute linear ramp at start and end)
   - Add a second event later in the day to test multiple sequential DR activations

7. **Decouple the simulation from the OpenADR real-time clock**
   - Currently the simulation uses the real wall-clock time to schedule events, which makes testing slow
   - Implement an "offline" / "mock" mode: the VTN event is pre-defined as a Python dict and injected directly into the EMS handler without running an actual HTTP server — this speeds up testing and is more suitable for a journal paper PoC

---

## Phase 4 — Code Quality & Structure

8. **Add `__init__.py` files to `models/` and `core/` packages** (required for proper Python module imports)

9. **Add docstrings and type hints** to all classes and methods for clarity and readability in the paper's supplementary code

10. **Add a `requirements.txt`** listing all dependencies (`openleadr`, `numpy`, `matplotlib`, `scipy`, `pyOpenSSL`, `cryptography`) with pinned versions

11. **Write a standalone `run_offline_poc.py`** script that runs the full PoC without needing a live OpenADR server — useful for reproducibility and quick article demonstrations


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
