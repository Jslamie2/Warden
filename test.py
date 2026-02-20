import asyncio
import websockets
import json

async def test_connection():
    uri = "ws://localhost:8765"
    peer_id = "test_user_689"
    target_room = "war_room_7" # The room we want to join

    try:
        async with websockets.connect(uri) as websocket:

            # 1. Register
            print(f"--- Registering as {peer_id} ---")
            registration_msg = {
                "action": "register",
                "peer_id": peer_id,
                "metadata": {"version": "1.0", "name": "Tester"}
            }
            await websocket.send(json.dumps(registration_msg))

            response = await websocket.recv()
            data = json.loads(response)

            # Check for Handover/Busy logic (from previous steps)
            if data.get("type") == "busy_notice":
                print("⚠️ ID Busy. Sending resume...")
                await websocket.send(json.dumps({"action": "resume"}))
                data = json.loads(await websocket.recv())

            if data.get("type") == "registered":
                print("✅ Registered!")

            # 2. JOIN ROOM (New Method)
            print(f"\n--- Joining Room: {target_room} ---")
            join_msg = {
                "action": "join_room",
                "room_id": target_room
            }
            await websocket.send(json.dumps(join_msg))

            # Server sends back type: "room_joined"
            room_conf = await websocket.recv()
            print(f"Room Response: {room_conf}")

            # 3. Request peer list
            # Now the server will look at self.rooms[target_room]
            print("\n--- Requesting Peer List ---")
            await websocket.send(json.dumps({"action": "list_peers"}))

            peers_data = await websocket.recv()
            peers_json = json.loads(peers_data)

            print(f"Available Peers in {target_room}: {json.dumps(peers_json.get('peers'), indent=2)}")

            # 4. Stay alive to be seen by others
            print("\nStaying connected for 150s so other clients can see ME in the list...")
            await asyncio.sleep(200)

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
