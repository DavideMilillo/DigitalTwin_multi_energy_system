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

3. **Improve the building thermal model**
   - Add internal heat gains (occupancy, lighting, equipment) as a disturbance input in the RC equation
   - Make the HVAC mode dynamic (the model should switch between heating/cooling based on whether T_out > T_in)
   - Consider a deadband control: the HVAC only activates if T_in deviates from setpoint by more than ±0.5°C

4. **Improve the EV fleet model**
   - Add a simple charging efficiency factor (e.g., η_charger = 0.92 for AC chargers)
   - Simulate EV battery degradation guard: charging should taper above 80% SoC (constant-current / constant-voltage profile)
   - Add a flag for "EV not connected" state (SoC is frozen when the EV is not at the charging station)
   - Validate that the minimum SoC required at arrival is also respected as an input constraint

5. **Improve the DT Sandbox dispatch logic**
   - In Strategy A: prioritize EV load reduction for vehicles with more time remaining before departure
   - In Strategy B: implement a gradual HVAC ramping (avoid abrupt setpoint step changes which are unrealistic)
   - Add a third strategy (Strategy C): pre-cooling / pre-heating before the event to build thermal energy storage, then shedding HVAC fully during the event — this is a key innovation for the article
   - Return a score metric from each sandbox run (e.g., total comfort violation degree + EV SoC shortfall) to allow a ranked comparison even when both strategies are infeasible

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