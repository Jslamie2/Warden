import socket
import time

# The ports used by almost all ASIC miners (Bitmain, Whatsminer, Avalon)
PORTS = [7000, 4000, 53535, 6000]

def main():
    sockets = []
    print("🚀 WARDEN LISTENER ACTIVE")
    print(f"Current PC IP: 10.95.88.216")
    print("-" * 40)

    for p in PORTS:
        try:
            # Create UDP socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Allow address reuse
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Enable Broadcast reception
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # Bind to all interfaces on this port
            s.bind(('', p))
            s.setblocking(False)
            sockets.append((s, p))
            print(f"✅ Listening on Port {p}")
        except Exception as e:
            print(f"❌ Could not open Port {p}: {e}")

    print("-" * 40)
    print("👉 Internet is SAFE. LAN will not disconnect.")
    print("👉 Go to the miner and press the 'IP Report' button.")
    
    try:
        while True:
            for sock, port in sockets:
                try:
                    data, addr = sock.recvfrom(1024)
                    print(f"\n[!] MINER SIGNAL CAPTURED!")
                    print(f"    IP Address: {addr[0]}")
                    print(f"    MAC (Data): {data.hex() if data else 'No Data'}")
                    print(f"    Found on Port: {port}")
                except BlockingIOError:
                    continue
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping Scanner...")
    finally:
        for sock, port in sockets:
            sock.close()

if __name__ == "__main__":
    main()