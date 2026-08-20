import requests
from bs4 import BeautifulSoup
import csv
import time
import os
import json
import signal
import sys
import functools

# Force flush semua print supaya log langsung muncul di GitHub Actions
print = functools.partial(print, flush=True)

# ===== KONFIGURASI =====
INPUT_CSV = "data_dikmen.csv"
OUTPUT_CSV = "data_dikmen_email.csv"
PROGRESS_FILE = "scrape_email_progress.json"
DELAY = 2             # delay antar request (detik)
TIMEOUT = 60          # timeout per request
MAX_RETRIES = 5       # max retry per halaman
RETRY_DELAY = 10      # delay awal saat retry
MAX_RUNTIME = int(os.getenv("MAX_RUNTIME", 5 * 60 * 60))  # default 5 jam (batas aman GitHub Actions); set env MAX_RUNTIME utk run lokal

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": "https://referensi.data.kemendikdasmen.go.id"
}

start_time = time.time()
stopping = False


def time_is_up():
    """Cek apakah sudah mendekati batas waktu."""
    elapsed = time.time() - start_time
    return elapsed >= MAX_RUNTIME


def handle_stop(signum, frame):
    """Handle Ctrl+C supaya progress tetap tersimpan."""
    global stopping
    print("\n[!] Stop signal diterima, menyimpan progress...")
    stopping = True


signal.signal(signal.SIGTERM, handle_stop)
signal.signal(signal.SIGINT, handle_stop)


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {"last_index": -1}


def save_progress(index):
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"last_index": index}, f)


def fetch(url):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.RequestException as e:
            print(f"  [!] Gagal (attempt {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                wait = RETRY_DELAY * attempt
                print(f"  [~] Retry dalam {wait} detik...")
                time.sleep(wait)
            else:
                return None


def get_email_from_detail(npsn):
    url = f"https://referensi.data.kemendikdasmen.go.id/pendidikan/npsn/{npsn}"
    html = fetch(url)
    if not html:
        return {"Email": "-", "Telepon": "-", "Fax": "-", "Website": "-"}

    soup = BeautifulSoup(html, "html.parser")
    result = {"Email": "-", "Telepon": "-", "Fax": "-", "Website": "-"}

    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) >= 4:
                label = tds[1].get_text(strip=True).lower()
                value = tds[3].get_text(strip=True)
                if "email" in label:
                    result["Email"] = value if value else "-"
                elif "telepon" in label:
                    result["Telepon"] = value if value else "-"
                elif "fax" in label:
                    result["Fax"] = value if value else "-"
                elif "website" in label:
                    result["Website"] = value if value else "-"
    return result


def main():
    global stopping

    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    total = len(reader)
    progress = load_progress()
    start_index = progress["last_index"] + 1

    original_fields = list(reader[0].keys())
    extra_fields = ["Email", "Telepon", "Fax", "Website"]
    output_fields = [f for f in original_fields if f not in extra_fields] + extra_fields

    write_mode = "a" if start_index > 0 else "w"

    with open(OUTPUT_CSV, write_mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields)
        if start_index == 0:
            writer.writeheader()

        print("=" * 60)
        print("  Scraper Email Dikmen (GitHub Actions)")
        print(f"  Total data  : {total}")
        print(f"  Mulai dari  : {start_index + 1}")
        print(f"  Delay       : {DELAY} detik")
        print(f"  Max runtime : {MAX_RUNTIME // 3600} jam")
        print("=" * 60)
        print()

        for i in range(start_index, total):
            # Cek batas waktu atau stop signal
            if time_is_up() or stopping:
                elapsed = int(time.time() - start_time)
                print(f"\n[!] Berhenti di index {i} (elapsed: {elapsed}s)")
                print(f"  Progress tersimpan. Jalankan ulang untuk lanjut.")
                save_progress(i - 1)
                return

            row = reader[i]
            npsn = row.get("NPSN", "").strip()
            nama = row.get("Nama Satuan Pendidikan", "")[:40]
            print(f"[{i+1}/{total}] {npsn} - {nama}", end=" ")

            if not npsn or npsn == "-":
                detail = {"Email": "-", "Telepon": "-", "Fax": "-", "Website": "-"}
                print("-> SKIP")
            else:
                detail = get_email_from_detail(npsn)
                print(f"-> {detail['Email']}")

            out_row = {k: v for k, v in row.items() if k in output_fields}
            out_row.update(detail)
            writer.writerow(out_row)
            f.flush()
            save_progress(i)
            time.sleep(DELAY)

    # Selesai semua
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)

    print()
    print("=" * 60)
    print("  SELESAI SEMUA!")
    print(f"  Total: {total} sekolah")
    print(f"  Output: {OUTPUT_CSV}")
    print("=" * 60)


if __name__ == "__main__":
    main()
