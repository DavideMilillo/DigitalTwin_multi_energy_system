# sensitivity_sweep.py
# Synthetic sensitivity / scenario sweep for the Digital Twin Sandbox.
#
# Addresses Reviewer 1, Comment 2: the PoC used only two events. This script
# strengthens generalizability by running the EXISTING sandbox across many
# synthetic scenarios, varying one factor at a time around the PoC baseline,
# and summarizing feasibility, the chosen strategy, and the EV charging energy
# saved by the chosen strategy relative to a no-DR baseline.
#
# It reuses the existing physics (no reimplementation) and invents no numbers:
# every value comes from an actual simulate_scenario call.
#
# Run (from this directory):
#   & 'C:\Users\david\anaconda3\envs\energy_AI\python.exe' sensitivity_sweep.py

import os
import sys
import csv
import copy

import numpy as np
import matplotlib.pyplot as plt

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import CONFIG
from models.building_model import BuildingThermalModel
from models.ev_fleet_model import EVFleetModel
from core.dt_sandbox import DigitalTwinSandbox

HERE = os.path.dirname(os.path.abspath(__file__))

# --- PoC baseline (hold these while sweeping one factor) --------------------
BASE = {
    "temp_shift": 0.0,   # degC added to the whole outdoor profile
    "C_th": CONFIG["building"]["C_th"],   # 6.0
    "R_th": CONFIG["building"]["R_th"],   # 1.5
    "target": 20.0,      # kW requested reduction
    "duration": 8,       # steps (2 h)
}
CURRENT_STEP = 52        # 13:00 notification
START_STEP = 56          # 14:00 event start
DT = CONFIG["dt_hours"]  # 0.25
STRATS = ["A", "B", "C"]
TIE_ORDER = {"C": 0, "B": 1, "A": 2}   # C preferred


def load_profiles():
    path = os.path.join(HERE, "data", "profiles.csv")
    T_out, base = [], []
    with open(path, "r") as f:
        for row in csv.DictReader(f):
            T_out.append(float(row["T_out"]))
            base.append(float(row["base_load"]))
    return np.array(T_out), np.array(base)


def make_building(C_th, R_th):
    b = CONFIG["building"]
    return BuildingThermalModel(
        R_th=R_th, C_th=C_th, COP=b["COP"],
        T_min=b["T_min"], T_max=b["T_max"], T_in_init=b["T_in_init"],
        P_HVAC_max=b["P_HVAC_max"], P_HVAC_baseline=b["P_HVAC_baseline"],
    )


def make_fleet():
    return EVFleetModel(copy.deepcopy(CONFIG["ev_fleet"]["evs"]))


def ev_baseline_power_over(fleet_cfg, c_step, e_step):
    """No-DR EV power per step over [c_step, e_step): proportional allocation,
    no curtailment. Mirrors run_offline_poc.py baseline usage."""
    f = EVFleetModel(copy.deepcopy(fleet_cfg))
    # advance to c_step under baseline
    for s in range(c_step):
        f.step(s, f.get_baseline_power(s, DT), DT, allocation_method="proportional")
    powers = []
    for s in range(c_step, e_step):
        p = f.step(s, f.get_baseline_power(s, DT), DT, allocation_method="proportional")
        powers.append(p)
    return np.array(powers)


def run_scenario(temp_shift, C_th, R_th, target, duration):
    """Evaluate strategies A,B,C for one scenario. Returns a result dict."""
    T_out, base = load_profiles()
    T_out = T_out + temp_shift

    end_step = START_STEP + duration
    sandbox = DigitalTwinSandbox()

    res = {"feasible": {}, "J": {}, "traj": {}}
    for strat in STRATS:
        b = make_building(C_th, R_th)
        f = make_fleet()
        # advance real state to the notification step so the sandbox starts
        # from the PoC's 13:00 condition
        for s in range(CURRENT_STEP):
            b.step(T_out[s], b.P_HVAC_baseline, DT, mode="cooling")
            f.step(s, f.get_baseline_power(s, DT), DT, allocation_method="proportional")
        feasible, traj, score = sandbox.simulate_scenario(
            b, f, strat, CURRENT_STEP, START_STEP, duration, target,
            base.tolist(), T_out.tolist(), DT,
        )
        res["feasible"][strat] = feasible
        res["J"][strat] = score
        res["traj"][strat] = traj

    # choose strategy: prefer feasible by C>B>A; else min J, ties C>B>A
    feas = [s for s in STRATS if res["feasible"][s]]
    if feas:
        chosen = sorted(feas, key=lambda s: TIE_ORDER[s])[0]
        chosen_feasible = True
    else:
        min_j = min(res["J"][s] for s in STRATS)
        cands = [s for s in STRATS if abs(res["J"][s] - min_j) < 1e-9]
        chosen = sorted(cands, key=lambda s: TIE_ORDER[s])[0]
        chosen_feasible = False

    # EV energy curtailed by chosen vs no-DR baseline over the event window
    ev_base = ev_baseline_power_over(CONFIG["ev_fleet"]["evs"], START_STEP, end_step)
    traj = res["traj"][chosen]
    # trajectories cover [CURRENT_STEP, end_step); slice the event window
    offset = START_STEP - CURRENT_STEP
    ev_chosen = np.array(traj["ev_power"])[offset:offset + duration]
    if len(ev_chosen) == len(ev_base):
        ev_curtailed_kwh = float(np.sum(ev_base - ev_chosen) * DT)
    else:
        ev_curtailed_kwh = None  # do not fabricate on mismatch

    return {
        "feasible": res["feasible"], "J": res["J"],
        "chosen": chosen, "chosen_feasible": chosen_feasible,
        "ev_curtailed_kwh": ev_curtailed_kwh,
    }


def build_sweeps():
    return {
        "temp_shift": [-4.0, -2.0, 0.0, 2.0, 4.0],
        "C_th": [3.0, 6.0, 9.0],
        "R_th": [1.0, 1.5, 2.0],
        "target": [10.0, 15.0, 20.0, 25.0],
        "duration": [4, 8, 12],
    }


def main():
    sweeps = build_sweeps()
    rows = []
    J_by_factor = {}  # factor -> (values, {strat: [J...]})

    for factor, values in sweeps.items():
        js = {s: [] for s in STRATS}
        for v in values:
            params = dict(BASE)
            params[factor] = v
            r = run_scenario(params["temp_shift"], params["C_th"], params["R_th"],
                             params["target"], params["duration"])
            for s in STRATS:
                js[s].append(r["J"][s])
            rows.append({
                "sweep_factor": factor,
                "factor_value": v,
                "feasible_A": r["feasible"]["A"], "J_A": round(r["J"]["A"], 4),
                "feasible_B": r["feasible"]["B"], "J_B": round(r["J"]["B"], 4),
                "feasible_C": r["feasible"]["C"], "J_C": round(r["J"]["C"], 4),
                "chosen_strategy": r["chosen"],
                "chosen_feasible": r["chosen_feasible"],
                "ev_curtailed_kwh_chosen": (round(r["ev_curtailed_kwh"], 3)
                                            if r["ev_curtailed_kwh"] is not None else ""),
            })
        J_by_factor[factor] = (values, js)

    # write CSV
    csv_path = os.path.join(HERE, "sensitivity_results.csv")
    cols = ["sweep_factor", "factor_value", "feasible_A", "J_A", "feasible_B",
            "J_B", "feasible_C", "J_C", "chosen_strategy", "chosen_feasible",
            "ev_curtailed_kwh_chosen"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    # figure: one panel per factor, J of A/B/C vs factor value
    plt.style.use("seaborn-v0_8-colorblind")
    labels = {"temp_shift": "Outdoor temp shift (degC)", "C_th": "C_th (kWh/degC)",
              "R_th": "R_th (degC/kW)", "target": "Requested reduction (kW)",
              "duration": "Event duration (steps)"}
    factors = list(sweeps.keys())
    fig, axs = plt.subplots(2, 3, figsize=(13, 7))
    axs = axs.ravel()
    for i, factor in enumerate(factors):
        values, js = J_by_factor[factor]
        ax = axs[i]
        for s in STRATS:
            ax.plot(values, js[s], "o-", label=f"Strategy {s}")
        ax.set_xlabel(labels[factor])
        ax.set_ylabel("Penalty score J")
        ax.set_title(f"Sensitivity to {labels[factor]}")
        ax.grid(True, linestyle="--", alpha=0.6)
        ax.legend()
    for j in range(len(factors), len(axs)):
        axs[j].axis("off")
    fig.suptitle("Digital Twin Sandbox sensitivity sweep (penalty score J; J=0 means feasible)")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    png = os.path.join(HERE, "sensitivity_summary.png")
    pdf = os.path.join(HERE, "sensitivity_summary.pdf")
    fig.savefig(png, dpi=300)
    fig.savefig(pdf, dpi=300)

    # console report
    print(f"Rows: {len(rows)}")
    print(f"CSV : {csv_path}")
    print(f"PNG : {png}")
    print(f"PDF : {pdf}")
    print("\n--- all rows ---")
    print("  ".join(cols))
    for r in rows:
        print("  ".join(str(r[c]) for c in cols))


if __name__ == "__main__":
    main()
