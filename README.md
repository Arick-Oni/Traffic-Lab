# Dhaka Traffic Scraper

Scrapes Google Maps traffic data for Dhaka, Bangladesh by capturing screenshots, extracting traffic colors via HSV thresholding, and producing structured tabular data.

## Setup

### Prerequisites
- **Python 3.9+**
- **Google Chrome** installed
- **ChromeDriver** matching your Chrome version (or use `webdriver-manager`)

### Install dependencies
```bash
pip install -r requirements.txt
```

## Project Structure

| File | Description |
|------|-------------|
| `config.json` | Master configuration (viewport, zoom, bounds, intervals) |
| `thresholds_v1.json` | HSV color thresholds for traffic classification |
| `main.py` | **Main orchestrator** — run all commands from here |
| `step2_collector.py` | Screenshot capture loop (Selenium + headless Chrome) |
| `step3_zones.py` | Grid zone generator (50×50 cells over Dhaka) |
| `step4_classify.py` | Pixel classification (HSV → congestion class) |
| `step5_aggregate.py` | Per-zone aggregation → `traffic_tabular.csv` |
| `step6_validate.py` | Validation plots & quality checks |
| `step7_resilience.py` | Drift detection & style-change monitoring |

## Quick Start

### 1. Generate the zone grid
```bash
python main.py zones
```
Creates `zones.json` with 2500 grid cells (50×50) mapped to pixel regions.

### 2. Start collecting data
```bash
python main.py collect
```
This will:
- Open Google Maps (headless) centered on Dhaka with traffic layer ON
- Take a screenshot every 5 minutes
- Immediately classify pixels and compute per-zone congestion
- Monitor for color drift
- Save everything to `screenshots/`, `captures.csv`, and `traffic_tabular.csv`

Press **Ctrl+C** to stop.

### 3. Batch-process existing screenshots
```bash
python main.py aggregate
```

### 4. Validate the data
```bash
python main.py validate
```
Produces:
- `validation_hourly.png` — congestion by hour (should show AM/PM peaks)
- `validation_known_areas.png` — Farmgate, Gulshan-2, Jatrabari patterns
- Console spot-check of 20 random data points

### 5. Check for drift
```bash
python main.py drift-scan
```

### 6. Analyze a single screenshot
```bash
python main.py single screenshots/2026-02-25_08-30-00.png
```

## Output Files

| File | Format | Description |
|------|--------|-------------|
| `screenshots/*.png` | PNG | Raw Google Maps screenshots |
| `captures.csv` | CSV | Metadata per screenshot (timestamp, zoom, bounds) |
| `zones.json` | JSON | Grid zone definitions with pixel + geo coordinates |
| `traffic_tabular.csv` | CSV | **Main output** — per-zone congestion data |
| `drift_log.csv` | CSV | Alerts when color distributions shift |

### traffic_tabular.csv columns
```
timestamp_utc, timestamp_local, filename, zone_id, row, col,
green_pct, orange_pct, red_pct, darkred_pct,
congestion_index, total_traffic_pixels, total_pixels
```

- `congestion_index`: 0 (free flow) to 100 (complete gridlock)
- `*_pct`: percentage of traffic-colored pixels in that class

## Tuning Thresholds

If Google Maps changes its color scheme, update `thresholds_v1.json`:
1. Take a fresh screenshot
2. Run `python main.py single <screenshot.png>` to see classification results
3. Open the screenshot in an image editor, sample HSV values of traffic colors
4. Create `thresholds_v2.json` with updated ranges
5. Update `config.json` → `thresholds.file` to point to the new file

## Notes

- The scraper uses **headless Chrome** — no visible browser window
- Screenshots are taken at a **fixed viewport** (1920×1080) and **fixed zoom** (13) to ensure pixel-to-zone mapping is consistent
- The drift detector will alert if >98% of pixels become unclassified (possible UI change) or if class distributions shift by more than 3σ
- Google Maps ToS should be reviewed before deploying at scale
