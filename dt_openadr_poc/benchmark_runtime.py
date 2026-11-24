# benchmark_runtime.py
# Execution-time micro-benchmark for the Digital Twin Sandbox.
#
# Addresses Reviewer 1, Comment 3: the paper must support its computational-
# efficiency claim with actual execution-time measurements on a stated hardware
# platform, and show how cost scales with the problem size.
#
# What it measures
# ----------------
# 1. Event-1 workload: the exact work the EMS performs when an OpenADR event
#    arrives -- evaluate all three candidate strategies (A, B, C) over the
#    look-ahead horizon used in the Proof of Concept (4 pre-event + 8 event
#    steps = 12 steps), with the 4-vehicle fleet. Reported as the per-decision
#    latency: mean / median / p95 / p99 / min / max over many repetitions.
# 2. Scaling: wall-clock time of ONE strategy simulation as we grow, one axis
#    at a time, the number of look-ahead steps N_t and the number of vehicles
#    N_EV, to show the near-linear O(N_s * N_t * N_EV) behaviour.
#
# No claim is made beyond what is measured on THIS machine. The script prints
# the CPU, RAM, OS and Python version so the numbers are attributable.
#
# Run:
#   & 'C:\Users\david\anaconda3\envs\energy_AI\python.exe' benchmark_runtime.py

import os
import sys
import csv
import json
import time
import platform
import statistics
from datetime import datetime

import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import CONFIG
from models.building_model import BuildingThermalModel
from models.ev_fleet_model import EVFleetModel
from core.dt_sandbox import DigitalTwinSandbox

try:
    import psutil
except ImportError:
    psutil = None

HERE = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def load_profiles():
    """Load the 24h outdoor-temperature and base-load profiles used in the PoC."""
    csv_path = os.path.join(HERE, "data", "profiles.csv")
    T_out, base = [], []
    with open(csv_path, mode="r") as f:
        for row in csv.DictReader(f):
            T_out.append(float(row["T_out"]))
            base.append(float(row["base_load"]))
    return np.array(T_out), np.array(base)


def make_building():
    b = CONFIG["building"]
    return BuildingThermalModel(
        R_th=b["R_th"], C_th=b["C_th"], COP=b["COP"],
        T_min=b["T_min"], T_max=b["T_max"], T_in_init=b["T_in_init"],
        P_HVAC_max=b["P_HVAC_max"], P_HVAC_baseline=b["P_HVAC_baseline"],
    )


def make_fleet(n_ev=None):
    """Build an EV fleet. If n_ev is given, replicate/trim the PoC fleet to size."""
    evs = CONFIG["ev_fleet"]["evs"]
    if n_ev is None:
        return EVFleetModel(evs)
    base = evs
    out = []
    for i in range(n_ev):
        src = dict(base[i % len(base)])
        src = dict(src)
        src["id"] = f"EV{i+1}"
        out.append(src)
    return EVFleetModel(out)


def summarize(samples_s):
    """Return a dict of statistics in milliseconds from a list of seconds."""
    ms = sorted(x * 1e3 for x in samples_s)
    n = len(ms)

    def pct(p):
        if n == 1:
            return ms[0]
        k = (n - 1) * p
        lo = int(k)
        hi = min(lo + 1, n - 1)
        return ms[lo] + (ms[hi] - ms[lo]) * (k - lo)

    return {
        "n": n,
        "mean_ms": statistics.fmean(ms),
        "median_ms": statistics.median(ms),
        "stdev_ms": statistics.pstdev(ms),
        "p95_ms": pct(0.95),
        "p99_ms": pct(0.99),
        "min_ms": ms[0],
        "max_ms": ms[-1],
    }


# ----------------------------------------------------------------------------
# Benchmark 1: Event-1 decision latency (evaluate strategies A, B, C)
# ----------------------------------------------------------------------------

def bench_event1_decision(T_out, base, reps=2000, warmup=200):
    """
    Time the full per-event decision: simulate strategies A, B, C over the
    Event-1 look-ahead window exactly as the EMS does.

    Event 1 parameters (from the PoC): notified at step 52 (13:00), active
    14:00-16:00 -> start_step=56, duration=8 steps, target=20 kW.
    The sandbox's Strategy C adds a 4-step pre-cool, so current_step=52.
    """
    dt_hours = CONFIG["dt_hours"]
    sandbox = DigitalTwinSandbox()

    current_step = 52
    start_step = 56
    duration = 8
    target = 20.0
    strategies = ["A", "B", "C"]

    def one_decision():
        # Fresh models each decision so deepcopy cost inside the sandbox is
        # measured on the same state the PoC uses at 13:00.
        b = make_building()
        f = make_fleet()
        # advance real state to step 52 so initial conditions match the PoC
        for s in range(current_step):
            b.step(T_out[s], b.P_HVAC_baseline, dt_hours, mode="cooling")
            f.step(s, f.get_baseline_power(s, dt_hours), dt_hours, allocation_method="proportional")
        t0 = time.perf_counter()
        for strat in strategies:
            sandbox.simulate_scenario(
                b, f, strat, current_step, start_step, duration, target,
                base.tolist(), T_out.tolist(), dt_hours,
            )
        return time.perf_counter() - t0

    for _ in range(warmup):
        one_decision()
    samples = [one_decision() for _ in range(reps)]
    return summarize(samples), {
        "strategies": len(strategies),
        "lookahead_steps": start_step + duration - current_step,
        "n_ev": len(CONFIG["ev_fleet"]["evs"]),
        "reps": reps,
        "warmup": warmup,
    }


# ----------------------------------------------------------------------------
# Benchmark 2: scaling in steps and vehicles (one strategy simulation)
# ----------------------------------------------------------------------------

def time_single_sim(T_out, base, n_ev, duration, reps=1000):
    """Mean ms for ONE Strategy-B simulation of given horizon and fleet size."""
    dt_hours = CONFIG["dt_hours"]
    sandbox = DigitalTwinSandbox()
    current_step = 40
    start_step = 44
    target = 10.0

    # extend profiles if the horizon runs past 96 steps
    need = start_step + duration + 1
    if need > len(T_out):
        reps_tile = int(np.ceil(need / len(T_out)))
        T_out_ext = np.tile(T_out, reps_tile)[:need]
        base_ext = np.tile(base, reps_tile)[:need]
    else:
        T_out_ext, base_ext = T_out, base

    def one():
        b = make_building()
        f = make_fleet(n_ev)
        t0 = time.perf_counter()
        sandbox.simulate_scenario(
            b, f, "B", current_step, start_step, duration, target,
            base_ext.tolist(), T_out_ext.tolist(), dt_hours,
        )
        return time.perf_counter() - t0

    for _ in range(50):
        one()
    samples = [one() for _ in range(reps)]
    return statistics.fmean(samples) * 1e3


def bench_scaling(T_out, base):
    step_sizes = [8, 16, 32, 48, 64, 96]
    ev_sizes = [1, 2, 4, 8, 16, 32]
    steps_rows = [
        {"lookahead_steps": s, "n_ev": 4, "mean_ms": time_single_sim(T_out, base, 4, s)}
        for s in step_sizes
    ]
    ev_rows = [
        {"lookahead_steps": 12, "n_ev": n, "mean_ms": time_single_sim(T_out, base, n, 12)}
        for n in ev_sizes
    ]
    return {"vs_steps": steps_rows, "vs_vehicles": ev_rows}


# ----------------------------------------------------------------------------
# Machine info
# ----------------------------------------------------------------------------

def machine_info():
    info = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "numpy": np.__version__,
    }
    if psutil is not None:
        info["physical_cpus"] = psutil.cpu_count(logical=False)
        freq = psutil.cpu_freq()
        if freq:
            info["cpu_max_mhz"] = round(freq.max, 1)
        info["ram_gb"] = round(psutil.virtual_memory().total / 1e9, 1)
    return info


def main():
    T_out, base = load_profiles()
    info = machine_info()

    print("=== Machine ===")
    for k, v in info.items():
        print(f"  {k}: {v}")

    print("\n=== Benchmark 1: Event-1 decision latency (strategies A,B,C) ===")
    lat, meta = bench_event1_decision(T_out, base)
    print(f"  workload: {meta['strategies']} strategies x "
          f"{meta['lookahead_steps']} steps x {meta['n_ev']} EVs, "
          f"{meta['reps']} reps")
    for k in ("mean_ms", "median_ms", "stdev_ms", "p95_ms", "p99_ms", "min_ms", "max_ms"):
        print(f"  {k:10s}: {lat[k]:.4f} ms")

    print("\n=== Benchmark 2: scaling ===")
    scaling = bench_scaling(T_out, base)
    print("  one Strategy-B sim vs look-ahead steps (N_EV=4):")
    for r in scaling["vs_steps"]:
        print(f"    steps={r['lookahead_steps']:3d}  {r['mean_ms']:.4f} ms")
    print("  one Strategy-B sim vs fleet size (steps=12):")
    for r in scaling["vs_vehicles"]:
        print(f"    N_EV={r['n_ev']:3d}  {r['mean_ms']:.4f} ms")

    out = {"machine": info, "event1_decision": {"stats": lat, "meta": meta},
           "scaling": scaling}
    out_path = os.path.join(HERE, "benchmark_runtime_results.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
