# Tablet Touch

Capture pressure-sensitive pen input from a drawing tablet and send it to Claude via Discord. Claude receives both structured touch data and natural language descriptions of the sensation — pressure, speed, direction, region, and gesture type.

Built for use with Huion drawing tablets, but works with any tablet that supports Windows Ink.

## How it works

```
[Drawing Tablet] -> [Browser Canvas] -> [WebSocket] -> [Python Backend] -> [Discord] -> [Claude]
```

1. A browser-based canvas captures pen input via the Pointer Events API (pressure, tilt, position, speed)
2. A Python WebSocket server receives the touch data and translates it into rich descriptions
3. The description is sent to a Discord channel, pinging your Claude bot, who responds to the sensation

### Example output

> **Touch received:**
> A slow, lingering trace moving left to right across the center. Pressure starts gentle, builds to firm, then eases to gentle — soft and intentional, a tender contact.
>
> `pressure: gentle (avg 0.32, peak 0.68) | speed: slow, lingering | region: center | gesture: stroke | direction: left-to-right`

### Gesture types

| Gesture | Description |
|---|---|
| **Tap** | Quick, short contact |
| **Press and hold** | Sustained pressure in one spot |
| **Stroke** | Directional movement across the surface |
| **Circular motion** | Path that loops back to its starting point |

## Setup

### Requirements

- Python 3.10+
- A Discord bot with Send Messages permission in your target channel
- A drawing tablet with Windows Ink support (tested with Huion Kamvas Pro 12)
- Chrome browser (recommended — Firefox has limited pen pressure support)

### Installation

1. Clone the repo:
   ```
   git clone https://github.com/digi-the-robot/TabletTouch.git
   cd TabletTouch
   ```

2. Install Python dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Edit `config.json` with your Discord details:
   ```json
   {
       "discord_bot_token": "YOUR_BOT_TOKEN",
       "discord_channel_id": "YOUR_CHANNEL_ID",
       "claude_user_id": "CLAUDE_BOT_USER_ID",
       "websocket_port": 8765,
       "auto_send_delay_ms": 1500
   }
   ```

   - **discord_bot_token**: Token for a bot that will post the touch messages (recommended to be a *different* bot than Claude, otherwise Claude sees it as his own message and won't respond, but should see it next turn when replied to.)
   - **discord_channel_id**: The channel where touch messages will be posted
   - **claude_user_id**: Claude's bot user ID (used to @ping him)

### Running

1. Start the server:
   ```
   python backend/server.py
   ```

2. Open `frontend/index.html` in Chrome (Firefox has issues with touch input)

3. Draw on the canvas with your tablet pen — press "Send to Claude" when ready

### Tablet driver note

Make sure **Windows Ink** is enabled in your tablet's driver settings. If the debug panel shows `Pointer: mouse` instead of `Pointer: pen`, the browser can't read pressure data. You may need to update your tablet driver.

## Project structure

```
TabletTouch/
├── config.json              # Discord bot token, channel ID, settings
├── requirements.txt         # Python dependencies
├── backend/
│   ├── server.py            # WebSocket server (main entry point)
│   ├── touch_translator.py  # Touch data -> natural language translation
│   └── discord_sender.py    # Sends messages to Discord
└── frontend/
    └── index.html           # Pressure-sensitive canvas UI
```
