#!/usr/bin/env python3
"""Publication figure (IEEE double-column width) summarizing pull tests by needle angle.

Reads every finished run under a runs directory, groups trials by needle angle and
writes figure_overview.{pdf,png,svg}, trial_summary.csv and caption_suggestion.txt.

  python plot_results.py runs --material Towel --out figures
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import seaborn as sns

IEEE_WIDTH_IN = 7.16  # two-column figure width
# navy, teal, coral, plum, ochre, sage: distinct in colour-blind vision and in grayscale
PALETTE = ["#1F3A5F", "#2A9D8F", "#E76F51", "#8E5572", "#C9A227", "#4D908E"]
GOOD_STOPS = ("duration_complete", "user_finish", "sensor_force_limit", "motor_travel_limit")


def style():
    sns.set_theme(context="paper", style="ticks", font="serif", rc={
        "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 10, "axes.labelsize": 11, "axes.titlesize": 11,
        "xtick.labelsize": 10, "ytick.labelsize": 10, "legend.fontsize": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.linewidth": 0.8, "xtick.direction": "out", "ytick.direction": "out",
        "axes.grid": True, "grid.color": "#E6E9EC", "grid.linewidth": 0.6, "axes.axisbelow": True,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    })


def load_runs(root, material, engagement, min_samples):
    runs, skipped = [], []
    for folder in sorted(Path(root).iterdir()):
        meta_path, csv_path = folder / "metadata.json", folder / "samples.csv"
        if not (meta_path.is_file() and csv_path.is_file()):
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        cfg = meta["config"]
        if meta.get("demo") or meta.get("status") != "finished" or \
                not str(meta.get("stop_reason", "")).startswith(GOOD_STOPS):
            skipped.append((folder.name, "not a completed real run")); continue
        if material and cfg.get("material") != material:
            continue
        if engagement and cfg.get("engagement_level") != engagement:
            continue
        data = pd.read_csv(csv_path)
        angle = cfg["geometry"].get("needle_angle_deg")
        if len(data) < min_samples or angle is None:
            skipped.append((folder.name, f"{len(data)} samples, angle {angle}")); continue
        runs.append({"id": folder.name, "angle": float(angle), "trial": cfg.get("trial_id"),
                     "mm_per_rev": cfg["motor"].get("mm_per_motor_rev"), "data": data})
    return runs, skipped


def prepare(runs, time_axis):
    # Tension reads negative on this load cell; plot pull force as positive.
    high = max(r["data"]["sensor_force_N"].max() for r in runs)
    low = min(r["data"]["sensor_force_N"].min() for r in runs)
    sign = -1.0 if abs(low) > abs(high) else 1.0
    warnings = []
    for r in runs:
        d = r["data"]
        t = (d["uno_elapsed_s"] if time_axis == "uno" else d["t_s"]).to_numpy(float)
        t = t - t[0]
        f = sign * d["sensor_force_N"].to_numpy(float)
        host_span = d["t_s"].iloc[-1] - d["t_s"].iloc[0]
        uno_span = d["uno_elapsed_s"].iloc[-1] - d["uno_elapsed_s"].iloc[0]
        if host_span > 0 and abs(uno_span - host_span) / host_span > 0.1:
            warnings.append(f"{r['id']}: sensor clock spans {uno_span:.1f} s, host clock {host_span:.1f} s")
        m = d.dropna(subset=["motor_displacement_deg", "motor_rx_monotonic_s"])
        speed = np.nan
        if len(m) > 1:
            dt = m["motor_rx_monotonic_s"].iloc[-1] - m["motor_rx_monotonic_s"].iloc[0]
            turns = abs(m["motor_displacement_deg"].iloc[-1] - m["motor_displacement_deg"].iloc[0]) / 360
            if dt > 0:  # motor telemetry is stamped with host time
                speed = turns * (r["mm_per_rev"] or 60) / dt  # mm/s if calibrated, otherwise rpm
        r.update(t=t, f=f, peak=float(f.max()), mean=float(np.trapezoid(f, t) / (t[-1] - t[0])), speed=speed)
    return warnings


def summary_panel(ax, table, column, angles, colors, ylabel, title, rng):
    for i, angle in enumerate(angles):
        v = table.loc[table.angle == angle, column].dropna().to_numpy(float)
        # Trial values sit left of the column centre, mean +/- SD to the right: nothing overlaps.
        x = i - 0.2 + rng.uniform(-0.06, 0.06, len(v))
        ax.scatter(x, v, s=28, color=colors[angle], edgecolor="white", linewidth=0.5, zorder=3)
        ax.errorbar(i + 0.2, v.mean(), yerr=v.std(ddof=1) if len(v) > 1 else 0, fmt="D", ms=6.5,
                    color=colors[angle], mec="black", mew=0.8, ecolor="black", elinewidth=1.4,
                    capsize=4, capthick=1.4, zorder=4)
    ax.set_xticks(range(len(angles)), [f"{a:g}" for a in angles])
    ax.set_xlim(-0.65, len(angles) - 0.35)
    ax.set_xlabel("Needle angle, $\\theta$ (deg)")
    ax.set_ylabel(ylabel)
    ax.set_title(title, loc="left", fontweight="bold")
    ax.grid(axis="x", visible=False)


def figure(runs, outdir):
    angles = sorted({r["angle"] for r in runs})
    colors = dict(zip(angles, sns.color_palette(PALETTE if len(angles) <= len(PALETTE)
                                                   else sns.color_palette("crest", len(angles)))))
    table = pd.DataFrame([{"angle": r["angle"], "trial": r["trial"], "run": r["id"], "peak_N": r["peak"],
                           "mean_N": r["mean"], "speed": r["speed"]} for r in runs])
    n = len(angles)
    fig = plt.figure(figsize=(IEEE_WIDTH_IN, 5.9), layout="constrained")
    grid = fig.add_gridspec(2, max(n, 3), height_ratios=[1.15, 1])
    top = [fig.add_subplot(grid[0, i]) for i in range(n)]
    tmax = max(r["t"][-1] for r in runs)
    fmax = max(r["f"].max() for r in runs)
    letters = iter("abcdefghijkl")
    for i, (ax, angle) in enumerate(zip(top, angles)):
        group = [r for r in runs if r["angle"] == angle]
        for r in group:
            ax.plot(r["t"], r["f"], color=colors[angle], lw=0.9, alpha=0.45, solid_capstyle="round")
        common = np.linspace(0, min(r["t"][-1] for r in group), 300)
        ax.plot(common, np.mean([np.interp(common, r["t"], r["f"]) for r in group], axis=0),
                color=colors[angle], lw=2.6, solid_capstyle="round")
        ax.set_xlim(0, tmax * 1.02)
        ax.set_ylim(-0.02 * fmax, fmax * 1.08)
        ax.set_xlabel("Time, $t$ (s)")
        if i == 0:
            ax.set_ylabel("Pull force, $F$ (N)")
        else:
            ax.tick_params(labelleft=False)
        ax.set_title(f"({next(letters)}) $\\theta$ = {angle:g}$^\\circ$", loc="left", fontweight="bold")
    speed_unit = "mm s$^{-1}$" if any(r["mm_per_rev"] for r in runs) else "rpm"
    rng = np.random.default_rng(0)
    for col, (column, ylabel, title) in enumerate((
            ("peak_N", "Peak pull force, $F_{\\max}$ (N)", "Peak force"),
            ("mean_N", "Mean pull force, $\\bar{F}$ (N)", "Mean force"),
            ("speed", f"Mean pull speed, $\\bar{{v}}$ ({speed_unit})", "Mean speed"))):
        ax = fig.add_subplot(grid[1, col])
        summary_panel(ax, table, column, angles, colors, ylabel, f"({next(letters)}) {title}", rng)
        top_limit = table[column].max() * 1.25
        ax.set_ylim(-0.04 * top_limit, top_limit)
    handles = [Patch(facecolor=colors[a], label=f"$\\theta$ = {a:g}$^\\circ$ (n = {(table.angle == a).sum()})")
               for a in angles]
    handles += [Line2D([], [], ls="", label="")] * (-len(handles) % 2)  # keep columns of two
    handles += [Line2D([], [], color="#555555", lw=0.9, alpha=0.6, label="Individual trial"),
                Line2D([], [], color="#555555", lw=2.6, label="Trial mean"),
                Line2D([], [], marker="o", ls="", color="#888888", mec="white", ms=6, label="Trial value"),
                Line2D([], [], marker="D", ls="", color="#888888", mec="black", ms=6, label="Mean $\\pm$ SD")]
    fig.legend(handles=handles, loc="outside upper center", ncols=4, frameon=False,
               columnspacing=1.4, handlelength=1.6)
    outdir.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png", "svg"):
        fig.savefig(outdir / f"figure_overview.{ext}", dpi=600 if ext == "png" else None)
    plt.close(fig)
    return table, speed_unit


def caption(table, speed_unit):
    counts = ", ".join(f"{a:g}$^\\circ$ (n = {len(g)})" for a, g in table.groupby("angle"))
    return ("Pull-test results by needle angle. (a)-(c) Pull force over time; thin lines are individual trials and "
            "the thick line is the trial mean. (d) Peak pull force, (e) time-averaged pull force and (f) mean pull "
            f"speed ({speed_unit}); circles are individual trials and diamonds are mean $\\pm$ one standard "
            f"deviation. Angles: {counts}. Time is the load-cell sample clock.\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs_dir", nargs="?", default="runs")
    parser.add_argument("--out", default="figures")
    parser.add_argument("--material")
    parser.add_argument("--engagement", help="on_surface | in_surface | deep_into_surface")
    parser.add_argument("--min-samples", type=int, default=20)
    parser.add_argument("--time-axis", choices=("uno", "host"), default="uno",
                        help="uno = load-cell clock (default, true sample timing); host = PC receive time")
    args = parser.parse_args()
    style()
    runs, skipped = load_runs(args.runs_dir, args.material, args.engagement, args.min_samples)
    if not runs:
        raise SystemExit("No matching completed runs found")
    warnings = prepare(runs, args.time_axis)
    out = Path(args.out)
    table, unit = figure(runs, out)
    (out / "caption_suggestion.txt").write_text(caption(table, unit), encoding="utf-8")
    table.to_csv(out / "trial_summary.csv", index=False)
    print(f"Plotted {len(runs)} runs at {table.angle.nunique()} angles -> {out.resolve()}")
    for name, why in skipped:
        print(f"  skipped {name}: {why}")
    if warnings:
        print(f"WARNING: sensor and host clocks disagree in {len(warnings)} run(s), e.g. {warnings[0]}")
        print("  Host receive time lags the sensor (serial backlog); time axis uses the sensor clock.")


if __name__ == "__main__":
    main()
