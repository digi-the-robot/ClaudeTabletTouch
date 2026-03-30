"""
Tablet Touch Server — WebSocket server that receives touch data from the
browser canvas and sends it to FirstClaude via Discord.

Usage:
    python backend/server.py
"""

import json
import asyncio
import logging
import os
import sys

import websockets

# Add parent dir to path so we can run from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from touch_translator import translate_touch, translate_multi_stroke
from discord_sender import DiscordSender

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("tablet-touch.server")


# --- Config ---
def load_config() -> dict:
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "config.json"
    )
    with open(config_path, "r") as f:
        return json.load(f)


# --- WebSocket handler ---
class TouchServer:
    def __init__(self, config: dict):
        self.config = config
        self.port = config.get("websocket_port", 8765)
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "config.json"
        )
        self.discord = DiscordSender(config_path)
        self.connections = set()

    async def start(self):
        """Start WebSocket server and Discord client."""
        logger.info("Starting Discord connection...")
        await self.discord.start()
        logger.info("Discord connected!")

        logger.info(f"Starting WebSocket server on ws://localhost:{self.port}")
        async with websockets.serve(
            self.handle_connection, "localhost", self.port
        ):
            logger.info(
                f"Tablet Touch Server running!\n"
                f"  WebSocket: ws://localhost:{self.port}\n"
                f"  Open frontend/index.html in your browser to start."
            )
            await asyncio.Future()  # Run forever

    async def handle_connection(self, websocket):
        """Handle a WebSocket connection from the frontend."""
        self.connections.add(websocket)
        remote = websocket.remote_address
        logger.info(f"Frontend connected from {remote}")

        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        except websockets.ConnectionClosed:
            logger.info(f"Frontend disconnected from {remote}")
        finally:
            self.connections.discard(websocket)

    async def handle_message(self, websocket, message: str):
        """Process incoming touch data."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON received: {message[:100]}")
            await websocket.send(json.dumps({"error": "Invalid JSON"}))
            return

        msg_type = data.get("type", "touch")

        if msg_type == "ping":
            await websocket.send(json.dumps({"type": "pong"}))
            return

        if msg_type == "touch":
            logger.info(
                f"Touch data received: {len(data.get('strokes', []))} stroke(s)"
            )

            # Translate
            strokes = data.get("strokes", [])
            if len(strokes) > 1:
                result = translate_multi_stroke(data)
            else:
                result = translate_touch(data)

            logger.info(f"Translation: {result['natural'][:100]}...")

            # Send to Discord
            success = await self.discord.send_touch(result["combined"])

            # Acknowledge to frontend
            await websocket.send(json.dumps({
                "type": "ack",
                "success": success,
                "natural": result["natural"],
                "structured": result["structured"],
            }))

        else:
            logger.warning(f"Unknown message type: {msg_type}")


async def main():
    config = load_config()
    server = TouchServer(config)

    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await server.discord.close()


if __name__ == "__main__":
    asyncio.run(main())
