import requests
from requests.auth import HTTPDigestAuth
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import csv
import random
import string
from tkinter import Tk, filedialog

# 🖱️ File picker for IP CSV
Tk().withdraw()
csv_path = filedialog.askopenfilename(
    title="Select CSV file containing miner IPs",
    filetypes=[("CSV files", "*.csv")]
)
df = pd.read_csv(csv_path)
miner_ips = df.iloc[:, 0].dropna().astype(str).tolist()

USERNAME = "root"
PASSWORD = "root"

def get_stats_and_serial(miner_ip):
    rate_sale = "N/A"
    serial_number = "N/A"

    try:
        # 🔍 1. Get rate_sale
        stats_url = f"http://{miner_ip}/cgi-bin/stats.cgi"
        stats_res = requests.get(stats_url, auth=HTTPDigestAuth(USERNAME, PASSWORD), timeout=5)
        stats_res.raise_for_status()
        stats_data = stats_res.json()
        if "STATS" in stats_data and isinstance(stats_data["STATS"], list):
            rate_sale_val = stats_data["STATS"][0].get("rate_sale")
            if rate_sale_val:
                rate_sale = f"{rate_sale_val} GH/s"

        # 🔍 2. Get serial number
        sys_url = f"http://{miner_ip}/cgi-bin/get_system_info.cgi"
        sys_res = requests.get(sys_url, auth=HTTPDigestAuth(USERNAME, PASSWORD), timeout=5)
        sys_res.raise_for_status()
        sys_data = sys_res.json()
        serial_number = sys_data.get("serinum", "N/A")

    except Exception as e:
        print(f"❌ {miner_ip} - Error: {e}")
        return [miner_ip, "ERROR", str(e)]

    print(f"✅ {miner_ip} → Serial: {serial_number}, Rate Sale: {rate_sale}")
    return [miner_ip, serial_number, rate_sale]

def scan_miners(miner_ips, max_threads=10):
    results = []
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = [executor.submit(get_stats_and_serial, ip) for ip in miner_ips]
        for future in as_completed(futures):
            results.append(future.result())
    return results

def save_results_to_csv(results):
    filename = f"miner_data_{''.join(random.choices(string.ascii_uppercase + string.digits, k=5))}.csv"
    with open(filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Miner IP", "Serial Number", "Rate Sale"])
        writer.writerows(results)
    print(f"\n✅ Results saved to {filename}")

if __name__ == "__main__":
    results = scan_miners(miner_ips)
    save_results_to_csv(results)
