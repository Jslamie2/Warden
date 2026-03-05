import socket
import struct
import subprocess
import sys
import ctypes
import os
import time
import ipaddress
import select

def get_local_ips():
    """
    Get all local IP addresses from all network interfaces.
    Works reliably on systems with both WiFi and Ethernet.
    """
    local_ips = []
    try:
        # Method 1: Use socket connections to get actual interface IPs
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Connect to external address (doesn't actually send data)
            # This forces the OS to choose the correct interface
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            local_ips.append(local_ip)
        except:
            pass
        finally:
            s.close()
        
        # Method 2: Get all interface IPs using getaddrinfo
        try:
            hostname = socket.gethostname()
            results = socket.getaddrinfo(hostname, None)
            for result in results:
                if result[0] == socket.AF_INET:  # IPv4 only
                    ip = result[4][0]
                    if ip not in local_ips and not ip.startswith("127."):
                        local_ips.append(ip)
        except:
            pass
        
        # Method 3: Fallback to hostname resolution
        try:
            fallback_ip = socket.gethostbyname(hostname)
            if fallback_ip not in local_ips and not fallback_ip.startswith("127."):
                local_ips.append(fallback_ip)
        except:
            pass
            
    except Exception as e:
        print(f"[!] Warning: Error detecting local IPs: {e}")
    
    # Remove duplicates and filter out localhost
    local_ips = list(set([ip for ip in local_ips if not ip.startswith("127.")]))
    return local_ips if local_ips else ["127.0.0.1"]


def get_preferred_local_ip():
    """
    Get the preferred local IP address, prioritizing non-unicast and non-link-local.
    On WiFi systems, this returns the actual interface IP, not 0.0.0.0 or 127.0.0.1.
    """
    local_ips = get_local_ips()
    
    # Priority: prefer non-192.168, non-10.x (often VPN), prefer actual interface IPs
    # For WiFi, we typically want the IP assigned to the wireless adapter
    for ip in local_ips:
        # Skip common VPN ranges first
        if ip.startswith("10.8.") or ip.startswith("172.16."):
            continue
        # Return first valid local IP
        return ip
    
    # Fallback to first available
    return local_ips[0] if local_ips else "0.0.0.0"


def get_subnet_prefix(ip):
    """Extract the /24 subnet prefix from an IP address."""
    return ".".join(ip.split(".")[:3])


def is_same_subnet(ip1, ip2):
    """Check if two IPs are on the same /24 subnet."""
    return get_subnet_prefix(ip1) == get_subnet_prefix(ip2)


def is_valid_local_ip(ip_str):
    """Check if an IP string is a valid local IP address."""
    if not ip_str:
        return False
    # Check for invalid prefixes
    if ip_str.startswith('0.') or ip_str.startswith('127.') or ip_str.startswith('255.'):
        return False
    # Check for valid private ranges
    try:
        ip = ipaddress.ip_address(ip_str)
        # Check if it's a private IP
        return ip.is_private
    except:
        return False


def get_broadcast_addresses():
    """
    Get broadcast addresses for all detected network interfaces.
    Essential for WiFi where broadcast may not work on 0.0.0.0
    """
    broadcast_ips = []
    local_ips = get_local_ips()
    
    for ip in local_ips:
        subnet = get_subnet_prefix(ip)
        broadcast_ips.append(f"{subnet}.255")
    
    return broadcast_ips


def add_firewall_rule(port):
    """Programmatically adds a Windows Firewall rule for the listener - includes all profiles."""
    rule_name = "Antminer_IP_Reporter"
    
    # Delete existing rule
    subprocess.run(f'netsh advfirewall firewall delete rule name="{rule_name}"', 
                   shell=True, capture_output=True)
    
    # Add rule for all profiles (Domain, Private, Public) - critical for WiFi
    cmd = f'netsh advfirewall firewall add rule name="{rule_name}" dir=in action=allow protocol=UDP localport={port} enable=yes profile=any'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"[+] Firewall: Rule '{rule_name}' added for UDP port {port} (all profiles).")
    else:
        print(f"[!] Firewall: Failed to add rule. Error: {result.stderr}")
    
    # Also try netsh command for specific profiles if the above doesn't work
    for profile in ["Public", "Private", "Domain"]:
        cmd = f'netsh advfirewall firewall add rule name="{rule_name}_{profile}" dir=in action=allow protocol=UDP localport={port} enable=yes profile={profile}'
        subprocess.run(cmd, shell=True, capture_output=True, text=True)


def check_firewall_and_network():
    """Check Windows Firewall status and current network profile."""
    print("\n" + "="*50)
    print(" CHECKING FIREWALL & NETWORK STATUS")
    print("="*50)
    
    # Check firewall status for UDP
    result = subprocess.run('netsh advfirewall firewall show rule name=all', 
                           shell=True, capture_output=True, text=True)
    if "Antminer_IP_Reporter" in result.stdout:
        print("[+] Antminer firewall rules found:")
        for line in result.stdout.split('\n'):
            if "Antminer_IP_Reporter" in line:
                print(f"    {line}")
    else:
        print("[!] No Antminer firewall rules found!")
    
    # Check current network profiles
    print("\n[*] Network profiles active:")
    result = subprocess.run('netsh advfirewall monitor show currentprofile', 
                           shell=True, capture_output=True, text=True)
    print(result.stdout)
    
    # Check if UDP ports are open
    print("[*] Checking if ports are listening:")
    result = subprocess.run('netstat -ano | findstr ":14235"', 
                           shell=True, capture_output=True, text=True)
    if result.stdout:
        print(f"    Port 14235: {result.stdout.strip()}")
    else:
        print("    Port 14235: NOT LISTENING")
    
    result = subprocess.run('netstat -ano | findstr ":12207"', 
                           shell=True, capture_output=True, text=True)
    if result.stdout:
        print(f"    Port 12207: {result.stdout.strip()}")
    else:
        print("    Port 12207: NOT LISTENING")
    
    print("="*50 + "\n")


def start_listener(port=14235):
    """Main UDP listener logic optimized for WiFi and multi-interface systems."""
    # Get all available local IPs and use the preferred one
    local_ips = get_local_ips()
    local_ip = get_preferred_local_ip()
    subnet_prefix = get_subnet_prefix(local_ip)
    broadcast_addrs = get_broadcast_addresses()
    
    # Display all detected network interfaces for debugging
    print(f"\n" + "="*50)
    print(f" WARDEN IP REPORTER - ACTIVE (WiFi Optimized)")
    print(f"="*50)
    print(f"[*] Detected Network Interfaces:")
    for idx, ip in enumerate(local_ips):
        print(f"    [{idx+1}] {ip}")
    print(f"[*] Broadcast Addresses:")
    for bcast in broadcast_addrs:
        print(f"    - {bcast}")
    print(f"[*] Primary IP: {local_ip}")
    print(f"[*] Listening on Ports: {port}, 12207")
    print(f"[*] Expecting Miner on: {subnet_prefix}.x")
    print(f"[*] Status: Waiting for 'IP Report' button press...")
    print(f"="*50 + "\n")
    
    # Create socket with larger buffer for WiFi
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
    
    # Try binding to multiple addresses for WiFi compatibility
    bound = False
    
    # First try: bind to all interfaces (0.0.0.0)
    try:
        sock.bind(('0.0.0.0', port))
        print(f"[*] Bound to 0.0.0.0:{port}")
        bound = True
    except Exception as e:
        print(f"[!] Failed to bind to 0.0.0.0:{port} - {e}")
    
    # Second try: if on WiFi, also try binding to specific broadcast addresses
    if not bound:
        for bcast in broadcast_addrs:
            try:
                sock.bind((bcast, port))
                print(f"[*] Bound to {bcast}:{port}")
                bound = True
                break
            except:
                pass
    
    # Note: Binding to 255.255.255.255 doesn't work on Windows, skip silently
    # The 0.0.0.0 binding should work for most cases
    
    # Also listen on the alternative port 12207 that miners sometimes use
    try:
        sock2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock2.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock2.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
        sock2.bind(('0.0.0.0', 12207))
        print(f"[*] Also listening on port 12207")
    except Exception as e:
        print(f"[-] Could not bind to port 12207: {e}")
        sock2 = None
    
    print(f"[*] Ready to receive packets...\n")
    
    try:
        while True:
            # Use select to listen on both sockets
            sockets_to_watch = [sock]
            if sock2:
                sockets_to_watch.append(sock2)
            
            readable = select.select(sockets_to_watch, [], [], 1.0)[0]
            
            for ready_sock in readable:
                try:
                    data, addr = ready_sock.recvfrom(1024)
                    print(f"[DEBUG] Received {len(data)} bytes from {addr[0]}:{addr[1]}")
                    print(f"[DEBUG] Raw data: {data.hex()}")
                    
                    if len(data) >= 11:
                        try:
                            _, mac_raw, ip_raw = struct.unpack('>B6s4s', data[:11])
                            mac_str = ':'.join(f'{b:02x}' for b in mac_raw)
                            ip_str = socket.inet_ntoa(ip_raw)
                            
                            # Validate the extracted IP - if it's invalid or looks like localhost,
                            # use the source address from the packet instead (more reliable on WiFi)
                            if not ip_str or ip_str.startswith('0.') or ip_str.startswith('127.') or ip_str.startswith('255.'):
                                ip_str = addr[0]
                            
                            # Check if we need to parse alternative format
                            # Some miners send data in different packet formats
                            if not is_valid_local_ip(ip_str):
                                if len(data) >= 18:
                                    try:
                                        _, mac_raw, _, ip_raw = struct.unpack('>B6sB4s', data[:12])
                                        ip_str = socket.inet_ntoa(ip_raw)
                                    except:
                                        pass
                            
                            # Final fallback to source address if still invalid
                            if not is_valid_local_ip(ip_str):
                                ip_str = addr[0]
                            
                            print(f"[{time.strftime('%H:%M:%S')}] >>> BUTTON PRESSED <<<")
                            print(f"    MINER IP:  {ip_str}")
                            print(f"    MINER MAC: {mac_str}")
                            print(f"    ORIGIN:    {addr[0]}")
                            print(f"    PORT:      {addr[1]}")
                            
                            # Use the improved subnet check
                            if not is_same_subnet(ip_str, addr[0]):
                                print(f"    [!] WARNING: Miner is on a different subnet!")
                            
                            # Also check if miner is on our detected subnets
                            miner_on_our_network = False
                            for detected_ip in local_ips:
                                if is_same_subnet(ip_str, detected_ip):
                                    miner_on_our_network = True
                                    break
                            if not miner_on_our_network:
                                print(f"    [!] WARNING: Miner not on any detected network interface!")
                            
                            print("-" * 30)
                            
                        except Exception as parse_err:
                            print(f"[!] Error parsing packet: {parse_err}")
                            
                except Exception as recv_err:
                    print(f"[!] Receive error: {recv_err}")
                    
    except Exception as e:
        print(f"[!] Socket Error: {e}")
    finally:
        sock.close()
        if sock2:
            sock2.close()


if __name__ == "__main__":
    # Check if already running as admin
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except:
        is_admin = False
    
    if not is_admin:
        print("[*] Requesting Administrator privileges to configure Firewall...")
        print("[*] Please accept the UAC prompt...")
        script_path = sys.argv[0]
        if not os.path.isabs(script_path):
            script_path = os.path.abspath(script_path)
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "cmd", f'/k cd /d "{os.path.dirname(script_path)}" && python "{script_path}"', None, 1
        )
        
        print("[*] Admin window should open now.")
        print("[*] This window will close in 3 seconds...")
        time.sleep(3)
        sys.exit()
    add_firewall_rule(12207)
    add_firewall_rule(14235)
    
    # Check firewall and network status
    check_firewall_and_network()
    
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

