"""
Step 4 — Color → Congestion Class Extraction
Converts Google Maps traffic screenshot pixels to congestion classes
using HSV thresholds.
"""

import json
import numpy as np
import cv2
from pathlib import Path


# ---------------------------------------------------------------------------
# Load thresholds
# ---------------------------------------------------------------------------

def load_thresholds(config_path="config.json"):
    """Load color thresholds from the versioned JSON file."""
    with open(config_path, "r") as f:
        cfg = json.load(f)
    thresh_file = cfg["thresholds"]["file"]
    with open(thresh_file, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Per-pixel classification
# ---------------------------------------------------------------------------

def classify_pixels(image_path, thresholds=None, config_path="config.json"):
    """
    Classify every pixel in a screenshot into a congestion class.

    Returns:
        class_map : np.ndarray of shape (H, W) with values:
            0 = green  (free flow)
            1 = orange (moderate)
            2 = red    (heavy)
            3 = dark_red (severe)
           -1 = unclassified (background, labels, water, etc.)
        masks : dict[str, np.ndarray]  — boolean mask per class
    """
    if thresholds is None:
        thresholds = load_thresholds(config_path)

    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

    h, w = img_hsv.shape[:2]
    class_map = np.full((h, w), -1, dtype=np.int8)
    masks = {}

    # Process in priority order: dark_red > red > orange > green
    # (dark_red overlaps with red in hue, so check it first)
    priority_order = ["dark_red", "red", "orange", "green"]

    for class_name in priority_order:
        if class_name not in thresholds:
            continue
        t = thresholds[class_name]
        lower = np.array(t["hsv_lower"], dtype=np.uint8)
        upper = np.array(t["hsv_upper"], dtype=np.uint8)
        score = t["congestion_score"]

        mask = cv2.inRange(img_hsv, lower, upper)
        # Only assign to pixels not yet classified
        unassigned = (class_map == -1)
        final_mask = (mask > 0) & unassigned

        class_map[final_mask] = score
        masks[class_name] = final_mask

    return class_map, masks


def compute_zone_stats(class_map, zone):
    """
    Compute congestion percentages for a single zone (pixel region).

    Args:
        class_map: full-image classification array
        zone: dict with pixel_x1, pixel_y1, pixel_x2, pixel_y2

    Returns:
        dict with green_pct, orange_pct, red_pct, darkred_pct,
        congestion_index, total_traffic_pixels
    """
    x1, y1 = zone["pixel_x1"], zone["pixel_y1"]
    x2, y2 = zone["pixel_x2"], zone["pixel_y2"]

    region = class_map[y1:y2, x1:x2]
    total_pixels = region.size

    # Count traffic pixels only (class >= 0)
    traffic_mask = region >= 0
    traffic_count = int(np.sum(traffic_mask))

    if traffic_count == 0:
        return {
            "green_pct": 0.0,
            "orange_pct": 0.0,
            "red_pct": 0.0,
            "darkred_pct": 0.0,
            "congestion_index": 0.0,
            "total_traffic_pixels": 0,
            "total_pixels": total_pixels,
        }

    green_count = int(np.sum(region == 0))
    orange_count = int(np.sum(region == 1))
    red_count = int(np.sum(region == 2))
    darkred_count = int(np.sum(region == 3))

    green_pct = round(green_count / traffic_count * 100, 2)
    orange_pct = round(orange_count / traffic_count * 100, 2)
    red_pct = round(red_count / traffic_count * 100, 2)
    darkred_pct = round(darkred_count / traffic_count * 100, 2)

    # Congestion index: weighted average (0=green, 1=orange, 2=red, 3=darkred)
    # Scaled to 0–100
    weighted = (green_count * 0 + orange_count * 1 +
                red_count * 2 + darkred_count * 3)
    congestion_index = round((weighted / (traffic_count * 3)) * 100, 2)

    return {
        "green_pct": green_pct,
        "orange_pct": orange_pct,
        "red_pct": red_pct,
        "darkred_pct": darkred_pct,
        "congestion_index": congestion_index,
        "total_traffic_pixels": traffic_count,
        "total_pixels": total_pixels,
    }


def visualize_classification(image_path, class_map, output_path=None):
    """
    Create a visualization overlay showing classified traffic pixels.
    Useful for debugging / validation.
    """
    img = cv2.imread(str(image_path))
    overlay = img.copy()

    # Color each class
    colors = {
        0: (0, 255, 0),     # green
        1: (0, 165, 255),   # orange (BGR)
        2: (0, 0, 255),     # red
        3: (0, 0, 139),     # dark red
    }

    for class_val, color in colors.items():
        mask = class_map == class_val
        overlay[mask] = color

    # Blend with original
    result = cv2.addWeighted(img, 0.4, overlay, 0.6, 0)

    if output_path:
        cv2.imwrite(str(output_path), result)
        print(f"[classify] Visualization saved → {output_path}")

    return result


# ---------------------------------------------------------------------------
# CLI entry point for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python step4_classify.py <screenshot.png> [output_vis.png]")
        sys.exit(1)

    image_path = sys.argv[1]
    vis_path = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"[classify] Processing {image_path} …")
    class_map, masks = classify_pixels(image_path)

    # Global stats
    total = class_map.size
    for name, score in [("green", 0), ("orange", 1), ("red", 2), ("dark_red", 3)]:
        count = int(np.sum(class_map == score))
        pct = count / total * 100
        print(f"  {name:10s}: {count:>8d} px  ({pct:.2f}%)")

    unclassified = int(np.sum(class_map == -1))
    print(f"  {'other':10s}: {unclassified:>8d} px  ({unclassified/total*100:.2f}%)")

    if vis_path:
        visualize_classification(image_path, class_map, vis_path)
