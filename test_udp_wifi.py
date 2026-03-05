"""
Quick UDP test to check if WiFi is blocking broadcasts
Run this while the listener is running to see if packets get through
"""
import socket
import time

def test_udp_wifi():
    print("="*50)
    print("UDP WiFi Connectivity Test")
    print("="*50)
    
    # Get local IP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    local_ip = s.getsockname()[0]
    s.close()
    
    print(f"Local IP: {local_ip}")
    subnet = ".".join(local_ip.split(".")[:3])
    broadcast_addr = f"{subnet}.255"
    print(f"Broadcast address: {broadcast_addr}")
    print()
    
    # Test 1: Send broadcast to subnet
    print("[Test 1] Sending UDP broadcast to subnet...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(b"TEST_BROADCAST", (broadcast_addr, 14235))
        sock.close()
        print("    Sent successfully")
    except Exception as e:
        print(f"    FAILED: {e}")
    
    # Test 2: Send to all interfaces
    print("[Test 2] Sending UDP to all interfaces (0.0.0.0)...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(b"TEST_ALL", ('0.0.0.0', 14235))
        sock.close()
        print("    Sent successfully")
    except Exception as e:
        print(f"    FAILED: {e}")
    
    # Test 3: Send to localhost
    print("[Test 3] Sending UDP to localhost...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(b"TEST_LOCAL", ('127.0.0.1', 14235))
        sock.close()
        print("    Sent successfully")
    except Exception as e:
        print(f"    FAILED: {e}")
    
    # Test 4: Check if we can receive on the port
    print("[Test 4] Quick receive test (2 seconds)...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', 14235))
        sock.setblocking(False)
        
        start = time.time()
        while time.time() - start < 2:
            try:
                data, addr = sock.recvfrom(1024)
                print(f"    RECEIVED: {data} from {addr}")
            except BlockingIOError:
                time.sleep(0.1)
        sock.close()
        print("    No packets received in 2 seconds")
    except Exception as e:
        print(f"    FAILED: {e}")
    
    print()
    print("="*50)
    print("If tests 1-3 failed, your WiFi is blocking UDP broadcasts")
    print("="*50)

if __name__ == "__main__":
    test_udp_wifi()
    input("\nPress Enter to exit...")

