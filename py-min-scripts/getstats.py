import socket
import json

def get_miner_stats(ip, port=4028):
    # The standard command format for cgminer/bmminer API
    command = {"command": "stats"}
    
    try:
        # 1. Create a TCP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5) # 5 second timeout
        
        # 2. Connect to the miner
        sock.connect((ip, port))
        
        # 3. Send the command (JSON string)
        sock.sendall(json.dumps(command).encode('utf-8'))
        
        # 4. Receive the response
        response = b""
        while True:
            data = sock.recv(4096)
            if not data:
                break
            response += data
            
        sock.close()
        
        # 5. Parse and return the JSON (ignoring the null-byte at the end)
        return json.loads(response.decode('utf-8').replace('\x00', ''))

    except Exception as e:
        return {"error": f"Could not connect to {ip}: {e}"}

# --- Usage ---
miner_ip = "10.95.255.227"  # Replace with your miner's IP
stats = get_miner_stats(miner_ip)

if "error" in stats:
    print(stats["error"])
else:
    # Print the full stats or specific info
    print(f"Miner Type: {stats['STATS'][0]['Type']}")
    print(f"Elapsed Time: {stats['STATS'][1]['Elapsed']} seconds")
    # Temperature and Hashrate are usually in the second STATS object
    print(f"GHS 5s (Hashrate): {stats['STATS'][1].get('GHS 5s')}")