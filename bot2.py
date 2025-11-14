import discord
from discord.ext import commands
import subprocess
import os
import pyautogui
import asyncio  # Required for the wait timer

# Configuration
STEAM_GAME_ID = "2414270"
TOKEN = os.getenv("DISCORD_BOT_TOKEN", "INSERT DISCORD TOKEN HERE")

# PyAutoGUI Safety
pyautogui.FAILSAFE = True

intents = discord.Intents.all()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")

@bot.command()
async def restart_game(ctx):
    """Restart game, wait 15s, then press Enter twice."""
    await ctx.send("🔄 Closing Sunderfolk...")

    try:
        # 1. Kill the game
        subprocess.run(["pkill", "-f", "Sunderfolk"], check=False)
        await asyncio.sleep(2) # Give it a moment to close completely

        # 2. Launch the game
        subprocess.Popen(
            ["xdg-open", f"steam://rungameid/{STEAM_GAME_ID}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await ctx.send("🚀 Game launching... Waiting 60s for splash screen and QR generation.")

        # 3. Wait 15 seconds (asynchronously, so the bot stays responsive)
        await asyncio.sleep(60)

        # 4. Send 2 Enter presses
        # We add a small delay between presses to ensure the game registers both
        pyautogui.press('enter')
        await asyncio.sleep(1)
        pyautogui.press('enter')

        await ctx.send("✅ startup sequence complete (QR code should be available for log in).")

    except Exception as e:
        await ctx.send(f"⚠️ Error during restart sequence: {e}")

@bot.command()
async def press(ctx, key: str):
    """Manually press a key."""
    allowed_keys = ['enter', 'esc', 'space', 'up', 'down', 'left', 'right']
    if len(key) == 1 or key.lower() in allowed_keys:
        pyautogui.press(key.lower())
        await ctx.send(f"⌨️ Pressed: `{key}`")
    else:
        await ctx.send("❌ Invalid key.")

@bot.command()
async def status_game(ctx):
    """Checks if the game process is currently running."""
    try:
        # pgrep returns exit code 0 if found, 1 if not found
        result = subprocess.run(["pgrep", "-f", "Sunderfolk"], stdout=subprocess.PIPE)

        if result.returncode == 0:
            await ctx.send("✅ Sunderfolk is currently **running**.")
        else:
            await ctx.send("❌ Sunderfolk is **not running**.")

    except FileNotFoundError:
        await ctx.send("❌ Error: 'pgrep' command not found. This bot requires Linux.")
    except Exception as e:
        await ctx.send(f"⚠️ Failed to check status: {e}")

if TOKEN == "YOUR_BOT_TOKEN_HERE":
    print("❌ Error: Please put your Bot Token in the code.")
else:
    bot.run(TOKEN)
