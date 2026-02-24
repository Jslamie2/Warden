import asyncio
import json

import websockets


async def listen_for_messages(websocket):
    """Background task to print any incoming messages from the server."""
    try:
        async for message in websocket:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "signal":
                sender = data.get("from")
                content = data.get("data")
                print(f"\n📩 [DIRECT MESSAGE] From {sender}: {content}")
            elif msg_type == "broadcast":
                sender = data.get("from")
                content = data.get("message")
                print(f"\n📢 [BROADCAST] From {sender}: {content}")
            elif msg_type == "pong":
                pass  # Heartbeat response
            else:
                print(f"\nℹ️ [SYSTEM]: {data}")
    except websockets.exceptions.ConnectionClosed:
        print("Connection closed by server.")


async def test_connection():
    uri = "ws://localhost:8765"
    peer_id = "test_user_9530"
    target_room = "war_room_7"
    try:
        async with websockets.connect(uri) as websocket:
            # 1. Registration
            print(f"--- Registering as {peer_id} ---")
            await websocket.send(
                json.dumps(
                    {
                        "action": "register",
                        "peer_id": peer_id,
                        "metadata": {"name": "PythonTester"},
                    }
                )
            )

            # Initial response handling
            resp = json.loads(await websocket.recv())
            if resp.get("type") == "busy_notice":
                await websocket.send(json.dumps({"action": "resume"}))
                resp = json.loads(await websocket.recv())

            print(f"✅ Connected as {resp.get('peer_id')}")

            # Start background listener
            listener_task = asyncio.create_task(listen_for_messages(websocket))

            # 2. Join Room
            print(f"--- Joining Room: {target_room} ---")
            await websocket.send(
                json.dumps({"action": "join_room", "room_id": target_room})
            )

            # 3. Request peer list to find someone to talk to
            print("--- Requesting Peer List ---")
            await websocket.send(json.dumps({"action": "list_peers"}))

            # Small sleep to let the listener catch and print the list
            await asyncio.sleep(1)

            # 4. SEND A DIRECT MESSAGE (Signaling)
            # Change 'TARGET_ID' to an actual ID from your peer list output
            target_peer = "test_user_9430"
            print(f"--- Sending Signal to {target_peer} ---")

            signal_msg = {
                "action": "signal",
                "target_id": target_peer,
                "data": "Hello! This is a private message via the rendezvous server.",
            }
            await websocket.send(json.dumps(signal_msg))

            # 5. SEND A BROADCAST
            print("--- Sending Broadcast to Room ---")
            await websocket.send(
                json.dumps(
                    {"action": "broadcast", "message": "Hello everyone in the room!"}
                )
            )

            # Keep alive to receive messages
            print("\nListening for incoming signals (Press Ctrl+C to stop)...")
            await asyncio.gather(listener_task)

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_connection())
