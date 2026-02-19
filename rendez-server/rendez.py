# rendezvous_server.py
import asyncio
import websockets
import json
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
import secrets

@dataclass
class Peer:
    peer_id: str
    websocket: websockets.WebSocketServerProtocol
    public_ip: str
    public_port: int
    metadata: dict = field(default_factory=dict)
    last_seen: float = field(default_factory=time.time)
    room: Optional[str] = None

class RendezvousServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.peers: Dict[str, Peer] = {}
        self.rooms: Dict[str, Set[str]] = {}  # room_id -> set of peer_ids
        
    async def start(self):
        print(f"Rendezvous server starting on ws://{self.host}:{self.port}")
        async with websockets.serve(self.handle_connection, self.host, self.port):
            await asyncio.Future()  # Run forever
    
    async def handle_connection(self, websocket: websockets.WebSocketServerProtocol, path: str):
        peer_id = None
        try:
            # First message must be registration
            message = await websocket.recv()
            data = json.loads(message)
            
            if data.get("action") != "register":
                await self.send_error(websocket, "First message must be register")
                return
            
            # Register peer
            peer_id = data.get("peer_id") or self.generate_peer_id()
            peer = Peer(
                peer_id=peer_id,
                websocket=websocket,
                public_ip=websocket.remote_address[0],
                public_port=websocket.remote_address[1],
                metadata=data.get("metadata", {})
            )
            
            self.peers[peer_id] = peer
            print(f"Peer registered: {peer_id} from {peer.public_ip}")
            
            await self.send(websocket, {
                "type": "registered",
                "peer_id": peer_id,
                "your_ip": peer.public_ip,
                "your_port": peer.public_port
            })
            
            # Handle subsequent messages
            async for message in websocket:
                await self.handle_message(peer_id, message)
                
        except websockets.exceptions.ConnectionClosed:
            print(f"Peer disconnected: {peer_id}")
        except Exception as e:
            print(f"Error with peer {peer_id}: {e}")
        finally:
            if peer_id and peer_id in self.peers:
                await self.cleanup_peer(peer_id)
    
    async def handle_message(self, peer_id: str, message: str):
        """Route message to appropriate handler"""
        try:
            data = json.loads(message)
            action = data.get("action")
            
            handlers = {
                "list_peers": self.handle_list_peers,
                "signal": self.handle_signal,
                "join_room": self.handle_join_room,
                "broadcast": self.handle_broadcast,
                "heartbeat": self.handle_heartbeat,
            }
            
            handler = handlers.get(action)
            if handler:
                await handler(peer_id, data)
            else:
                await self.send_error(self.peers[peer_id].websocket, f"Unknown action: {action}")
                
        except json.JSONDecodeError:
            await self.send_error(self.peers[peer_id].websocket, "Invalid JSON")
    
    # ============ HANDLERS ============
    
    async def handle_list_peers(self, peer_id: str, data: dict):
        """List all available peers (for discovery)"""
        peer = self.peers[peer_id]
        
        # Return peers in same room, or all peers if no room
        room_id = peer.room
        if room_id and room_id in self.rooms:
            peer_ids = self.rooms[room_id]
        else:
            peer_ids = self.peers.keys()
        
        peers_info = []
        for pid in peer_ids:
            if pid == peer_id:
                continue  # Don't include self
            p = self.peers[pid]
            peers_info.append({
                "peer_id": pid,
                "public_ip": p.public_ip,
                "public_port": p.public_port,
                "metadata": p.metadata,
                "room": p.room
            })
        
        await self.send(peer.websocket, {
            "type": "peer_list",
            "peers": peers_info,
            "count": len(peers_info)
        })
    
    async def handle_signal(self, peer_id: str, data: dict):
        """Relay WebRTC signaling or connection info to target peer"""
        target_id = data.get("target_id")
        signal_data = data.get("data")
        
        if target_id not in self.peers:
            await self.send_error(self.peers[peer_id].websocket, f"Target {target_id} not found")
            return
        
        target = self.peers[target_id]
        
        # Relay signal
        await self.send(target.websocket, {
            "type": "signal",
            "from": peer_id,
            "data": signal_data
        })
        
        print(f"📡 Signal relayed: {peer_id} -> {target_id}")
    
    async def handle_join_room(self, peer_id: str, data: dict):
        """Join a room for group communication"""
        room_id = data.get("room_id")
        peer = self.peers[peer_id]
        
        # Leave previous room
        if peer.room and peer.room in self.rooms:
            self.rooms[peer.room].discard(peer_id)
        
        # Join new room
        peer.room = room_id
        if room_id not in self.rooms:
            self.rooms[room_id] = set()
        self.rooms[room_id].add(peer_id)
        
        await self.send(peer.websocket, {
            "type": "room_joined",
            "room_id": room_id,
            "peers_in_room": len(self.rooms[room_id])
        })
        
        # Notify others
        await self.broadcast_to_room(room_id, {
            "type": "peer_joined",
            "peer_id": peer_id
        }, exclude=peer_id)
    
    async def handle_broadcast(self, peer_id: str, data: dict):
        """Broadcast message to room or all peers"""
        message = data.get("message")
        peer = self.peers[peer_id]
        
        if peer.room:
            await self.broadcast_to_room(peer.room, {
                "type": "broadcast",
                "from": peer_id,
                "message": message
            }, exclude=peer_id)
        else:
            # Broadcast to all
            for pid, p in self.peers.items():
                if pid != peer_id:
                    await self.send(p.websocket, {
                        "type": "broadcast",
                        "from": peer_id,
                        "message": message
                    })
    
    async def handle_heartbeat(self, peer_id: str, data: dict):
        """Keep connection alive"""
        self.peers[peer_id].last_seen = time.time()
        await self.send(self.peers[peer_id].websocket, {"type": "pong"})
    
    # ============ UTILITIES ============
    
    async def broadcast_to_room(self, room_id: str, message: dict, exclude: Optional[str] = None):
        """Send message to all peers in room"""
        if room_id not in self.rooms:
            return
        
        for peer_id in self.rooms[room_id]:
            if peer_id == exclude:
                continue
            if peer_id in self.peers:
                await self.send(self.peers[peer_id].websocket, message)
    
    async def cleanup_peer(self, peer_id: str):
        """Remove peer and notify others"""
        peer = self.peers.pop(peer_id, None)
        if not peer:
            return
        
        # Remove from room
        if peer.room and peer.room in self.rooms:
            self.rooms[peer.room].discard(peer_id)
            # Notify room
            await self.broadcast_to_room(peer.room, {
                "type": "peer_left",
                "peer_id": peer_id
            })
        
        print(f"🧹 Cleaned up peer: {peer_id}")
    
    async def send(self, websocket, data: dict):
        """Send JSON to websocket"""
        try:
            await websocket.send(json.dumps(data))
        except:
            pass
    
    async def send_error(self, websocket, message: str):
        """Send error message"""
        await self.send(websocket, {"type": "error", "message": message})
    
    def generate_peer_id(self) -> str:
        """Generate unique peer ID"""
        return secrets.token_urlsafe(8)
    
    async def cleanup_loop(self):
        """Periodic cleanup of stale peers"""
        while True:
            await asyncio.sleep(30)
            now = time.time()
            stale = [
                pid for pid, p in self.peers.items()
                if now - p.last_seen > 120  # 2 minutes timeout
            ]
            for pid in stale:
                print(f"⏰ Peer timeout: {pid}")
                await self.cleanup_peer(pid)


# ============ RUN SERVER ============

if __name__ == "__main__":
    server = RendezvousServer(host="0.0.0.0", port=8765)
    asyncio.create_task(server.cleanup_loop())
    asyncio.run(server.start())