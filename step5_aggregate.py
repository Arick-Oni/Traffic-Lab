"""
Step 5 — Aggregate per zone into tabular rows
Processes all screenshots, classifies pixels, and computes per-zone
congestion metrics. Outputs traffic_tabular.csv.
"""

import json
import csv
import os
from pathlib import Path
from datetime import datetime

import numpy as np

from step4_classify import classify_pixels, compute_zone_stats


def load_config(path="config.json"):
    with open(path, "r") as f:
        return json.load(f)


def load_zones(path="zones.json"):
    with open(path, "r") as f:
        data = json.load(f)
    return data["zones"]


def load_captures(path="captures.csv"):
    """Load capture metadata from CSV."""
    captures = []
    if not os.path.exists(path):
        return captures
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            captures.append(row)
    return captures


def process_single_image(image_path, zones, thresholds=None, config_path="config.json"):
    """
    Classify one screenshot and compute stats for all zones.

    Returns: list of dicts (one per zone)
    """
    class_map, _ = classify_pixels(image_path, thresholds, config_path)

    results = []
    for zone in zones:
        stats = compute_zone_stats(class_map, zone)
        stats["zone_id"] = zone["zone_id"]
        stats["row"] = zone["row"]
        stats["col"] = zone["col"]
        results.append(stats)

    return results


def aggregate_all(config_path="config.json"):
    """
    Process all captured screenshots and produce traffic_tabular.csv.
    """
    cfg = load_config(config_path)
    zones = load_zones(cfg["grid"]["zones_file"])
    captures = load_captures(cfg["capture"]["captures_csv"])
    output_csv = cfg["output"]["traffic_csv"]
    screenshot_dir = Path(cfg["capture"]["screenshot_dir"])

    # Load thresholds once
    from step4_classify import load_thresholds
    thresholds = load_thresholds(config_path)

    # Determine which images have already been processed
    processed = set()
    if os.path.exists(output_csv):
        with open(output_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                processed.add(row["filename"])

    # Prepare output CSV
    fieldnames = [
        "timestamp_utc", "timestamp_local", "filename", "zone_id",
        "row", "col",
        "green_pct", "orange_pct", "red_pct", "darkred_pct",
        "congestion_index", "total_traffic_pixels", "total_pixels"
    ]

    write_header = not os.path.exists(output_csv)
    out_file = open(output_csv, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(out_file, fieldnames=fieldnames)
    if write_header:
        writer.writeheader()

    total_captures = len(captures)
    new_count = 0

    for i, cap in enumerate(captures):
        filename = cap["filename"]
        if filename in processed:
            continue

        image_path = screenshot_dir / filename
        if not image_path.exists():
            print(f"[aggregate] SKIP {filename} — file not found")
            continue

        print(f"[aggregate] Processing {i+1}/{total_captures}: {filename} …")

        zone_results = process_single_image(
            str(image_path), zones, thresholds, config_path
        )

        for zr in zone_results:
            row = {
                "timestamp_utc": cap.get("timestamp_utc", ""),
                "timestamp_local": cap.get("timestamp_local", ""),
                "filename": filename,
                "zone_id": zr["zone_id"],
                "row": zr["row"],
                "col": zr["col"],
                "green_pct": zr["green_pct"],
                "orange_pct": zr["orange_pct"],
                "red_pct": zr["red_pct"],
                "darkred_pct": zr["darkred_pct"],
                "congestion_index": zr["congestion_index"],
                "total_traffic_pixels": zr["total_traffic_pixels"],
                "total_pixels": zr["total_pixels"],
            }
            writer.writerow(row)

        new_count += 1

    out_file.close()
    print(f"[aggregate] Done. Processed {new_count} new screenshots → {output_csv}")
    total_rows = new_count * len(zones)
    print(f"[aggregate] Wrote {total_rows} new zone-rows ({len(zones)} zones × {new_count} images)")


def process_incremental(image_path, timestamp_utc, timestamp_local, filename,
                        config_path="config.json"):
    """
    Process a single new screenshot immediately (called from the collector).
    Appends results to traffic_tabular.csv.
    """
    cfg = load_config(config_path)
    zones = load_zones(cfg["grid"]["zones_file"])
    output_csv = cfg["output"]["traffic_csv"]

    from step4_classify import load_thresholds
    thresholds = load_thresholds(config_path)

    zone_results = process_single_image(image_path, zones, thresholds, config_path)

    fieldnames = [
        "timestamp_utc", "timestamp_local", "filename", "zone_id",
        "row", "col",
        "green_pct", "orange_pct", "red_pct", "darkred_pct",
        "congestion_index", "total_traffic_pixels", "total_pixels"
    ]

    write_header = not os.path.exists(output_csv)
    with open(output_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for zr in zone_results:
            writer.writerow({
                "timestamp_utc": timestamp_utc,
                "timestamp_local": timestamp_local,
                "filename": filename,
                "zone_id": zr["zone_id"],
                "row": zr["row"],
                "col": zr["col"],
                "green_pct": zr["green_pct"],
                "orange_pct": zr["orange_pct"],
                "red_pct": zr["red_pct"],
                "darkred_pct": zr["darkred_pct"],
                "congestion_index": zr["congestion_index"],
                "total_traffic_pixels": zr["total_traffic_pixels"],
                "total_pixels": zr["total_pixels"],
            })

    return zone_results


if __name__ == "__main__":
    aggregate_all()
