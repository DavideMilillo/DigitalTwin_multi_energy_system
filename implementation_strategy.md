

```markdown
# Implementation Plan: Proactive OpenADR Architecture via DT Sandboxing

## 1. Project Overview
This project is a Proof of Concept (PoC) demonstrating a predictive Digital Twin (DT) integrated with an Energy Management System (EMS). The EMS acts as an OpenADR Virtual End Node (VEN). Upon receiving a flexibility request (e.g., load shedding) from the Virtual Top Node (VTN), the EMS uses the DT as a "sandbox" to simulate "What-If" scenarios. The goal is to perform Sector Coupling: coordinating EV fleet charging and Building HVAC setpoints to meet the grid request without violating user comfort or EV State of Charge (SoC) requirements.

## 2. Directory Structure
```text
dt_openadr_poc/
│
├── models/
│   ├── __init__.py
│   ├── building_model.py    # Thermal dynamics of the building
│   └── ev_fleet_model.py    # EV fleet SoC and availability tracking
│
├── core/
│   ├── __init__.py
│   ├── dt_sandbox.py        # The Digital Twin simulation engine
│   └── ems_ven.py           # The OpenADR interface and decision logic
│
├── data/
│   └── profiles.csv         # Synthetic input data (Prices, T_out, EV schedules)
│
├── main_simulation.py       # 24h loop execution and plotting
└── implementation_strategy.md   # strategic roadmap for the code-base


## 3. Module Specifications

### Phase 1: Physical Models (`models/`)

**A. `building_model.py**`

* **Class:** `BuildingThermalModel`
* **Purpose:** Simulates the indoor temperature based on a simplified Equivalent RC (Resistance-Capacitance) thermal network.
* **Key Equation:** Implement a discrete-time thermal update:

$$T_{in}(t+1) = T_{in}(t) + \frac{\Delta t}{C_{th}} \left( \frac{T_{out}(t) - T_{in}(t)}{R_{th}} \pm P_{HVAC}(t) \cdot COP \right)$$


* **Constraints:** Comfort bounds (e.g., $20^\circ\text{C} \le T_{in} \le 24^\circ\text{C}$).

**B. `ev_fleet_model.py**`

* **Class:** `EVFleetModel`
* **Purpose:** Tracks aggregated SoC of parked EVs.
* **Key Variables:** `arrival_time`, `departure_time`, `target_SoC`, `max_charging_power`.
* **Logic:** Updates SoC based on applied charging power $P_{EV}(t)$. Must strictly flag if a requested power profile fails to meet the `target_SoC` at `departure_time`.

### Phase 2: The Core Logic (`core/`)

**C. `dt_sandbox.py**`

* **Class:** `DigitalTwinSandbox`
* **Purpose:** Takes copies (deepcopies) of the current state of `BuildingThermalModel` and `EVFleetModel`.
* **Methods:** `simulate_scenario(strategy, duration, power_reduction_target)`
* *Strategy A (EV Only):* Cuts $P_{EV}$ to meet the target. Simulates if target SoC is violated.
* *Strategy B (Coupled):* Cuts $P_{HVAC}$ exploiting thermal inertia, and cuts $P_{EV}$ only for the remainder. Simulates if $T_{in}$ bounds or SoC are violated.


* **Output:** Returns a feasibility boolean and the projected state trajectories for the next $N$ steps.

**D. `ems_ven.py**`

* **Class:** `EMSOpenADRNode`
* **Purpose:** Receives the mock VTN signal.
* **Logic:** 1. Parse event (e.g., `{"time": "14:00", "duration_minutes": 120, "shed_kW": 40}`).
2. Call `dt_sandbox` with Strategy A.
3. Call `dt_sandbox` with Strategy B.
4. Evaluate results: prioritize Strategy B (Sector Coupling) if comfort constraints hold, as it preserves EV mobility.
5. Return the chosen optimal power dispatch arrays for HVAC and EV.

### Phase 3: Execution and Visualization

**E. `main_simulation.py**`

* **Setup:** Initialize models with assumed parameters (e.g., $R_{th}$, $C_{th}$, EV capacity). Create a synthetic 24h time-series (15-min resolution) for $T_{out}$ and base load.
* **Event:** Trigger an OpenADR shed event at a specific time (e.g., peak price hour).
* **Execution:** Run the time loop. When the event hits, invoke the EMS, which consults the DT, and apply the chosen dispatch.
* **Plotting (Matplotlib):** Generate a multi-subplot figure:
1. Total Power Profile (Baseline vs. DT-Optimized, showing the grid limit).
2. Building Temperature ($T_{in}$ vs. Comfort Bounds).
3. EV Fleet SoC trajectory.

***
'''



