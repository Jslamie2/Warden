import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import socket
import struct
import time
import ipaddress
import webbrowser
from datetime import datetime
import queue
import sys

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
        self.root.title("Warden - IP Reporter")
        self.root.geometry("900x700")
        self.root.configure(bg="#1a1a2e")
        
        # Data structures
        self.miner_entries = {}  # MAC -> {ip, time, visited, widget}
        self.listening = False
        self.listener_thread = None
        self.packet_queue = queue.Queue()
        
        # Colors
        self.bg_dark = "#16213e"
        self.bg_card = "#0f3460"
        self.accent = "#e94560"
        self.text_white = "#ffffff"
        self.text_gray = "#a0a0a0"
        self.visited_color = "#4ecca3"
        
        self.setup_ui()
        self.process_queue()
    
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
        
        # Status indicator
        self.status_label = tk.Label(
            header_frame,
            text="STOPPED",
            font=("Segoe UI", 12),
            bg=self.bg_dark,
            fg="#ff6b6b",
            padx=15,
            pady=5
        )
        self.status_label.pack(side="right", pady=10)
        
        # Info Bar
        info_frame = tk.Frame(self.root, bg=self.bg_card, padx=20, pady=15)
        info_frame.pack(fill="x", padx=20, pady=(0, 10))
        
        self.local_ip_label = tk.Label(
            info_frame,
            text="Local IP: Detecting...",
            font=("Segoe UI", 11),
            bg=self.bg_card,
            fg=self.text_white
        )
        self.local_ip_label.pack(side="left")
        
        self.ports_label = tk.Label(
            info_frame,
            text="Ports: 14235, 12207",
            font=("Segoe UI", 11),
            bg=self.bg_card,
            fg=self.text_gray
        )
        self.ports_label.pack(side="right")
        
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
            activeforeground=self.text_white,
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
            activeforeground=self.text_white,
            padx=25,
            pady=10,
            borderwidth=0,
            cursor="hand2",
            command=self.stop_listening,
            state="disabled"
        )
        self.stop_btn.pack(side="left", padx=5)
        
        # Stats
        self.stats_label = tk.Label(
            btn_frame,
            text="Miners Found: 0 | Unvisited: 0",
            font=("Segoe UI", 11),
            bg=self.bg_dark,
            fg=self.text_gray,
            padx=20
        )
        self.stats_label.pack(side="right", padx=10)
        
        # Miner List (scrollable frame)
        list_container = tk.Frame(self.root, bg=self.bg_dark, padx=20, pady=10)
        list_container.pack(fill="both", expand=True)
        
        # Scrollbar
        scrollbar = tk.Scrollbar(list_container)
        scrollbar.pack(side="right", fill="y")
        
        self.miner_list = tk.Canvas(
            list_container,
            bg=self.bg_dark,
            highlightthickness=0,
            yscrollcommand=scrollbar.set
        )
        self.miner_list.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.miner_list.yview)
        
        self.miner_list_frame = tk.Frame(self.miner_list, bg=self.bg_dark)
        self.miner_list.create_window((0, 0), window=self.miner_list_frame, anchor="nw")
        
        self.miner_list_frame.bind("<Configure>", lambda e: self.miner_list.configure(scrollregion=self.miner_list.bbox("all")))
        
        # Footer
        footer = tk.Label(
            self.root,
            text="Waiting for miners to press IP Report button...",
            font=("Segoe UI", 10),
            bg=self.bg_dark,
            fg=self.text_gray,
            pady=10
        )
        footer.pack(fill="x")
        
        # Update local IP display
        self.update_local_ip()
    
    def update_local_ip(self):
        local_ips = get_local_ips()
        local_ip = get_preferred_local_ip()
        self.local_ip_label.config(text="Local IP: " + local_ip)
        if len(local_ips) > 1:
            self.local_ip_label.config(text="Local IP: " + local_ip + " (" + str(len(local_ips)) + " interfaces)")
    
    def start_listening(self):
        self.listening = True
        self.start_btn.config(bg="#4a4a6a", state="disabled")
        self.stop_btn.config(bg=self.accent, state="normal")
        self.status_label.config(text="LISTENING", fg="#4ecca3")
        
        self.listener_thread = threading.Thread(target=self.listen_for_miners, daemon=True)
        self.listener_thread.start()
    
    def stop_listening(self):
        self.listening = False
        self.start_btn.config(bg=self.accent, state="normal")
        self.stop_btn.config(bg="#4a4a6a", state="disabled")
        self.status_label.config(text="STOPPED", fg="#ff6b6b")
    
    def listen_for_miners(self):
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
        
        # Also listen on secondary port
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
                try:
                    data, addr = sock.recvfrom(1024)
                    if len(data) >= 11:
                        try:
                            _, mac_raw, ip_raw = struct.unpack('>B6s4s', data[:11])
                            mac_str = ':'.join(f'{b:02x}' for b in mac_raw)
                            ip_str = socket.inet_ntoa(ip_raw)
                            
                            if not ip_str or ip_str.startswith('0.') or ip_str.startswith('127.') or ip_str.startswith('255.'):
                                ip_str = addr[0]
                            
                            if not is_valid_local_ip(ip_str):
                                if len(data) >= 18:
                                    try:
                                        _, mac_raw, _, ip_raw = struct.unpack('>B6sB4s', data[:12])
                                        ip_str = socket.inet_ntoa(ip_raw)
                                    except: pass
                            
                            if not is_valid_local_ip(ip_str):
                                ip_str = addr[0]
                            
                            # Add to queue for GUI update
                            self.packet_queue.put({
                                'ip': ip_str,
                                'mac': mac_str,
                                'origin': addr[0],
                                'time': datetime.now().strftime("%H:%M:%S")
                            })
                        except Exception as e:
                            print(f"Parse error: {e}")
                except socket.timeout:
                    pass
            except Exception as e:
                if self.listening:
                    print(f"Listen error: {e}")
        
        sock.close()
        if sock2:
            sock2.close()
    
    def process_queue(self):
        try:
            while True:
                data = self.packet_queue.get_nowait()
                self.add_miner_entry(data['ip'], data['mac'], data['origin'], data['time'])
        except queue.Empty:
            pass
        
        self.root.after(100, self.process_queue)
    
    def add_miner_entry(self, ip, mac, origin, time_str):
        # Check if MAC already exists
        if mac in self.miner_entries:
            # Update existing entry
            entry = self.miner_entries[mac]
            entry['ip'] = ip
            entry['time'] = time_str
            entry['time_label'].config(text="Time: " + time_str)
            entry['ip_label'].config(text="IP: " + ip)
            # Move to top
            entry['frame'].lift()
        else:
            # Create new entry
            self.create_miner_card(mac, ip, time_str)
        
        self.update_stats()
    
    def create_miner_card(self, mac, ip, time_str):
        card = tk.Frame(self.miner_list_frame, bg=self.bg_card, padx=15, pady=12)
        card.pack(fill="x", pady=5)
        
        # Left side - Info
        info_frame = tk.Frame(card, bg=self.bg_card)
        info_frame.pack(side="left", fill="x", expand=True)
        
        # IP (clickable)
        ip_label = tk.Label(
            info_frame,
            text="IP: " + ip,
            font=("Segoe UI", 14, "bold"),
            bg=self.bg_card,
            fg="#00d9ff",
            cursor="hand2"
        )
        ip_label.pack(anchor="w")
        ip_label.bind("<Button-1>", lambda e: self.open_browser(ip, mac))
        
        # MAC
        mac_label = tk.Label(
            info_frame,
            text="MAC: " + mac,
            font=("Segoe UI", 10),
            bg=self.bg_card,
            fg=self.text_gray
        )
        mac_label.pack(anchor="w")
        
        # Time
        time_label = tk.Label(
            info_frame,
            text="Time: " + time_str,
            font=("Segoe UI", 10),
            bg=self.bg_card,
            fg=self.text_gray
        )
        time_label.pack(anchor="w")
        
        # Right side - Visit button / Status
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
        
        # Store entry data
        self.miner_entries[mac] = {
            'ip': ip,
            'mac': mac,
            'visited': False,
            'frame': card,
            'ip_label': ip_label,
            'time_label': time_label,
            'visit_btn': visit_btn
        }
    
    def open_browser(self, ip, mac):
        if mac in self.miner_entries:
            entry = self.miner_entries[mac]
            entry['visited'] = True
            
            # Update UI to show visited
            entry['ip_label'].config(fg=self.visited_color)
            entry['visit_btn'].config(text="VISITED", bg=self.visited_color)
            
            # Open browser
            url = "http://" + ip
            webbrowser.open(url)
            
            self.update_stats()
    
    def update_stats(self):
        total = len(self.miner_entries)
        unvisited = sum(1 for e in self.miner_entries.values() if not e['visited'])
        
        # Update footer message
        if unvisited > 0:
            msg = str(unvisited) + " miner(s) not visited - Click the IP to open browser or click VISIT"
        else:
            msg = "All miners have been visited"
        
        # Find and update footer (last widget)
        for widget in self.root.winfo_children():
            if isinstance(widget, tk.Label):
                try:
                    text = widget.cget("text")
                    if text.startswith("Waiting") or "not visited" in text or "visited" in text:
                        widget.config(text=msg)
                        break
                except:
                    pass
        
        self.stats_label.config(text="Miners Found: " + str(total) + " | Unvisited: " + str(unvisited))


def main():
    root = tk.Tk()
    
    # Set window icon (if available)
    try:
        root.iconbitmap("miner.ico")
    except:
        pass
    
    app = MinerIPReporterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

