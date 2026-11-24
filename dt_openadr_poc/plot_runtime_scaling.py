# plot_runtime_scaling.py
# Plots the scaling results produced by benchmark_runtime.py.
# Two panels: mean single-simulation time vs look-ahead steps, and vs fleet size,
# each with a least-squares linear fit to illustrate the O(N_t) / O(N_EV) trend.

import os
import json
import numpy as np
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))


def linfit(x, y):
    a, b = np.polyfit(x, y, 1)
    return a, b


def main():
    with open(os.path.join(HERE, "benchmark_runtime_results.json")) as f:
        data = json.load(f)

    steps = data["scaling"]["vs_steps"]
    evs = data["scaling"]["vs_vehicles"]

    xs = np.array([r["lookahead_steps"] for r in steps])
    ys = np.array([r["mean_ms"] for r in steps])
    xe = np.array([r["n_ev"] for r in evs])
    ye = np.array([r["mean_ms"] for r in evs])

    plt.style.use("seaborn-v0_8-colorblind")
    fig, ax = plt.subplots(1, 2, figsize=(10, 4))

    a, b = linfit(xs, ys)
    ax[0].plot(xs, ys, "o-", label="measured")
    ax[0].plot(xs, a * xs + b, "k--", alpha=0.7, label=f"linear fit ($R^2$={rsq(xs,ys,a,b):.3f})")
    ax[0].set_xlabel("Look-ahead steps $N_t$")
    ax[0].set_ylabel("Single simulation time (ms)")
    ax[0].set_title("Scaling with horizon ($N_{EV}=4$)")
    ax[0].legend()
    ax[0].grid(True, linestyle="--", alpha=0.6)

    a2, b2 = linfit(xe, ye)
    ax[1].plot(xe, ye, "s-", color="tab:orange", label="measured")
    ax[1].plot(xe, a2 * xe + b2, "k--", alpha=0.7, label=f"linear fit ($R^2$={rsq(xe,ye,a2,b2):.3f})")
    ax[1].set_xlabel("Fleet size $N_{EV}$")
    ax[1].set_ylabel("Single simulation time (ms)")
    ax[1].set_title("Scaling with fleet size ($N_t=12$)")
    ax[1].legend()
    ax[1].grid(True, linestyle="--", alpha=0.6)

    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(HERE, f"runtime_scaling.{ext}"), dpi=300)
    print("Saved runtime_scaling.png / .pdf")


def rsq(x, y, a, b):
    yhat = a * x + b
    ss_res = np.sum((y - yhat) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    return 1 - ss_res / ss_tot


if __name__ == "__main__":
    main()
