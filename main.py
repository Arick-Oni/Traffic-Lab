"""
Main Orchestrator — Dhaka Traffic Scraper
Runs the full pipeline:
  1. Generate zones (once)
  2. Capture screenshots in a loop
  3. Classify & aggregate each screenshot immediately
  4. Monitor for drift
  5. Run validation on demand

Usage:
  python main.py collect        — start screenshot collection + live processing
  python main.py zones          — generate zones.json
  python main.py aggregate      — batch-process all unprocessed screenshots
  python main.py validate       — run validation checks on collected data
  python main.py drift-scan     — scan all screenshots for drift
  python main.py single <img>   — process a single screenshot
"""

import sys
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

import pytz


def load_config(path="config.json"):
    with open(path, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Command: zones
# ---------------------------------------------------------------------------
def cmd_zones():
    from step3_zones import generate_zones
    generate_zones()


# ---------------------------------------------------------------------------
# Command: collect (with live processing)
# ---------------------------------------------------------------------------
def cmd_collect():
    from step2_collector import (
        load_config, build_maps_url, create_driver,
        wait_for_map_load, dismiss_popups, take_screenshot,
        init_csv, append_csv
    )
    from step5_aggregate import process_incremental
    from step7_resilience import DriftDetector

    cfg = load_config()
    cap = cfg["capture"]

    screenshot_dir = Path(cap["screenshot_dir"])
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    csv_path = cap["captures_csv"]
    init_csv(csv_path)

    interval = cap["interval_seconds"]
    tz = pytz.timezone(cfg["timezone"])
    run_id = str(uuid.uuid4())[:8]
    machine_id = cap["machine_id"]

    # Ensure zones exist
    zones_file = cfg["grid"]["zones_file"]
    if not os.path.exists(zones_file):
        print("[main] Generating zones …")
        cmd_zones()

    # Initialize drift detector
    drift = DriftDetector()
    drift.load_history_from_csv(cfg["output"]["traffic_csv"])

    url = build_maps_url(cfg)
    print(f"[main] Starting collection loop")
    print(f"[main] URL      : {url}")
    print(f"[main] Interval : {interval}s")
    print(f"[main] Run ID   : {run_id}")

    iteration = 0
    try:
        while True:
            now_utc = datetime.utcnow()
            now_local = datetime.now(tz)

            filename = now_local.strftime("%Y-%m-%d_%H-%M-%S") + ".png"
            filepath = screenshot_dir / filename

            # 1. Fresh browser for every capture
            print(f"[main] Opening browser …")
            driver = create_driver(cfg)
            try:
                driver.get(url)
                wait_for_map_load(driver)
                dismiss_popups(driver)
                time.sleep(3)

                take_screenshot(driver, str(filepath))
            finally:
                driver.quit()
                print(f"[main] Browser closed.")

            ts_utc = now_utc.isoformat()
            ts_local = now_local.isoformat()

            row = [
                ts_utc, ts_local, filename,
                cap["zoom_level"],
                cap["center_lat"], cap["center_lng"],
                cap["bounds"]["north"], cap["bounds"]["south"],
                cap["bounds"]["east"], cap["bounds"]["west"],
                run_id, machine_id,
            ]
            append_csv(csv_path, row)

            iteration += 1
            print(f"[main] #{iteration} captured {filename}")

            # 2. Classify & aggregate immediately
            try:
                process_incremental(
                    str(filepath), ts_utc, ts_local, filename
                )
                print(f"[main] #{iteration} processed")
            except Exception as e:
                print(f"[main] #{iteration} processing error: {e}")

            # 3. Drift check
            try:
                alerts = drift.check(str(filepath), filename, ts_utc)
                if alerts:
                    print(f"[main] #{iteration} DRIFT ALERTS: {len(alerts)}")
            except Exception as e:
                print(f"[main] #{iteration} drift check error: {e}")

            # Sleep until next interval
            elapsed = (datetime.utcnow() - now_utc).total_seconds()
            sleep_time = max(0, interval - elapsed)
            if sleep_time > 0:
                print(f"[main] sleeping {sleep_time:.0f}s …")
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n[main] Stopped by user.")


# ---------------------------------------------------------------------------
# Command: aggregate
# ---------------------------------------------------------------------------
def cmd_aggregate():
    from step5_aggregate import aggregate_all
    aggregate_all()


# ---------------------------------------------------------------------------
# Command: validate
# ---------------------------------------------------------------------------
def cmd_validate():
    from step6_validate import run_validation
    run_validation()


# ---------------------------------------------------------------------------
# Command: drift-scan
# ---------------------------------------------------------------------------
def cmd_drift_scan():
    from step7_resilience import DriftDetector
    cfg = load_config()
    screenshot_dir = Path(cfg["capture"]["screenshot_dir"])
    detector = DriftDetector()
    detector.load_history_from_csv(cfg["output"]["traffic_csv"])

    pngs = sorted(screenshot_dir.glob("*.png"))
    print(f"[main] Scanning {len(pngs)} screenshots for drift …")

    alert_count = 0
    for png in pngs:
        alerts = detector.check(str(png), png.name)
        alert_count += len(alerts)

    print(f"[main] Drift scan complete. Total alerts: {alert_count}")


# ---------------------------------------------------------------------------
# Command: single
# ---------------------------------------------------------------------------
def cmd_single(image_path):
    from step4_classify import classify_pixels, compute_zone_stats, visualize_classification
    from step3_zones import load_config
    import numpy as np

    cfg = load_config()
    zones_file = cfg["grid"]["zones_file"]

    if not os.path.exists(zones_file):
        print("[main] Generating zones first …")
        cmd_zones()

    with open(zones_file, "r") as f:
        zones_data = json.load(f)
    zones = zones_data["zones"]

    print(f"[main] Classifying {image_path} …")
    class_map, masks = classify_pixels(image_path)

    # Global stats
    total = class_map.size
    for name, score in [("green", 0), ("orange", 1), ("red", 2), ("dark_red", 3)]:
        count = int(np.sum(class_map == score))
        print(f"  {name:10s}: {count:>8d} px  ({count/total*100:.2f}%)")

    # Zone stats for known areas
    from step3_zones import find_zone_for_latlon
    known_areas = cfg.get("known_areas", {})
    for name, coords in known_areas.items():
        zone = find_zone_for_latlon(zones_file, coords["lat"], coords["lng"])
        if zone:
            stats = compute_zone_stats(class_map, zone)
            print(f"\n  {name} (zone {zone['zone_id']}):")
            print(f"    green={stats['green_pct']:.1f}%  "
                  f"orange={stats['orange_pct']:.1f}%  "
                  f"red={stats['red_pct']:.1f}%  "
                  f"dark_red={stats['darkred_pct']:.1f}%  "
                  f"CI={stats['congestion_index']:.1f}")

    # Save visualization
    vis_path = image_path.replace(".png", "_classified.png")
    visualize_classification(image_path, class_map, vis_path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1].lower()

    if command == "collect":
        cmd_collect()
    elif command == "zones":
        cmd_zones()
    elif command == "aggregate":
        cmd_aggregate()
    elif command == "validate":
        cmd_validate()
    elif command == "drift-scan":
        cmd_drift_scan()
    elif command == "single":
        if len(sys.argv) < 3:
            print("Usage: python main.py single <screenshot.png>")
            sys.exit(1)
        cmd_single(sys.argv[2])
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
