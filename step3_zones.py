"""
Step 3 — Generate spatial grid zones
Creates a grid overlay on the Dhaka bounding box.
Maps each grid cell to its pixel region in the fixed screenshot.
Outputs zones.json
"""

import json
from pathlib import Path


def load_config(path="config.json"):
    with open(path, "r") as f:
        return json.load(f)


def generate_zones(config_path="config.json"):
    cfg = load_config(config_path)
    cap = cfg["capture"]
    grid = cfg["grid"]

    rows = grid["rows"]
    cols = grid["cols"]
    width = cap["viewport_width"]
    height = cap["viewport_height"]

    bounds = cap["bounds"]
    lat_north = bounds["north"]
    lat_south = bounds["south"]
    lng_east = bounds["east"]
    lng_west = bounds["west"]

    cell_w = width / cols
    cell_h = height / rows

    lat_step = (lat_north - lat_south) / rows
    lng_step = (lng_east - lng_west) / cols

    zones = []
    zone_id = 0
    for r in range(rows):
        for c in range(cols):
            # Pixel coordinates (top-left origin)
            px_x1 = int(c * cell_w)
            px_y1 = int(r * cell_h)
            px_x2 = int((c + 1) * cell_w)
            px_y2 = int((r + 1) * cell_h)

            # Geographic coordinates
            geo_north = lat_north - r * lat_step
            geo_south = lat_north - (r + 1) * lat_step
            geo_west = lng_west + c * lng_step
            geo_east = lng_west + (c + 1) * lng_step

            zones.append({
                "zone_id": zone_id,
                "row": r,
                "col": c,
                "pixel_x1": px_x1,
                "pixel_y1": px_y1,
                "pixel_x2": px_x2,
                "pixel_y2": px_y2,
                "geo_north": round(geo_north, 6),
                "geo_south": round(geo_south, 6),
                "geo_west": round(geo_west, 6),
                "geo_east": round(geo_east, 6),
            })
            zone_id += 1

    output_path = grid["zones_file"]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "grid_rows": rows,
            "grid_cols": cols,
            "viewport_width": width,
            "viewport_height": height,
            "bounds": bounds,
            "total_zones": len(zones),
            "zones": zones
        }, f, indent=2)

    print(f"[zones] Generated {len(zones)} zones → {output_path}")
    print(f"[zones] Grid: {rows} rows × {cols} cols")
    print(f"[zones] Cell size: {cell_w:.1f} × {cell_h:.1f} px")
    return zones


def find_zone_for_latlon(zones_path, lat, lng):
    """Look up which zone a given lat/lng falls into."""
    with open(zones_path, "r") as f:
        data = json.load(f)

    for z in data["zones"]:
        if (z["geo_south"] <= lat <= z["geo_north"] and
                z["geo_west"] <= lng <= z["geo_east"]):
            return z
    return None


if __name__ == "__main__":
    zones = generate_zones()

    # Quick test: find zones for known areas
    cfg = load_config()
    for name, coords in cfg.get("known_areas", {}).items():
        zone = find_zone_for_latlon("zones.json", coords["lat"], coords["lng"])
        if zone:
            print(f"  {name}: zone_id={zone['zone_id']}  "
                  f"row={zone['row']} col={zone['col']}  "
                  f"px=({zone['pixel_x1']},{zone['pixel_y1']})-"
                  f"({zone['pixel_x2']},{zone['pixel_y2']})")
        else:
            print(f"  {name}: NOT in grid bounds")
