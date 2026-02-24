import ctypes
import os
import socket
import subprocess
import sys
import time


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


if not is_admin():
    # Relaunch as Admin to allow 'netsh' and raw socket binding
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )
    sys.exit()

try:
    import psutil
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil

# --- CONFIGURATION ---
TARGET_IP = "10.95.53.216"
MASK = "255.255.255.0"
PORTS = [7000, 4000, 53535, 6000]  # Scanning all common miner brands


def find_adapter():
    for adapter, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET and addr.address.startswith("10.95"):
                return adapter
    return None


def main():
    name = find_adapter()
    if not name:
        print("❌ ERROR: No active adapter found on 10.95.x.x network.")
        print("Check your Ethernet cable and ensure your PC has a 10.95 IP.")
        input("Press Enter to exit...")
        return

    print(f"Found Adapter: {name}")
    print(f"Injecting Subnet Alias {TARGET_IP}...")

    subprocess.run(
        f'netsh interface ipv4 add address "{name}" {TARGET_IP} {MASK}',
        shell=True,
        capture_output=True,
    )

    sockets = []
    print("\nINITIALIZING LISTENERS:")
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
            # This prevents the WinError 10013 from crashing the script
            print(f"  [SKIP] Port {p} - Blocked by Firewall or another App")

    if not sockets:
        print(
            "\n❌ CRITICAL: All ports blocked. Disable Windows Firewall/Antivirus and retry."
        )
        input("Press Enter to exit...")
        return

    print("\n" + "=" * 50)
    print(" SCANNER ACTIVE - I AM LISTENING...")
    print("STAND AT THE MINER.")
    print(" PRESS AND HOLD THE 'IP REPORT' BUTTON FOR 10 SECONDS.")
    print("=" * 50)
    print("(Press Ctrl+C to stop and clean up)")

    try:
        while True:
            for sock, port in sockets:
                try:
                    data, addr = sock.recvfrom(1024)
                    print("\n" + "*" * 20)
                    print(f"MINER DETECTED!")
                    print(f"IP ADDRESS : {addr[0]}")
                    print(f"REPORT PORT: {port}")
                    print(f"RAW DATA   : {data.hex()}")
                    print("*" * 20)
                except BlockingIOError:
                    continue
            time.sleep(0.1)  # Prevent 100% CPU usage
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        print(f"\nCLEANING UP: Removing {TARGET_IP}...")
        subprocess.run(
            f'netsh interface ipv4 delete address "{name}" {TARGET_IP}',
            shell=True,
            capture_output=True,
        )
        for sock, port in sockets:
            sock.close()
        print("Done.")
        input("Press Enter to close.")


if __name__ == "__main__":
    main()
