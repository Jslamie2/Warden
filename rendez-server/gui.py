import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import threading
import socket
import struct
import time
import ipaddress
import webbrowser
from datetime import datetime
import queue
import sys
import json
import asyncio
import websockets
from database import init_db, get_or_create_user, report_miner, mark_visited, get_collisions, insert_broadcast, get_roster, get_unvisited_miners, get_miner_reporters, get_user_display_name, delete_miner

# Import the listener functions from ip_listener
sys.path.insert(0, '.')
try:
    from ip_listener import get_local_ips, get_preferred_local_ip, get_subnet_prefix, is_same_subnet, is_valid_local_ip, add_firewall_rule
except ImportError:
    # Fallback functions if ip_listener not available
    def get_local_ips():
        local_ips = []
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ips.append(s.getsockname()[0])
            s.close()
        except: pass
        return local_ips if local_ips else ["127.0.0.1"]
    
    def get_preferred_local_ip():
        return get_local_ips()[0]
    
    def get_subnet_prefix(ip):
        return ".".join(ip.split(".")[:3])
    
    def is_same_subnet(ip1, ip2):
        return get_subnet_prefix(ip1) == get_subnet_prefix(ip2)
    
    def is_valid_local_ip(ip_str):
        if not ip_str: return False
        if ip_str.startswith('0.') or ip_str.startswith('127.') or ip_str.startswith('255.'): return False
        try:
            return ipaddress.ip_address(ip_str).is_private
        except: return False
    
    def add_firewall_rule(port): pass


class MinerIPReporterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Warden - IP Reporter (Network-Aware)")
        self.root.geometry("1100x800")
        self.root.configure(bg="#1a1a2e")
        
        # Initialize DB
        init_db()
        
        # Get/create user
        self.hostname = socket.gethostname()
        self.user = get_or_create_user()
        self.user_id = self.user['id']
        self.display_name = self.user.get('display_name', self.hostname)
        self.user_id = self.user['id']
        self.hostname = socket.gethostname()
        self.display_name = self.user.get('display_name', self.hostname)
        self.local_ip = get_preferred_local_ip()
        self.subnet_prefix = get_subnet_prefix(self.local_ip)
        print(f"Initialized: User ID {self.user_id} ({self.hostname}), Subnet {self.subnet_prefix}")
        
        # Data structures
        self.miner_entries = {}  # temp UI cache
        self.listening = False
        self.ws_connected = False
        self.listener_thread = None
        self.ws_thread = None
        self.packet_queue = queue.Queue()
        self.roster_data = {}  # network roster cache
        
        # Colors
        self.bg_dark = "#16213e"
        self.bg_card = "#0f3460"
        self.accent = "#e94560"
        self.text_white = "#ffffff"
        self.text_gray = "#a0a0a0"
        self.visited_color = "#4ecca3"
        self.conflict_color = "#ffaa00"
        
        # WS config
        self.ws_uri = "ws://localhost:8765"
        self.peer_id = f"{self.user_id}-{self.hostname[:8]}"
        self.room_id = self.subnet_prefix
        
        # Start WS thread (async event loop in thread)
        self.ws_thread = threading.Thread(target=self.ws_client_loop, daemon=True)
        self.ws_thread.start()
        
        self.setup_ui()
        self.process_queue()
        self.update_local_ip()
    
    def ws_client_loop(self):
        """Async WS client loop in thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.ws_async_client())
    
    async def ws_async_client(self):
        """Async WS connection/reconnect."""
        while True:
            try:
                async with websockets.connect(self.ws_uri) as ws:
                    self.ws_connected = True
                    print(f"WS connected as {self.peer_id} in room {self.room_id}")
                    
                    # Register
                    await ws.send(json.dumps({
                        "action": "register",
                        "peer_id": self.peer_id,
                        "metadata": {
                            "user_id": self.user_id,
                            "hostname": self.hostname,
                            "subnet": self.subnet_prefix,
                            "type": "warden_gui"
                        }
                    }))
                    
                    # Join room
                    await ws.send(json.dumps({
                        "action": "join_room",
                        "room_id": self.room_id
                    }))
                    
                    # List peers / roster
                    await ws.send(json.dumps({"action": "list_peers"}))
                    
                    async for message in ws:
                        data = json.loads(message)
                        self.handle_ws_message(data)
                        
            except Exception as e:
                self.ws_connected = False
                print(f"WS disconnect: {e}")
                await asyncio.sleep(5)
    
    def handle_ws_message(self, data):
        """Handle incoming WS messages."""
        msg_type = data.get('type')
        if msg_type == 'registered':
            print(f"WS registered: {data}")
        elif msg_type == 'peer_list':
            self.roster_data = data
            # Update roster UI
            self.root.after(0, self.update_roster_ui)
        elif msg_type == 'broadcast':
            self.root.after(0, lambda: self.handle_broadcast(data))
    
    def handle_broadcast(self, data):
        """Handle broadcast msg (collision, url_available)."""
        msg = data['message']
        msg_type = msg.get('type')
        if msg_type == 'ip_assigned':
            mac = msg['mac']
            other_user = msg['computer_name']
            messagebox.showinfo("Network Assignment", f"{other_user} assigned miner {mac}")
        elif msg_type == 'collision_alert':
            messagebox.showwarning("Collision!", msg['alert'])
    
    def update_roster_ui(self):
        """Update network roster display."""
        from database import get_all_users
        self.roster_text.delete(1.0, tk.END)
        users = get_all_users()
        roster_text = "Network Users:\n\n"
        for user in users:
            display = user.get('display_name', user['computer_name'])
            roster_text += f"{display} (@{user['computer_name']}) ID:{user['id']}\n"
        self.roster_text.insert(1.0, roster_text)
        
        # Trigger periodic update
        self.root.after(10000, self.update_roster_ui)
    
    def setup_ui(self):
        # Header
        header_frame = tk.Frame(self.root, bg=self.bg_dark, height=80)
        header_frame.pack(fill="x", padx=20, pady=10)
        header_frame.pack_propagate(False)
        
        # Logo/Title
        title_label = tk.Label(
            header_frame, 
            text="Warden", 
            font=("Segoe UI", 24, "bold"),
            bg=self.bg_dark, 
            fg=self.accent
        )
        title_label.pack(side="left", pady=10)
        
        # User/Status
        status_frame = tk.Frame(header_frame, bg=self.bg_dark)
        status_frame.pack(side="right", pady=10)
        
        self.ws_status = tk.Label(status_frame, text="WS: OFFLINE", fg="#ff6b6b", font=("Segoe UI", 10))
        self.ws_status.pack(side="right", padx=10)
        
        self.status_label = tk.Label(
            status_frame,
            text="STOPPED",
            font=("Segoe UI", 12),
            bg=self.bg_dark,
            fg="#ff6b6b",
            padx=15,
            pady=5
        )
        self.status_label.pack(side="right")
        
        # Info Bar
        info_frame = tk.Frame(self.root, bg=self.bg_card, padx=20, pady=15)
        info_frame.pack(fill="x", padx=20, pady=(0, 10))
        
        self.name_btn = tk.Button(
            info_frame,
            text=f"Name: {self.display_name}",
            font=("Segoe UI", 11, "bold"),
            bg=self.bg_card,
            fg=self.accent,
            cursor="hand2",
            command=self.update_name,
            padx=10
        )
        self.name_btn.pack(side="left", padx=(0,10))
        
        self.local_ip_label = tk.Label(
            info_frame,
            text=f"Local: {self.local_ip} | Subnet: {self.subnet_prefix} | ID:{self.user_id}",
            font=("Segoe UI", 11),
            bg=self.bg_card,
            fg=self.text_white
        )
        self.local_ip_label.pack(side="left")
        
        self.ports_label = tk.Label(
            info_frame,
            text="Ports: 14235/12207 | WS:8765",
            font=("Segoe UI", 11),
            bg=self.bg_card,
            fg=self.text_gray
        )
        self.ports_label.pack(side="right")
        
        # Notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Miners tab
        miners_frame = tk.Frame(self.notebook, bg=self.bg_dark)
        self.notebook.add(miners_frame, text="Miners")
        
        list_container = tk.Frame(miners_frame, bg=self.bg_dark, padx=20, pady=10)
        list_container.pack(fill="both", expand=True)
        
        scrollbar = tk.Scrollbar(list_container)
        scrollbar.pack(side="right", fill="y")
        
        self.miner_list = tk.Canvas(list_container, bg=self.bg_dark, highlightthickness=0, yscrollcommand=scrollbar.set)
        self.miner_list.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.miner_list.yview)
        
        self.miner_list_frame = tk.Frame(self.miner_list, bg=self.bg_dark)
        self.miner_list.create_window((0, 0), window=self.miner_list_frame, anchor="nw")
        self.miner_list_frame.bind("<Configure>", lambda e: self.miner_list.configure(scrollregion=self.miner_list.bbox("all")))
        
        # Roster tab
        roster_frame = tk.Frame(self.notebook, bg=self.bg_dark)
        self.notebook.add(roster_frame, text="Network Roster")
        
        self.roster_text = scrolledtext.ScrolledText(roster_frame, bg=self.bg_card, fg=self.text_white, font=("Consolas", 10))
        self.roster_text.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Buttons Frame
        btn_frame = tk.Frame(self.root, bg=self.bg_dark, padx=20, pady=10)
        btn_frame.pack(fill="x")
        
        self.start_btn = tk.Button(
            btn_frame,
            text="START REPORTING",
            font=("Segoe UI", 12, "bold"),
            bg=self.accent,
            fg=self.text_white,
            activebackground="#ff6b9d",
            padx=25,
            pady=10,
            borderwidth=0,
            cursor="hand2",
            command=self.start_listening
        )
        self.start_btn.pack(side="left", padx=5)
        
        self.stop_btn = tk.Button(
            btn_frame,
            text="STOP REPORTING",
            font=("Segoe UI", 12, "bold"),
            bg="#4a4a6a",
            fg=self.text_white,
            activebackground="#6a6a8a",
            padx=25,
            pady=10,
            borderwidth=0,
            cursor="hand2",
            command=self.stop_listening,
            state="disabled"
        )
        self.stop_btn.pack(side="left", padx=5)
        
        self.stats_label = tk.Label(
            btn_frame,
            text="Miners: 0 | Unvisited: 0 | Peers: 0",
            font=("Segoe UI", 11),
            bg=self.bg_dark,
            fg=self.text_gray,
            padx=20
        )
        self.stats_label.pack(side="right", padx=10)
    
    def update_ws_status(self):
        """Update WS status label."""
        if self.ws_connected:
            self.ws_status.config(text="WS: ONLINE", fg="#4ecca3")
        else:
            self.ws_status.config(text="WS: OFFLINE", fg="#ff6b6b")
    
    def update_name(self):
        """Update display name."""
        new_name = tk.simpledialog.askstring("Update Name", "Enter new display name:", initialvalue=self.display_name)
        if new_name and new_name.strip():
            new_name = new_name.strip()
            self.user = get_or_create_user(display_name=new_name)
            self.display_name = new_name
            self.name_btn.config(text=f"Name: {self.display_name}")
            self.local_ip_label.config(text=f"Local: {self.local_ip} | Subnet: {self.subnet_prefix} | ID:{self.user_id}")
            print(f"Name updated to: {self.display_name}")

    def delete_miner_entry(self, mac, miner_id):
        if messagebox.askyesno("Delete Miner", f"Are you sure you want to delete the miner with MAC: {mac} and all its associated reports?"):
            delete_miner(miner_id) 
            self.miner_entries[mac]['frame'].destroy()
            del self.miner_entries[mac]
            self.update_stats()
            messagebox.showinfo("Deleted", f"Miner {mac} and its reports have been deleted.")
    
    def update_miner_stats(self, mac, total_hashrate, avg_hashrate):
        """Update hashrate statistics for a given miner card."""
        if mac in self.miner_entries:
            entry = self.miner_entries[mac]
            stats_text = f"Total: {total_hashrate:.2f} TH/s | Avg: {avg_hashrate:.2f} TH/s"
            entry['stats_label'].config(text=stats_text)



    
    def update_local_ip(self):
        """Update local IP display."""
        local_ips = get_local_ips()
        local_ip = get_preferred_local_ip()
        self.local_ip_label.config(text=f"Local: {local_ip} | Subnet: {self.subnet_prefix} | ID:{self.user_id}")
        if len(local_ips) > 1:
            self.local_ip_label.config(text=f"Local: {local_ip} ({len(local_ips)} ifaces) | Subnet: {self.subnet_prefix} | ID:{self.user_id}")
    
    def start_listening(self):
        """Start UDP listening."""
        self.listening = True
        self.start_btn.config(state="disabled", bg="#4a4a6a")
        self.stop_btn.config(state="normal", bg=self.accent)
        self.status_label.config(text="LISTENING", fg="#4ecca3")
        
        self.listener_thread = threading.Thread(target=self.listen_for_miners, daemon=True)
        self.listener_thread.start()
    
    def stop_listening(self):
        """Stop UDP listening."""
        self.listening = False
        self.start_btn.config(state="normal", bg=self.accent)
        self.stop_btn.config(state="disabled", bg="#4a4a6a")
        self.status_label.config(text="STOPPED", fg="#ff6b6b")
    
    def listen_for_miners(self):
        """UDP listener for miner broadcasts."""
        port = 14235
        local_ips = get_local_ips()
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
        
        try:
            sock.bind(('0.0.0.0', port))
        except:
            try:
                sock.bind(('0.0.0.0', 12207))
                port = 12207
            except:
                pass
        
        sock2 = None
        try:
            sock2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock2.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            other_port = 12207 if port == 14235 else 14235
            sock2.bind(('0.0.0.0', other_port))
        except:
            pass
        
        while self.listening:
            try:
                sock.settimeout(1.0)
                data, addr = sock.recvfrom(1024)
                if len(data) >= 11:
                    _, mac_raw, ip_raw = struct.unpack('>B6s4s', data[:11])
                    mac = ':'.join(f'{b:02x}' for b in mac_raw)
                    ip = socket.inet_ntoa(ip_raw)
                    
                    if not is_valid_local_ip(ip):
                        ip = addr[0]
                    
                    self.root.after(0, lambda m=mac, i=ip: self.add_miner_entry(i, m, addr[0], datetime.now().strftime("%H:%M:%S")))
            except socket.timeout:
                pass
            except Exception as e:
                print(f"Listen error: {e}")
        
        sock.close()
        if sock2:
            sock2.close()
    
    def process_queue(self):
        """Process UDP packets."""
        self.root.after(100, self.process_queue)
    
    def add_miner_entry(self, ip, mac, origin, time_str):
        """Add miner to UI, check collision, report to DB/WS."""
        # Collision check
        collisions = get_collisions(mac, self.user_id)
        if collisions:
            alert = f"Collision! {len(collisions)} other users reported {mac}:"
            for c in collisions[:3]:
                alert += f"\n  - {c['computer_name']} ({c['reported_ip']})"
            messagebox.showwarning("Miner Collision Detected", alert)
            # Broadcast collision
            insert_broadcast("collision_alert", self.user_id, {"mac": mac, "alert": alert})
        
        # Report to DB
        report_miner(mac, ip, self.user_id)
        
        # Broadcast IP assigned
        insert_broadcast("ip_assigned", self.user_id, {
            "computer_name": self.hostname,
            "mac": mac,
            "ip": ip
        })
        
        # Create UI card
        if mac not in self.miner_entries:
            self.create_miner_card(mac, ip, time_str)
        
        self.update_stats()
    
    def create_miner_card(self, mac, ip, time_str):
        """Create miner card in UI."""
        card = tk.Frame(self.miner_list_frame, bg=self.bg_card, padx=15, pady=12)
        card.pack(fill="x", pady=5)
        
        info_frame = tk.Frame(card, bg=self.bg_card)
        info_frame.pack(side="left", fill="x", expand=True)
        
# Get reporter info
        from database import get_connection, get_miner_reporters
        # Need miner_id - query miners table by mac
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM miners WHERE mac_address = ?', (mac,))
        miner_row = cursor.fetchone()
        conn.close()
        if miner_row:
            miner_id = miner_row['id']
            reporters = get_miner_reporters(miner_id)
            reporter_info = reporters[0] if reporters else None
            if reporter_info:
                reporter_name = reporter_info['display_name']
                user_computer = reporter_info.get('computer_name', 'Unknown')
            else:
                reporter_name = 'Unknown'
                user_computer = 'Unknown'
            if len(reporters) > 1:
                reporter_name = 'Multi'
                user_computer = 'Multi'
        else:
            reporter_name = 'Unknown'
        
        ip_label = tk.Label(
            info_frame,
            text=f"[{reporter_name} ({user_computer})] {ip}",
            font=("Segoe UI", 14, "bold"),
            bg=self.bg_card,
            fg="#00d9ff",
            cursor="hand2"
        )
        ip_label.pack(anchor="w")
        ip_label.bind("<Button-1>", lambda e: self.open_browser(ip, mac))
        
        mac_label = tk.Label(
            info_frame,
            text=f"MAC: {mac}",
            font=("Segoe UI", 10),
            bg=self.bg_card,
            fg=self.text_gray
        )
        mac_label.pack(anchor="w")
        
        time_label = tk.Label(
            info_frame,
            text=f"Time: {time_str}",
            font=("Segoe UI", 10),
            bg=self.bg_card,
            fg=self.text_gray
        )
        time_label.pack(anchor="w")
        
        status_frame = tk.Frame(card, bg=self.bg_card)
        status_frame.pack(side="right", padx=10)
        
        visit_btn = tk.Button(
            status_frame,
            text="VISIT",
            font=("Segoe UI", 10, "bold"),
            bg="#2d4a6a",
            fg=self.text_white,
            activebackground="#3d5a7a",
            padx=15,
            pady=5,
            borderwidth=0,
            cursor="hand2",
            command=lambda: self.open_browser(ip, mac)
        )
        visit_btn.pack()

        delete_btn = tk.Button(
            status_frame,
            text="DELETE",
            font=("Segoe UI", 10, "bold"),
            bg="#cc3300", 
            fg=self.text_white,
            activebackground="#ff5533",
            padx=15,
            pady=5,
            borderwidth=0,
            cursor="hand2",
            command=lambda: self.delete_miner_entry(mac, miner_id)
        )
        delete_btn.pack(pady=(5,0))
        
        self.miner_entries[mac] = {
            'ip': ip,
            'mac': mac,
            'reporter_name': reporter_name,
            'visited': False,
            'frame': card,
            'ip_label': ip_label,
            'time_label': time_label,
            'visit_btn': visit_btn,
            'delete_btn': delete_btn, 
            'miner_id': miner_id
        }
    
    def open_browser(self, ip, mac):
        """Open miner IP, mark visited, broadcast."""
        if mac in self.miner_entries:
            entry = self.miner_entries[mac]
            reporter_name = entry.get('reporter_name', 'Unknown')
            entry['visited'] = True
            entry['ip_label'].config(fg=self.visited_color)
            entry['visit_btn'].config(text="VISITED", bg=self.visited_color)
            
            # Mark in DB
            # Get actual miner_id
            from database import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM miners WHERE mac_address = ?', (mac,))
            miner_row = cursor.fetchone()
            conn.close()
            if miner_row:
                mark_visited(miner_row['id'], self.user_id)
            
            print(f"Visiting {reporter_name}'s miner {mac} at {ip}")
            
            # Broadcast url available
            insert_broadcast("url_available", self.user_id, {
                "display_name": self.display_name,
                "mac": mac,
                "ip": ip
            })
            
            webbrowser.open(f"http://{ip}")
        
        self.update_stats()
    
    def update_stats(self):
        """Update stats label."""
        total = len(self.miner_entries)
        unvisited = len([e for e in self.miner_entries.values() if not e['visited']])
        peers = len(self.roster_data.get('peers', [])) if self.roster_data else 0
        
        self.stats_label.config(text=f"Miners: {total} | Unvisited: {unvisited} | Peers: {peers}")


def main():
    root = tk.Tk()
    
    # Set window icon
    try:
        root.iconbitmap("miner.ico")
    except:
        pass
    
    app = MinerIPReporterGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
