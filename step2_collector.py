"""
Step 2 — Screenshot Collector
Captures Google Maps traffic screenshots at fixed intervals using Selenium.
Saves timestamped PNGs and logs metadata to captures.csv.
"""

import json
import os
import csv
import time
import uuid
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pytz


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config(path="config.json"):
    with open(path, "r") as f:
        return json.load(f)


def build_maps_url(cfg):
    """
    Build a Google Maps URL with the traffic layer enabled.
    The URL format: https://www.google.com/maps/@{lat},{lng},{zoom}z/data=!5m1!1e1
    The !5m1!1e1 suffix enables the traffic layer.
    """
    lat = cfg["capture"]["center_lat"]
    lng = cfg["capture"]["center_lng"]
    zoom = cfg["capture"]["zoom_level"]
    # !5m1!1e1 = traffic layer ON
    return f"https://www.google.com/maps/@{lat},{lng},{zoom}z/data=!5m1!1e1"


def create_driver(cfg):
    """Create a headless Chrome driver with fixed viewport."""
    width = cfg["capture"]["viewport_width"]
    height = cfg["capture"]["viewport_height"]

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument(f"--window-size={width},{height}")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--force-color-profile=srgb")
    chrome_options.add_argument("--lang=en-US")
    # Disable info bars and automation flags
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=chrome_options)
    driver.set_window_size(width, height)
    return driver


def wait_for_map_load(driver, timeout=30):
    """Wait until the map canvas is rendered."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "canvas"))
        )
        # Extra wait for tiles + traffic overlay to load
        time.sleep(8)
    except Exception:
        # Fallback: just wait a fixed amount
        time.sleep(15)


def dismiss_popups(driver):
    """Try to dismiss cookie consent or other popups."""
    try:
        # Google consent dialog
        buttons = driver.find_elements(By.CSS_SELECTOR, "button")
        for btn in buttons:
            text = btn.text.lower()
            if "accept" in text or "reject" in text or "agree" in text:
                btn.click()
                time.sleep(1)
                break
    except Exception:
        pass


def take_screenshot(driver, save_path):
    """Take a full-page screenshot and save to disk."""
    driver.save_screenshot(save_path)


def init_csv(csv_path):
    """Create the captures CSV if it doesn't exist."""
    if not os.path.exists(csv_path):
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp_utc", "timestamp_local", "filename",
                "zoom", "center_lat", "center_lng",
                "bounds_north", "bounds_south", "bounds_east", "bounds_west",
                "run_id", "machine_id"
            ])


def append_csv(csv_path, row):
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row)


# ---------------------------------------------------------------------------
# Main capture loop
# ---------------------------------------------------------------------------

def capture_loop(config_path="config.json"):
    cfg = load_config(config_path)
    cap = cfg["capture"]

    screenshot_dir = Path(cap["screenshot_dir"])
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    csv_path = cap["captures_csv"]
    init_csv(csv_path)

    interval = cap["interval_seconds"]
    tz = pytz.timezone(cfg["timezone"])
    run_id = str(uuid.uuid4())[:8]
    machine_id = cap["machine_id"]

    url = build_maps_url(cfg)
    print(f"[collector] Maps URL : {url}")
    print(f"[collector] Interval : {interval}s")
    print(f"[collector] Run ID   : {run_id}")
    print(f"[collector] Output   : {screenshot_dir}/")

    iteration = 0
    try:
        while True:
            now_utc = datetime.utcnow()
            now_local = datetime.now(tz)

            filename = now_local.strftime("%Y-%m-%d_%H-%M-%S") + ".png"
            filepath = screenshot_dir / filename

            # Fresh browser for every capture
            print(f"[collector] Opening browser …")
            driver = create_driver(cfg)
            try:
                driver.get(url)
                wait_for_map_load(driver)
                dismiss_popups(driver)
                time.sleep(3)

                take_screenshot(driver, str(filepath))
            finally:
                driver.quit()
                print(f"[collector] Browser closed.")

            row = [
                now_utc.isoformat(),
                now_local.isoformat(),
                filename,
                cap["zoom_level"],
                cap["center_lat"],
                cap["center_lng"],
                cap["bounds"]["north"],
                cap["bounds"]["south"],
                cap["bounds"]["east"],
                cap["bounds"]["west"],
                run_id,
                machine_id,
            ]
            append_csv(csv_path, row)

            iteration += 1
            print(f"[collector] #{iteration}  saved {filename}")

            # Sleep until next interval
            elapsed = (datetime.utcnow() - now_utc).total_seconds()
            sleep_time = max(0, interval - elapsed)
            if sleep_time > 0:
                print(f"[collector] sleeping {sleep_time:.0f}s …")
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n[collector] Stopped by user.")


if __name__ == "__main__":
    capture_loop()
