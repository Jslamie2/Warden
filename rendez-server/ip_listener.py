import ctypes
import os
import socket
import subprocess
import sys
import time
import signal
import atexit

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
    sys.exit()

try:
    import psutil
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil

# --- CONFIGURATION ---
TARGET_IP = "10.95.53.216"
MASK = "255.255.255.0"
PORTS = [7000, 4000, 53535, 6000]
ADAPTER_NAME = None # Will be set globally

def cleanup():
    """The 'Nuclear' Cleanup: Force adapter back to DHCP"""
    if ADAPTER_NAME:
        print(f"\n[CLEANUP] Resetting {ADAPTER_NAME} to DHCP...")
        # Delete specific address
        subprocess.run(f'netsh interface ipv4 delete address "{ADAPTER_NAME}" {TARGET_IP}', shell=True, capture_output=True)
        # Force DHCP just in case
        subprocess.run(f'netsh interface ip set address "{ADAPTER_NAME}" dhcp', shell=True, capture_output=True)
        # Refresh connection
        subprocess.run('ipconfig /renew', shell=True, capture_output=True)
        print("[CLEANUP] Internet restored.")

# Register cleanup to run even on crashes or sys.exit()
atexit.register(cleanup)

def signal_handler(sig, frame):
    sys.exit(0)

# Catch Ctrl+C and other terminations
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def find_adapter():
    for adapter, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET and addr.address.startswith("10.95"):
                return adapter
    return None

def main():
    global ADAPTER_NAME
    ADAPTER_NAME = find_adapter()
    
    if not ADAPTER_NAME:
        print("ERROR: No active adapter found on 10.95.x.x network.")
        return

    print(f"Found Adapter: {ADAPTER_NAME}")
    print(f"Injecting Subnet Alias {TARGET_IP}...")

    subprocess.run(f'netsh interface ipv4 add address "{ADAPTER_NAME}" {TARGET_IP} {MASK}', shell=True)

    sockets = []
    for p in PORTS:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind(("", p))
            s.setblocking(False)
            sockets.append((s, p))
            print(f"  [OPEN] Port {p}")
        except OSError:
            print(f"  [SKIP] Port {p} - Blocked")

    print("\nSCANNER ACTIVE - Press Ctrl+C to stop and restore internet.")

    try:
        while True:
            for sock, port in sockets:
                try:
                    data, addr = sock.recvfrom(1024)
                    print(f"\nMINER DETECTED! IP: {addr[0]}")
                except BlockingIOError:
                    continue
            time.sleep(0.1)
    except SystemExit:
        pass # atexit handles this

if __name__ == "__main__":
    main()