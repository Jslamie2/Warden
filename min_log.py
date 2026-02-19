import requests
from requests.auth import HTTPDigestAuth
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from google import genai
import os
import time
# Initialize the driver (Chrome example)
import os
from dotenv import load_dotenv




def get_stats_and_serial(miner_ip,USERNAME,PASSWORD):
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
        print(f"error: {miner_ip} - Error: {e}")
        return [miner_ip, "ERROR", str(e)]
    
#note the api_key is free so using it doesn't harm me in anyway.
#Iam prototyping this so yh I dont normally leave my api keys hanging in prod
def llm(max_chars=200,prompt=None):
    api_key = os.getenv("API")
    client = genai.Client(api_key=api_key)
   
    try:
        chat = client.chats.create(
            model="gemma-3-4b-it",
            config={'max_output_tokens': max_chars}
        )
        constrained_prompt = f"You are an ASIC antminer expert, based on the miner give a prediction on how it would take the miner before it stop hashing{prompt})"
        res = chat.send_message(constrained_prompt)
        return  res.text
    except:
        return " model config failed"


def get_log(url):
    driver = webdriver.Chrome()
    last_log_content = ""
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 30)
        try:
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.TAG_NAME, "iframe")))
        except:
            pass
        log_element = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "log-content")))
        while True:
            try:
                raw_text = log_element.get_attribute("textContent") or ""
                if len(raw_text) > len(last_log_content):
                    new_raw_data = raw_text[len(last_log_content):]
                    clean_new_data = " ".join([line.strip() for line in new_raw_data.splitlines() if line.strip()])
                    
                    if clean_new_data:
                        with open("miner_log.txt", "a", encoding="utf-8") as f:
                            f.write(clean_new_data + " ") 
                        
                        diagnoses = llm(prompt = clean_new_data[-20000:])
                        print(diagnoses)
                    
                    last_log_content = raw_text
                
            except Exception:
                log_element = driver.find_element(By.CLASS_NAME, "log-content")
            
            time.sleep(2)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.quit()

url = "http://root:root@10.95.185.162/#blog"
get_log(url)