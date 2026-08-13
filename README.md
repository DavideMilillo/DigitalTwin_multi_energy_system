# Proactive OpenADR Demand Response via Digital Twin Sandboxing

This repository contains the Proof-of-Concept (PoC) implementation of a proactive Digital Twin (DT) sandboxing architecture for demand response in sector-coupled energy systems (Smart Commercial Buildings and Electric Vehicle Fleets).

The core innovation is a predictive "What-If" decision engine embedded within an OpenADR 2.0b Virtual End Node (VEN). Upon receiving a grid flexibility request, the engine instantiates deep-copied state replicas of local physical assets to evaluate candidate multi-vector control strategies in forward projection before committing any physical dispatch action.

---

## 1. Repository Structure

All implementation code is located in the [dt_openadr_poc](./dt_openadr_poc/) directory:

- [config.py](./dt_openadr_poc/config.py): Centralized system parameters, building thermal properties, comfort bounds, and EV fleet profiles.
- [run_offline_poc.py](./dt_openadr_poc/run_offline_poc.py): A fast, deterministic 24-hour simulation runner that evaluates sequential OpenADR events and generates publication figures.
- [plot_strategy_comparison.py](./dt_openadr_poc/plot_strategy_comparison.py): Dedicated script to simulate and generate publication-quality matrix/overlaid comparison plots across Strategies A, B, and C.
- [main_simulation.py](./dt_openadr_poc/main_simulation.py): Full live simulation with an integrated background OpenADR VTN server and VEN client communication layer.
- **`models/`**: Physical component models.
  - [building_model.py](./dt_openadr_poc/models/building_model.py): Equivalent Thermal Parameter (ETP) circuit simulating indoor temperature ($T_{in}$) under HVAC cooling load, ambient temperature ($T_{out}$), and internal heat gains.
  - [ev_fleet_model.py](./dt_openadr_poc/models/ev_fleet_model.py): Multi-vehicle EV fleet tracking arrival/departure schedules, battery SoC dynamics, constant-voltage charging taper, and priority-departure power allocation.
  - [eta_model.py](./dt_openadr_poc/models/eta_model.py): Dynamic converter and charger efficiency modeled using the analytical **de Mango / Schmidt-Sauer** quadratic loss formulation.
- **`core/`**: Orchestration and OpenADR logic.
  - [dt_sandbox.py](./dt_openadr_poc/core/dt_sandbox.py): Digital Twin Sandbox engine performing parallel forward "What-If" lookahead projections and scoring strategy feasibility ($J_s$).
  - [ems_ven.py](./dt_openadr_poc/core/ems_ven.py): OpenADR 2.0b Virtual End Node (VEN) client, interfacing OpenADR signals with the DT decision engine.
- **`data/`**:
  - [profiles.csv](./dt_openadr_poc/data/profiles.csv): 24-hour synthetic profiles for outdoor temperature ($T_{out}$) and building non-HVAC electrical base load.

---

## 2. Power Electronics Conversion Loss Model

Both building HVAC compressor drives (inverters) and Electric Vehicle chargers (on-board converters) are modeled with dynamic power-dependent conversion efficiencies rather than constant values. We employ the peer-reviewed **de Mango / Schmidt-Sauer** quadratic loss formulation, modeling efficiency $\eta(x)$ as a function of the normalized loading ratio $x = P / P_{\text{nom}}$:

$$\eta(x) = \frac{x}{x + p_0 + p_1 x^2}$$

where:
- $p_0 = 0.015$ represents no-load / self-consumption losses (dominant at light loading).
- $p_1 = 0.025$ represents resistive / ohmic copper losses (scaling quadratically with power, dominant at high loading).

---

## 3. Evaluated Control Strategies

Upon receiving an OpenADR `LOAD_DISPATCH` signal (representing a target power reduction $\Delta P_{\text{target}}$ in kW), the Digital Twin Sandbox clones the current physical system states and evaluates three candidate strategies:

1. **Strategy A (EV-Only Curtailment)**: HVAC remains on baseline thermostat control ($T_{in} \in [22.59^\circ\text{C}, 23.24^\circ\text{C}]$). 100% of the required demand reduction is absorbed by EV chargers. While feasible, it results in heavy EV curtailment (32.6 kWh).
2. **Strategy B (Coupled Building + EV)**: Coordinated shedding. HVAC power is shut off completely during the event without prior pre-cooling. This causes thermal comfort violations ($T_{in}$ reaches up to $24.83^\circ\text{C} > T_{\text{max}} = 24.0^\circ\text{C}$), rendering the strategy **infeasible**.
3. **Strategy C (Pre-cooling + Coupled)**: Proactive multi-vector coordination. The engine runs HVAC at max power ($P_{\text{HVAC,max}} = 12$ kW) for 4 time steps (1 hour) before the event to pre-cool the building thermal mass down to $20.90^\circ\text{C}$. During the event, HVAC is shed completely while stored thermal inertia absorbs incoming heat. The HVAC load shed frees up electrical headroom for EV charging, saving 4.6 kWh (14%) of EV charging energy compared to Strategy A.

---

## 4. Key Physical Findings

- **Thermal Buffer Proactivity**: Thermal energy storage in building envelopes is only accessible through *proactive* pre-cooling (Strategy C). Reactive rule-based shedding (Strategy B) leads to thermal comfort violations.
- **Physical Feasibility Floor**: In evening events (e.g., Event 2 at 20:00, baseline load = 14 kW, requested shed = 15 kW), the minimum achievable demand is bounded by the uncontrollable base load (8 kW). Load-shedding demand response cannot reduce consumption below this physical floor, motivating future Vehicle-to-Grid (V2G) integration.

---

## 5. Installation & Usage

### Prerequisites
Install dependencies using Python 3.10+:
```bash
pip install -r requirements.txt
```

### 1. Run Strategy Comparison & Matrix Plotter
To generate side-by-side and overlaid comparison plots across Strategies A, B, and C:
```bash
python dt_openadr_poc/plot_strategy_comparison.py
```
Outputs saved in `dt_openadr_poc/`:
- `strategy_comparison_matrix.png` / `.pdf`
- `strategy_comparison_overlaid.png` / `.pdf`

### 2. Run Offline 24-Hour Simulation & Verification
To run the full deterministic simulation with sequential OpenADR events (14:00 and 20:00) and verify quantitative shed compliance:
```bash
python dt_openadr_poc/run_offline_poc.py
```
Outputs saved in `dt_openadr_poc/`:
- `simulation_results_offline.png` / `.pdf`

### 3. Run Live Networked OpenADR Simulation
To test the complete VTN/VEN network communication workflow over HTTP:
```bash
python dt_openadr_poc/main_simulation.py
```




### Digital Twin Architecture and Anatomy for multy energy system digitral Twin Sandobxing

Image from NotebookLM
<img width="1376" height="768" alt="Multi-Energy_Digital_Twins_-_Slide_4" src="https://github.com/user-attachments/assets/fb502730-1ed7-42b1-ba95-f1814afadb34" />


