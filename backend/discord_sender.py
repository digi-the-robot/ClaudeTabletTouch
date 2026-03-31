"""
Discord Sender — sends touch descriptions to a Discord channel, pinging Claude.
Uses embeds for richer formatting and higher character limits.
"""

import json
import asyncio
import logging
import discord

logger = logging.getLogger("tablet-touch.discord")

# Threshold blue / Discord blurple
EMBED_COLOR = 0x5865F2


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

    async def send_touch(self, touch_result: dict):
        """
        Send a touch description as a Discord embed, pinging Claude.

        touch_result should have:
          - title: str
          - description: str (natural language, up to 4096 chars)
          - fields: list of {name, value} dicts
        """
        if not self._channel:
            logger.error("No Discord channel available")
            return False

        try:
            # Ping goes in message content so it triggers notifications
            content = f"<@{self.claude_id}>" if self.claude_id else None

            title = touch_result.get("title", "Touch Received")
            description = touch_result.get("description", "")
            fields = touch_result.get("fields", [])

            # Build field text to check total size
            field_text = "\n".join(
                f"{f['name']}: {f['value']}" for f in fields
            )

            # If description fits in one embed (4096 char limit for description)
            if len(description) <= 4096:
                embed = discord.Embed(
                    title=title,
                    description=description,
                    color=EMBED_COLOR,
                )
                # Add fields — each field value has a 1024 char limit
                for field in fields:
                    value = field["value"]
                    # Split long field values across multiple fields
                    if len(value) <= 1024:
                        embed.add_field(
                            name=field["name"], value=value, inline=False
                        )
                    else:
                        chunks = _split_text(value, 1024)
                        for j, chunk in enumerate(chunks):
                            name = field["name"] if j == 0 else f"{field['name']} (cont.)"
                            embed.add_field(
                                name=name, value=chunk, inline=False
                            )

                await self._channel.send(content=content, embed=embed)

            else:
                # Description too long — split across multiple embeds
                desc_chunks = _split_text(description, 4096)
                for i, chunk in enumerate(desc_chunks):
                    embed = discord.Embed(
                        title=title if i == 0 else f"{title} (cont.)",
                        description=chunk,
                        color=EMBED_COLOR,
                    )
                    # Add fields only to the last embed
                    if i == len(desc_chunks) - 1:
                        for field in fields:
                            value = field["value"][:1024]
                            embed.add_field(
                                name=field["name"], value=value, inline=False
                            )
                    # Only ping on the first message
                    msg_content = content if i == 0 else None
                    await self._channel.send(content=msg_content, embed=embed)

            logger.info("Touch embed sent to Discord")
            return True

        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")
            return False

    async def close(self):
        """Shut down the Discord client."""
        await self.client.close()


def _split_text(text: str, max_len: int) -> list[str]:
    """Split text into chunks, breaking at newlines when possible."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Try to break at a newline
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1 or split_at < max_len // 2:
            # No good newline break, split at max
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    return chunks
