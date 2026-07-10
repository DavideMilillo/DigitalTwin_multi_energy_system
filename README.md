# Proactive OpenADR Demand Response via Digital Twin Sandboxing

This repository contains the Proof-of-Concept (PoC) implementation of a proactive Digital Twin (DT) sandboxing architecture for demand response in sector-coupled energy systems (Smart Buildings and Electric Vehicle Fleets).

The core innovation is a predictive "What-If" decision engine that evaluates multiple coordinated control schedules upon receiving a flexibility event from the grid, ensuring physical constraints (thermal comfort and EV mobility targets) are met.

---

## 1. Repository Structure

All implementation code is located in the [dt_openadr_poc](./dt_openadr_poc/) directory:

- [config.py](./dt_openadr_poc/config.py): Centralized system parameters, comfort bounds, and EV profiles.
- [run_offline_poc.py](./dt_openadr_poc/run_offline_poc.py): A fast, deterministic 24-hour simulation runner that bypasses the live network clock for reproducible testing.
- [main_simulation.py](./dt_openadr_poc/main_simulation.py): Full live simulation with an integrated background OpenADR VTN server and VEN client.
- **`models/`**: Physical component models.
  - [building_model.py](./dt_openadr_poc/models/building_model.py): Equivalent RC thermal network simulating indoor temperature ($T_{in}$) under HVAC load and external disturbances.
  - [ev_fleet_model.py](./dt_openadr_poc/models/ev_fleet_model.py): Charging fleet tracking connection status, battery SoC constraints, and departure targets.
  - [eta_model.py](./dt_openadr_poc/models/eta_model.py): Dynamic converter and charger efficiency modeled using the standard **Schmidt-Sauer** quadratic loss formulation (see details below).
- **`core/`**: Orchestration logic.
  - [dt_sandbox.py](./dt_openadr_poc/core/dt_sandbox.py): Digital Twin Sandbox engine that performs forward "What-If" lookahead projections.
  - [ems_ven.py](./dt_openadr_poc/core/ems_ven.py): OpenADR Virtual End Node (VEN) client, interfacing the network signal with the DT decision logic.
- **`data/`**:
  - [profiles.csv](./dt_openadr_poc/data/profiles.csv): 24-hour profiles for ambient temperature ($T_{out}$) and building non-HVAC electrical base loads.

---

## 2. Power Electronics Conversion Loss Model

Both building HVAC compressors (inverters) and Electric Vehicle chargers (onboard converters) are modeled with dynamic power conversion efficiencies instead of static values. We employ the standard, peer-reviewed **Schmidt-Sauer** quadratic loss formulation, which models efficiency $\eta(x)$ as a function of the normalized loading ratio $x = P / P_{\text{nom}}$:

$$\eta(x) = \frac{x}{x + p_0 + p_1 x^2}$$

where:
- $p_0$ represents the no-load / self-consumption losses (which dominate at light loads).
- $p_1$ represents the resistive / ohmic copper losses (which scale quadratically with power and dominate at high loads).

### Scientific Reference:
> **Schmidt, H., & Sauer, D. U. (1996).** "Praxisgerechte Modellierung und Abschätzung von Wechselrichter-Wirkungsgraden" (Practice-oriented simulation and assessment of inverter efficiencies). *Sonnenenergie*, 11.

---

## 3. Dynamic Control Strategies

Upon receiving a `LOAD_DISPATCH` signal (representing a target power reduction in kW during peak hours), the Digital Twin Sandbox clones the current physical system states and evaluates three strategies:

1. **Strategy A (EV Only)**: HVAC remains on baseline control. All requested power reduction is absorbed by EV chargers.
2. **Strategy B (Coupled Building + EV)**: Coordinated shedding. HVAC power is reduced first (allowing indoor temperature to float up within comfort limits), and the remainder is shed by EV chargers.
3. **Strategy C (Pre-cooling + Coupled)**: Proactive pre-cooling. Runs HVAC at max power for 4 steps (1 hour) before the event to lower building temperature safely near the lower comfort limit ($T_{min} = 20^\circ\text{C}$). During the event, HVAC is shed completely, utilizing stored thermal energy to prevent comfort violations during peak heat hours.

---

## 4. Installation & Usage

### Prerequisites
Ensure you have a Python environment with the required libraries installed:
```bash
pip install -r requirements.txt
```

### Running the Fast Offline PoC (Recommended for quick results)
To run the deterministic 24-hour simulation with a mock afternoon OpenADR event at 14:00 (peak heat):
```bash
python dt_openadr_poc/run_offline_poc.py
```
This generates a high-resolution comparison plot:
- `dt_openadr_poc/simulation_results_offline.png`
- `dt_openadr_poc/simulation_results_offline.pdf`

### Running the Live OpenADR Simulation
To test the complete server/client workflow using standard HTTP calls on `localhost:8080`:
```bash
python dt_openadr_poc/main_simulation.py
```
This starts a background VTN server, transmits the DR event to the VEN, resolves it via the Digital Twin Sandbox, and runs the physical simulation loop.
