"""
Step 6 — Validation Script
Validates that extracted traffic data "looks like Dhaka traffic":
  - Plots average congestion by hour (should spike morning + evening)
  - Checks known areas (Farmgate, Gulshan-2, Jatrabari)
  - Spot-checks random screenshots vs computed values
"""

import json
import csv
import random
import os
from datetime import datetime
from pathlib import Path
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def load_config(path="config.json"):
    with open(path, "r") as f:
        return json.load(f)


def load_traffic_data(csv_path):
    """Load traffic_tabular.csv into a list of dicts."""
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert numeric fields
            for key in ["zone_id", "row", "col", "total_traffic_pixels", "total_pixels"]:
                row[key] = int(row[key])
            for key in ["green_pct", "orange_pct", "red_pct", "darkred_pct", "congestion_index"]:
                row[key] = float(row[key])
            rows.append(row)
    return rows


def load_zones(path="zones.json"):
    with open(path, "r") as f:
        data = json.load(f)
    return {z["zone_id"]: z for z in data["zones"]}


def find_zone_for_latlon(zones_dict, lat, lng):
    """Find zone_id for a given lat/lng."""
    for zid, z in zones_dict.items():
        if (z["geo_south"] <= lat <= z["geo_north"] and
                z["geo_west"] <= lng <= z["geo_east"]):
            return zid
    return None


# ---------------------------------------------------------------------------
# Validation 1: Average congestion by hour of day
# ---------------------------------------------------------------------------

def plot_congestion_by_hour(data, output_path="validation_hourly.png"):
    """
    Plot average congestion index by hour of day.
    Expected: peaks around 8-10 AM and 5-8 PM for Dhaka.
    """
    hourly = defaultdict(list)

    for row in data:
        ts_str = row.get("timestamp_local", "")
        if not ts_str:
            continue
        try:
            dt = datetime.fromisoformat(ts_str)
            hour = dt.hour
            hourly[hour].append(row["congestion_index"])
        except (ValueError, TypeError):
            continue

    if not hourly:
        print("[validate] No hourly data available for plotting.")
        return

    hours = sorted(hourly.keys())
    means = [np.mean(hourly[h]) for h in hours]
    stds = [np.std(hourly[h]) for h in hours]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(hours, means, yerr=stds, color="steelblue", alpha=0.8, capsize=3)
    ax.set_xlabel("Hour of Day (Asia/Dhaka)")
    ax.set_ylabel("Average Congestion Index (0–100)")
    ax.set_title("Dhaka Traffic — Average Congestion by Hour")
    ax.set_xticks(range(24))
    ax.set_xlim(-0.5, 23.5)
    ax.grid(axis="y", alpha=0.3)

    # Highlight typical rush hours
    for h in [8, 9, 17, 18, 19]:
        if h in hours:
            idx = hours.index(h)
            ax.bar(h, means[idx], color="tomato", alpha=0.7)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"[validate] Hourly plot saved → {output_path}")

    # Print summary
    print("[validate] Hourly averages:")
    for h in hours:
        marker = " ← RUSH" if h in [8, 9, 17, 18, 19] else ""
        print(f"  {h:02d}:00  avg={np.mean(hourly[h]):.1f}  "
              f"std={np.std(hourly[h]):.1f}  n={len(hourly[h])}{marker}")


# ---------------------------------------------------------------------------
# Validation 2: Known area patterns
# ---------------------------------------------------------------------------

def check_known_areas(data, config_path="config.json"):
    """
    For Farmgate, Gulshan-2, Jatrabari — check congestion patterns.
    These areas should show high congestion during rush hours.
    """
    cfg = load_config(config_path)
    zones_dict = load_zones(cfg["grid"]["zones_file"])
    known_areas = cfg.get("known_areas", {})

    area_zones = {}
    for name, coords in known_areas.items():
        zid = find_zone_for_latlon(zones_dict, coords["lat"], coords["lng"])
        if zid is not None:
            area_zones[name] = zid
            print(f"[validate] {name} → zone_id {zid}")
        else:
            print(f"[validate] {name} — NOT in grid bounds!")

    if not area_zones:
        print("[validate] No known areas found in grid.")
        return

    # Collect data per known area
    area_data = {name: defaultdict(list) for name in area_zones}

    for row in data:
        zid = row["zone_id"]
        for name, z in area_zones.items():
            if zid == z:
                ts_str = row.get("timestamp_local", "")
                if ts_str:
                    try:
                        dt = datetime.fromisoformat(ts_str)
                        area_data[name][dt.hour].append(row["congestion_index"])
                    except (ValueError, TypeError):
                        pass

    # Plot
    fig, axes = plt.subplots(1, len(area_zones), figsize=(6 * len(area_zones), 4),
                              sharey=True)
    if len(area_zones) == 1:
        axes = [axes]

    for ax, (name, hourly) in zip(axes, area_data.items()):
        if not hourly:
            ax.set_title(f"{name}\n(no data)")
            continue
        hours = sorted(hourly.keys())
        means = [np.mean(hourly[h]) for h in hours]
        ax.bar(hours, means, color="coral", alpha=0.8)
        ax.set_title(name)
        ax.set_xlabel("Hour")
        ax.set_xticks(range(0, 24, 2))
        ax.grid(axis="y", alpha=0.3)

    axes[0].set_ylabel("Congestion Index (0–100)")
    fig.suptitle("Known Area Congestion Patterns", fontsize=14)
    fig.tight_layout()
    fig.savefig("validation_known_areas.png", dpi=150)
    plt.close(fig)
    print("[validate] Known areas plot saved → validation_known_areas.png")


# ---------------------------------------------------------------------------
# Validation 3: Spot-check random screenshots
# ---------------------------------------------------------------------------

def spot_check(data, n=20):
    """
    Randomly sample n data points and print for manual inspection.
    """
    if len(data) < n:
        sample = data
    else:
        sample = random.sample(data, n)

    print(f"\n[validate] Spot-check — {len(sample)} random zone-rows:")
    print(f"  {'timestamp_local':25s} zone  green%  orange%  red%  dkred%  CI")
    print("  " + "-" * 80)

    for row in sorted(sample, key=lambda r: r.get("timestamp_local", "")):
        ts = row.get("timestamp_local", "")[:19]
        print(f"  {ts:25s} {row['zone_id']:4d}  "
              f"{row['green_pct']:6.1f}  {row['orange_pct']:7.1f}  "
              f"{row['red_pct']:5.1f}  {row['darkred_pct']:6.1f}  "
              f"{row['congestion_index']:5.1f}")


# ---------------------------------------------------------------------------
# Validation 4: Data quality summary
# ---------------------------------------------------------------------------

def data_quality_report(data):
    """Print overall data quality statistics."""
    if not data:
        print("[validate] No data to report on.")
        return

    timestamps = set()
    zones_seen = set()
    total_rows = len(data)

    ci_values = []
    zero_traffic_count = 0

    for row in data:
        timestamps.add(row.get("filename", ""))
        zones_seen.add(row["zone_id"])
        ci_values.append(row["congestion_index"])
        if row["total_traffic_pixels"] == 0:
            zero_traffic_count += 1

    n_screenshots = len(timestamps)
    n_zones = len(zones_seen)
    ci_arr = np.array(ci_values)

    print(f"\n[validate] === DATA QUALITY REPORT ===")
    print(f"  Total rows        : {total_rows:,}")
    print(f"  Screenshots       : {n_screenshots}")
    print(f"  Zones with data   : {n_zones}")
    print(f"  Zero-traffic zones: {zero_traffic_count:,}  "
          f"({zero_traffic_count/total_rows*100:.1f}%)")
    print(f"  Congestion Index  : mean={ci_arr.mean():.1f}  "
          f"std={ci_arr.std():.1f}  "
          f"min={ci_arr.min():.1f}  max={ci_arr.max():.1f}")

    # Check for suspicious patterns
    if ci_arr.mean() < 1:
        print("  ⚠ WARN: Very low average CI — thresholds may be too strict")
    if zero_traffic_count / total_rows > 0.9:
        print("  ⚠ WARN: >90% zones have zero traffic pixels — check thresholds")
    if n_screenshots < 10:
        print("  ⚠ WARN: Very few screenshots — collect more data for meaningful validation")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_validation(config_path="config.json"):
    cfg = load_config(config_path)
    traffic_csv = cfg["output"]["traffic_csv"]

    if not os.path.exists(traffic_csv):
        print(f"[validate] {traffic_csv} not found. Run step5_aggregate.py first.")
        return

    print(f"[validate] Loading {traffic_csv} …")
    data = load_traffic_data(traffic_csv)
    print(f"[validate] Loaded {len(data):,} rows")

    data_quality_report(data)
    plot_congestion_by_hour(data)
    check_known_areas(data, config_path)
    spot_check(data, n=20)

    print("\n[validate] ✓ Validation complete. Check the PNG plots for visual review.")


if __name__ == "__main__":
    run_validation()
