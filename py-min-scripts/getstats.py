import socket
import json

def get_miner_stats(ip, port=4028):
    command = {"command": "stats"}
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5) # 5 second timeout
        sock.connect((ip, port))
        sock.sendall(json.dumps(command).encode('utf-8'))
        response = b""
        while True:
            data = sock.recv(4096)
            if not data:
                break
            response += data
            
        sock.close()
        return json.loads(response.decode('utf-8').replace('\x00', ''))
    except Exception as e:
        return {"error": f"Could not connect to {ip}: {e}"}

# --- Usage ---
miner_ip = "10.95.53.85"  # Replace with your miner's IP
stats = get_miner_stats(miner_ip)
print(stats)
