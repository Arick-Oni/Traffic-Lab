"""
Step 7 — Resilience & Drift Detection
Monitors for UI/color drift in Google Maps screenshots.
Tracks color histograms and alerts if distribution shifts suddenly.
"""

import json
import csv
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import cv2


def load_config(path="config.json"):
    with open(path, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Histogram tracking
# ---------------------------------------------------------------------------

def compute_color_histogram(image_path, bins=32):
    """
    Compute a normalized HSV histogram for a screenshot.
    Returns a flat numpy array suitable for comparison.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return None
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Compute 3D histogram (H, S, V)
    hist = cv2.calcHist(
        [hsv], [0, 1, 2], None,
        [bins, bins, bins],
        [0, 180, 0, 256, 0, 256]
    )
    # Normalize
    hist = cv2.normalize(hist, hist).flatten()
    return hist


def compute_traffic_color_distribution(image_path, thresholds_path="thresholds_v1.json"):
    """
    Compute the percentage of pixels in each traffic class.
    Returns a dict with class percentages (for tracking over time).
    """
    with open(thresholds_path, "r") as f:
        thresholds = json.load(f)

    img = cv2.imread(str(image_path))
    if img is None:
        return None
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    total = hsv.shape[0] * hsv.shape[1]

    dist = {}
    for class_name, t in thresholds.items():
        lower = np.array(t["hsv_lower"], dtype=np.uint8)
        upper = np.array(t["hsv_upper"], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
        count = int(np.sum(mask > 0))
        dist[class_name] = round(count / total * 100, 4)

    dist["unclassified"] = round(100 - sum(dist.values()), 4)
    return dist


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------

class DriftDetector:
    """
    Tracks color distributions over time and detects sudden shifts
    that could indicate Google Maps UI changes.
    """

    def __init__(self, config_path="config.json", window_size=50):
        self.config_path = config_path
        self.cfg = load_config(config_path)
        self.drift_log = self.cfg["output"]["drift_log"]
        self.window_size = window_size
        self.history = []  # list of distribution dicts

        # Initialize drift log
        if not os.path.exists(self.drift_log):
            with open(self.drift_log, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "filename", "alert_type", "details",
                    "green_pct", "orange_pct", "red_pct", "darkred_pct",
                    "unclassified_pct"
                ])

    def check(self, image_path, filename, timestamp=None):
        """
        Check a new screenshot for drift. Returns list of alerts.
        """
        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()

        dist = compute_traffic_color_distribution(
            image_path,
            self.cfg["thresholds"]["file"]
        )
        if dist is None:
            return [{"type": "FILE_ERROR", "detail": f"Cannot read {image_path}"}]

        alerts = []

        # Check 1: Unusually high unclassified percentage
        # (could mean Google changed colors)
        if dist.get("unclassified", 0) > 98:
            alerts.append({
                "type": "HIGH_UNCLASSIFIED",
                "detail": f"Unclassified={dist['unclassified']:.1f}% — "
                          f"possible UI change or blank screenshot"
            })

        # Check 2: Distribution shift from rolling average
        if len(self.history) >= self.window_size:
            recent = self.history[-self.window_size:]
            for key in ["green", "orange", "red", "dark_red"]:
                if key not in dist:
                    continue
                hist_values = [h.get(key, 0) for h in recent]
                mean = np.mean(hist_values)
                std = np.std(hist_values)

                if std > 0 and abs(dist[key] - mean) > 3 * std:
                    alerts.append({
                        "type": "DISTRIBUTION_SHIFT",
                        "detail": f"{key}: current={dist[key]:.2f}%  "
                                  f"rolling_mean={mean:.2f}%  "
                                  f"rolling_std={std:.2f}%  "
                                  f"(>{3}σ deviation)"
                    })

        # Check 3: Zero traffic pixels entirely
        traffic_total = sum(dist.get(k, 0) for k in ["green", "orange", "red", "dark_red"])
        if traffic_total < 0.5:
            alerts.append({
                "type": "NO_TRAFFIC_PIXELS",
                "detail": f"Total traffic pixels = {traffic_total:.2f}% — "
                          f"map may not have loaded or traffic layer is off"
            })

        # Log alerts
        if alerts:
            for alert in alerts:
                self._log_alert(timestamp, filename, alert["type"], alert["detail"], dist)
                print(f"[drift] ALERT [{alert['type']}] {alert['detail']}")
        else:
            pass  # all good

        # Update history
        self.history.append(dist)

        return alerts

    def _log_alert(self, timestamp, filename, alert_type, details, dist):
        with open(self.drift_log, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp, filename, alert_type, details,
                dist.get("green", 0),
                dist.get("orange", 0),
                dist.get("red", 0),
                dist.get("dark_red", 0),
                dist.get("unclassified", 0),
            ])

    def load_history_from_csv(self, traffic_csv):
        """
        Bootstrap the drift detector history from existing traffic data.
        Computes approximate distributions per screenshot from aggregated data.
        """
        if not os.path.exists(traffic_csv):
            return

        from collections import defaultdict
        screenshot_data = defaultdict(lambda: defaultdict(list))

        with open(traffic_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                fname = row["filename"]
                for key in ["green_pct", "orange_pct", "red_pct", "darkred_pct"]:
                    screenshot_data[fname][key].append(float(row[key]))

        for fname, values in screenshot_data.items():
            dist = {
                "green": np.mean(values.get("green_pct", [0])),
                "orange": np.mean(values.get("orange_pct", [0])),
                "red": np.mean(values.get("red_pct", [0])),
                "dark_red": np.mean(values.get("darkred_pct", [0])),
            }
            dist["unclassified"] = max(0, 100 - sum(dist.values()))
            self.history.append(dist)

        print(f"[drift] Loaded {len(self.history)} historical distributions")


# ---------------------------------------------------------------------------
# Histogram comparison (for deeper analysis)
# ---------------------------------------------------------------------------

def compare_histograms(hist1, hist2, method="correlation"):
    """
    Compare two histograms using OpenCV methods.
    Methods: 'correlation', 'chi-square', 'intersection', 'bhattacharyya'
    """
    methods = {
        "correlation": cv2.HISTCMP_CORREL,
        "chi-square": cv2.HISTCMP_CHISQR,
        "intersection": cv2.HISTCMP_INTERSECT,
        "bhattacharyya": cv2.HISTCMP_BHATTACHARYYA,
    }
    m = methods.get(method, cv2.HISTCMP_CORREL)
    return cv2.compareHist(
        hist1.astype(np.float32),
        hist2.astype(np.float32),
        m
    )


def check_style_change(reference_path, current_path, threshold=0.85):
    """
    Compare a reference screenshot histogram against a current one.
    If correlation drops below threshold, flag as possible style change.

    Returns (is_ok, correlation_score)
    """
    ref_hist = compute_color_histogram(reference_path)
    cur_hist = compute_color_histogram(current_path)

    if ref_hist is None or cur_hist is None:
        return False, 0.0

    score = compare_histograms(ref_hist, cur_hist, "correlation")
    is_ok = score >= threshold
    return is_ok, score


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python step7_resilience.py check <image.png>")
        print("  python step7_resilience.py compare <ref.png> <current.png>")
        print("  python step7_resilience.py scan-all")
        sys.exit(1)

    command = sys.argv[1]

    if command == "check":
        image_path = sys.argv[2]
        detector = DriftDetector()
        alerts = detector.check(image_path, os.path.basename(image_path))
        if not alerts:
            print("[drift] No issues detected.")

    elif command == "compare":
        ref = sys.argv[2]
        cur = sys.argv[3]
        ok, score = check_style_change(ref, cur)
        print(f"[drift] Correlation: {score:.4f}  "
              f"{'OK' if ok else 'POSSIBLE STYLE CHANGE'}")

    elif command == "scan-all":
        cfg = load_config()
        screenshot_dir = Path(cfg["capture"]["screenshot_dir"])
        detector = DriftDetector()

        # Load history from existing data
        detector.load_history_from_csv(cfg["output"]["traffic_csv"])

        pngs = sorted(screenshot_dir.glob("*.png"))
        print(f"[drift] Scanning {len(pngs)} screenshots …")

        alert_count = 0
        for png in pngs:
            alerts = detector.check(str(png), png.name)
            alert_count += len(alerts)

        print(f"[drift] Scan complete. Total alerts: {alert_count}")
