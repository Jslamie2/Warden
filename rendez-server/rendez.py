import asyncio
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

import websockets


@dataclass
class Peer:
    peer_id: str
    websocket: any
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
        self.rooms: Dict[str, Set[str]] = {}

    async def start(self):
        print(f"Rendezvous server starting on ws://{self.host}:{self.port}")
        asyncio.create_task(self.cleanup_loop())
        async with websockets.serve(self.handle_connection, self.host, self.port):
            await asyncio.Future()

    async def handle_connection(self, websocket):
        peer_id = None
        try:
            # 1. Registration Phase
            message = await websocket.recv()
            data = json.loads(message)
            if data.get("action") != "register":
                await self.send_error(websocket, "First message must be register")
                return

            peer_id = data.get("peer_id") or self.generate_peer_id()
            remote_ip, remote_port = websocket.remote_address[:2]

            # --- HANDOVER LOGIC ---
            if peer_id in self.peers:
                old_peer = self.peers[peer_id]
                await self.send(
                    websocket,
                    {
                        "type": "busy_notice",
                        "message": "This ID is already active. Resume here to switch devices?",
                    },
                )

                try:
                    confirm_msg = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                    confirm_data = json.loads(confirm_msg)
                    if confirm_data.get("action") == "resume":
                        print(f"Handover: Kicking old {peer_id}")
                        await self.send(
                            old_peer.websocket,
                            {
                                "type": "suspended",
                                "message": "Session moved to another device.",
                            },
                        )
                        await old_peer.websocket.close()
                    else:
                        await self.send_error(websocket, "Handover cancelled.")
                        return
                except asyncio.TimeoutError:
                    await self.send_error(websocket, "Handover timed out.")
                    return

            # --- FINALIZE REGISTRATION ---
            peer = Peer(
                peer_id=peer_id,
                websocket=websocket,
                public_ip=remote_ip,
                public_port=remote_port,
                metadata=data.get("metadata", {}),
            )
            self.peers[peer_id] = peer
            print(f"Peer registered: {peer_id} from {remote_ip}")

            await self.send(
                websocket,
                {
                    "type": "registered",
                    "peer_id": peer_id,
                    "your_ip": remote_ip,
                    "your_port": remote_port,
                },
            )

            # 2. Main Message Loop
            async for message in websocket:
                await self.handle_message(peer_id, message)

        except websockets.exceptions.ConnectionClosed:
            print(f"🔌 Connection closed: {peer_id}")
        except Exception as e:
            print(f"❌ Error with peer {peer_id}: {e}")
        finally:
            # Safety check: ensure we don't delete a NEW session's data
            if peer_id and peer_id in self.peers:
                if self.peers[peer_id].websocket == websocket:
                    await self.cleanup_peer(peer_id)

    async def handle_message(self, peer_id: str, message: str):
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
        except Exception as e:
            print(f"Error handling message from {peer_id}: {e}")

    # ============ HANDLERS ============
    async def handle_list_peers(self, peer_id: str, data: dict):
        peer = self.peers.get(peer_id)
        if not peer:
            return
        room_id = peer.room
        # LOGIC FIX: Determine who is in the "viewing range"
        if room_id and room_id in self.rooms:
            # Peer is in a room: target only people in that specific room
            target_ids = self.rooms[room_id]
        else:
            # Peer is not in a room: target everyone who is ALSO not in a room
            target_ids = [pid for pid, p in self.peers.items() if p.room is None]

        peers_info = [
            {"peer_id": pid, "metadata": p.metadata}
            for pid, p in self.peers.items()
            if pid in target_ids and pid != peer_id
        ]

        print(
            f"{peer_id} requested list. Found {len(peers_info)} others in room '{room_id}'"
        )
        await self.send(
            peer.websocket, {"type": "peer_list", "peers": peers_info, "room": room_id}
        )

    async def handle_join_room(self, peer_id: str, data: dict):
        room_id = data.get("room_id")
        peer = self.peers.get(peer_id)
        if not peer:
            return
        # 1. Cleanup old room registry
        if peer.room and peer.room in self.rooms:
            self.rooms[peer.room].discard(peer_id)
            if not self.rooms[peer.room]:
                del self.rooms[peer.room]
        # 2. Update peer state and new room registry
        peer.room = room_id
        if room_id:
            if room_id not in self.rooms:
                self.rooms[room_id] = set()
            self.rooms[room_id].add(peer_id)
            print(f"{peer_id} joined room: {room_id}")

        await self.send(peer.websocket, {"type": "room_joined", "room_id": room_id})

    async def handle_signal(self, peer_id: str, data: dict):
        target_id = data.get("target_id")
        if target_id in self.peers:
            await self.send(
                self.peers[target_id].websocket,
                {"type": "signal", "from": peer_id, "data": data.get("data")},
            )

    async def handle_broadcast(self, peer_id: str, data: dict):
        peer = self.peers.get(peer_id)
        if not peer:
            return
        msg = {"type": "broadcast", "from": peer_id, "message": data.get("message")}

        if peer.room:
            await self.broadcast_to_room(peer.room, msg, exclude=peer_id)
        else:
            # Global broadcast to all roomless people
            for pid, p in self.peers.items():
                if pid != peer_id and p.room is None:
                    await self.send(p.websocket, msg)

    async def handle_heartbeat(self, peer_id: str, data: dict):
        if peer_id in self.peers:
            self.peers[peer_id].last_seen = time.time()
            await self.send(self.peers[peer_id].websocket, {"type": "pong"})

    # ============ UTILITIES ============

    async def broadcast_to_room(self, room_id: str, message: dict, exclude: str = None):
        if room_id in self.rooms:
            for pid in list(self.rooms[room_id]):  # use list() to avoid mutation errors
                if pid != exclude and pid in self.peers:
                    await self.send(self.peers[pid].websocket, message)

    async def cleanup_peer(self, peer_id: str):
        peer = self.peers.pop(peer_id, None)
        if peer and peer.room in self.rooms:
            self.rooms[peer.room].discard(peer_id)
            if not self.rooms[peer.room]:
                del self.rooms[peer.room]
        print(f"Cleaned up: {peer_id}")

    async def send(self, websocket, data: dict):
        try:
            await websocket.send(json.dumps(data))
        except:
            pass

    async def send_error(self, websocket, message: str):
        await self.send(websocket, {"type": "error", "message": message})

    def generate_peer_id(self) -> str:
        return secrets.token_urlsafe(8)

    async def cleanup_loop(self):
        while True:
            await asyncio.sleep(30)
            now = time.time()
            stale = [pid for pid, p in self.peers.items() if now - p.last_seen > 120]
            for pid in stale:
                await self.cleanup_peer(pid)


if __name__ == "__main__":
    server = RendezvousServer()
    asyncio.run(server.start())
