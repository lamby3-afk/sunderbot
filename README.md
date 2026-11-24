# sunderbot / CouchBot

A cross-platform (Windows / Linux / macOS) Discord bot to launch and manage Steam couch co-op games for 24/7 playability.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Enable **Message Content Intent** for your bot in the Discord Developer Portal.
3. Set environment variables:
   - `DISCORD_TOKEN` *(required)*: Your Discord bot token.
   - `COUCHBOT_ROLE` *(optional)*: Name of a Discord role allowed to use `!start`, `!end`, `!restart`, and `!press`. If omitted, those commands are restricted to the bot owner.
4. Run the bot:
   ```bash
   python gamebot.py
   ```

## Commands

| Command | Access | Description |
| :--- | :--- | :--- |
| `!list` | Everyone | Lists all configured games |
| `!status <game>` | Everyone | Checks if a game process is running |
| `!start <game>` | Owner / Role | Launches a game via Steam and runs any `post_launch` steps |
| `!end <game>` | Owner / Role | Stops a running game |
| `!restart <game>` | Owner / Role | Stops and relaunches a game |
| `!press <key>` | Owner / Role | Sends an allowed key (`enter`, `esc`, `space`, `up`, `down`, `left`, `right`, `tab`) |
| `!add_game <name> <appid> <process>` | Owner | Adds a game to `games.json` |
| `!remove_game <name>` | Owner | Removes a game from `games.json` |

## Custom Post-Launch Sequences

You can add an optional `post_launch` list to any game in `games.json` (for example, waiting for Sunderfolk's splash screen and pressing Enter twice):

```json
{
    "sunderfolk": {
        "appid": "2414270",
        "process_name": "Sunderfolk",
        "post_launch": [
            {"message": "⏳ Waiting 60s for splash screen and QR generation...", "wait": 60},
            {"press": "enter", "wait": 1},
            {"press": "enter", "message": "📱 QR code should now be available for log in."}
        ]
    }
}
```

## Streaming / Playing

- For Sunderfolk or phone-controlled party games, Discord stream is available in **24/7 Couchgames**.
- For action games or anything requiring PC/Joypad controls, connect via **Parsec** (share your PeerID privately in Discord).
