import socket
import struct
import subprocess
import sys
import ctypes
import os
import time

def add_firewall_rule(port):
    """Programmatically adds a Windows Firewall rule for the listener."""
    rule_name = "Antminer_IP_Reporter"
    subprocess.run(f'netsh advfirewall firewall delete rule name="{rule_name}"', 
                   shell=True, capture_output=True)
    
    
    cmd = f'netsh advfirewall firewall add rule name="{rule_name}" dir=in action=allow protocol=UDP localport={port}'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"[+] Firewall: Rule '{rule_name}' added for UDP port {port}.")
    else:
        print(f"[!] Firewall: Failed to add rule. Error: {result.stderr}")

def start_listener(port=14235):
    """Main UDP listener logic."""
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    subnet_prefix = ".".join(local_ip.split(".")[:3])

    print(f"\n" + "="*50)
    print(f" WARDEN IP REPORTER - ACTIVE")
    print(f"="*50)
    print(f"[*] Local IP: {local_ip}")
    print(f"[*] Listening on Port: {port}")
    print(f"[*] Expecting Miner on: {subnet_prefix}.x")
    print(f"[*] Status: Waiting for 'IP Report' button press...")
    print(f"="*50 + "\n")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Allow socket reuse to avoid "port already in use" errors
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        sock.bind(('0.0.0.0', port))
        while True:
            data, addr = sock.recvfrom(1024)
            # Try different packet formats to get the local IP
            if len(data) >= 11:
                try:
                    # Standard format: header(1) + MAC(6) + IP(4)
                    _, mac_raw, ip_raw = struct.unpack('>B6s4s', data[:11])
                    mac_str = ':'.join(f'{b:02x}' for b in mac_raw)
                    ip_str = socket.inet_ntoa(ip_raw)
                    
                    # Check if we got a valid local IP (10.95.x.x)
                    # If not, try alternative packet format
                    if not ip_str.startswith('10.95.'):
                        # Try offset - sometimes IP is at different position
                        if len(data) >= 18:
                            _, mac_raw, _, ip_raw = struct.unpack('>B6sB4s', data[:12])
                            ip_str = socket.inet_ntoa(ip_raw)
                    
                    # Use the ORIGIN IP if extracted IP is not local
                    if not ip_str.startswith('10.95.'):
                        ip_str = addr[0]
                    
                    print(f"[{time.strftime('%H:%M:%S')}] >>> BUTTON PRESSED <<<")
                    print(f"    MINER IP:  {ip_str}")
                    print(f"    MINER MAC: {mac_str}")
                    print(f"    ORIGIN:    {addr[0]}")
                    if ".".join(ip_str.split(".")[:2]) != ".".join(addr[0].split(".")[:2]):
                        print(f"    [!] WARNING: Miner is on a different subnet!")
                    print("-" * 30)
                    
                except Exception as parse_err:
                    print(f"[!] Error parsing packet: {parse_err}")
                    
    except Exception as e:
        print(f"[!] Socket Error: {e}")
    finally:
        sock.close()

if __name__ == "__main__":
    # Check if already running as admin
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except:
        is_admin = False
    
    if not is_admin:
        print("[*] Requesting Administrator privileges to configure Firewall...")
        print("[*] Please accept the UAC prompt...")
        
        # Get full path to the script
        script_path = sys.argv[0]
        if not os.path.isabs(script_path):
            script_path = os.path.abspath(script_path)
        
        # Use cmd /k to keep window open after launching
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "cmd", f'/k cd /d "{os.path.dirname(script_path)}" && python "{script_path}"', None, 1
        )
        
        print("[*] Admin window should open now.")
        print("[*] This window will close in 3 seconds...")
        time.sleep(3)
        sys.exit()
    
    # Only reaches here if running as admin
    add_firewall_rule(12207)
    add_firewall_rule(14235)
    
    print("\n" + "="*50)
    print(" WARDEN IP REPORTER - ADMIN MODE")
    print("="*50 + "\n")
    
    try:
        start_listener(14235)
    except KeyboardInterrupt:
        print("\n[*] Shutting down...")
    except Exception as e:
        print(f"[!] Error: {e}")
        print("\n[*] Press Enter to exit...")
        input()

