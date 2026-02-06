import requests
from requests.auth import HTTPDigestAuth
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
# Initialize the driver (Chrome example)


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
        print(sys_data)
        serial_number = sys_data.get("serinum", "N/A")

    except Exception as e:
        print(f"❌ {miner_ip} - Error: {e}")
        return [miner_ip, "ERROR", str(e)]
    

def get_log():
    driver = webdriver.Chrome()
    last_log_content = ""  # Track what we've already seen

    try:
        url = "http://root:root@10.95.47.132/#blog"
        driver.get(url)
        wait = WebDriverWait(driver, 20)
        log_element = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "log-content")))
        print("--- Started Real-Time Monitoring (Press Ctrl+C to stop) ---")

        while True:
            current_full_text = log_element.text
            if current_full_text != last_log_content:
                new_data = current_full_text[len(last_log_content):]
                if new_data:
                    print(new_data, end="") # Print new lines as they appear
                    with open("miner_log.txt", "a", encoding="utf-8") as f:
                        f.write(new_data)
                
                last_log_content = current_full_text
            time.sleep(2) 

    except KeyboardInterrupt:
        print("\nMonitoring stopped by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()

get_log()