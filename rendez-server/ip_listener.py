import socket
import subprocess
import time
import sys
import ctypes

# --- CONFIGURATION ---
ADAPTER_NAME = "Ethernet 3"  # From your ipconfig
MINER_SUB_IP = "10.95.51.216" # An IP in the miner's range
NETMASK = "255.255.255.0"
PORT = 7000 # Antminer standard discovery port

def is_admin():
    try: return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False

def main():
    if not is_admin():
        print("🛡️ Elevation required to add Subnet Alias...")
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()

    # Step 1: Add a secondary IP so we are on the same subnet as the Antminer
    print(f"🔗 Joining Antminer Subnet ({MINER_SUB_IP})...")
    subprocess.run(f'netsh interface ipv4 add address "{ADAPTER_NAME}" {MINER_SUB_IP} {NETMASK} skipassource=True', shell=True)

    # Step 2: Setup the Listener
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        # Bind to ALL interfaces on Port 7000
        sock.bind(('', PORT))
        sock.settimeout(1.0)
        
        print("\n" + "="*50)
        print("🎯 ANTMINER DISCOVERY ACTIVE")
        print("👉 Go to the Antminer.")
        print("👉 Press and HOLD the 'IP Report' button for 5 seconds.")
        print("="*50)

        while True:
            try:
                data, addr = sock.recvfrom(1024)
                # Antminer packets usually contain the MAC address in the payload
                print(f"\n[!] ANTMINER DETECTED!")
                print(f"    IP ADDRESS : {addr[0]}")
                print(f"    RAW DATA   : {data.hex()}")
            except socket.timeout:
                continue
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        # Step 3: Cleanup
        print(f"🧹 Removing temporary IP {MINER_SUB_IP}...")
        subprocess.run(f'netsh interface ipv4 delete address "{ADAPTER_NAME}" {MINER_SUB_IP}', shell=True)
        sock.close()

if __name__ == "__main__":
    main()