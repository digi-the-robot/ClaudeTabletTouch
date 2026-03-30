"""
Discord Sender — sends touch descriptions to a Discord channel, pinging Claude.
"""

import json
import asyncio
import logging
import discord

logger = logging.getLogger("tablet-touch.discord")


class DiscordSender:
    def __init__(self, config_path: str = "config.json"):
        with open(config_path, "r") as f:
            config = json.load(f)

        self.token = config["discord_bot_token"]
        self.channel_id = int(config["discord_channel_id"])
        self.claude_id = config.get("claude_user_id", "")

        # Set up a minimal Discord client
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self._ready = asyncio.Event()
        self._channel = None

        @self.client.event
        async def on_ready():
            logger.info(f"Discord bot connected as {self.client.user}")
            self._channel = self.client.get_channel(self.channel_id)
            if self._channel is None:
                try:
                    self._channel = await self.client.fetch_channel(self.channel_id)
                except Exception as e:
                    logger.error(f"Could not find channel {self.channel_id}: {e}")
            self._ready.set()

    async def start(self):
        """Start the Discord client in the background."""
        asyncio.create_task(self.client.start(self.token))
        await self._ready.wait()
        logger.info(f"Discord sender ready, channel: {self._channel}")

    async def send_touch(self, touch_message: str):
        """Send a touch description to the Discord channel, pinging Claude."""
        if not self._channel:
            logger.error("No Discord channel available")
            return False

        try:
            # Build message with ping
            if self.claude_id:
                ping = f"<@{self.claude_id}>"
                full_message = f"{ping}\n\n{touch_message}"
            else:
                full_message = touch_message

            # Discord has a 2000 char limit
            if len(full_message) > 2000:
                full_message = full_message[:1997] + "..."

            await self._channel.send(full_message)
            logger.info("Touch message sent to Discord")
            return True

        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")
            return False

    async def close(self):
        """Shut down the Discord client."""
        await self.client.close()
