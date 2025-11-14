import discord
from discord.ext import commands
import subprocess
import json
import os
import asyncio # Used for asyncio.sleep()

# --- Configuration ---
# Load token from environment variable for security
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable not set!")
    
GAMES_FILE = "games.json"

# --- Load Games Data ---
if os.path.exists(GAMES_FILE):
    try:
        with open(GAMES_FILE, "r") as f:
            GAMES = json.load(f)
    except json.JSONDecodeError:
        print(f"Warning: {GAMES_FILE} is corrupted. Starting with empty list.")
        GAMES = {}
else:
    GAMES = {}

# --- Bot Setup ---
# Must enable message_content intent in code AND Discord Developer Portal
intents = discord.Intents.all()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

def save_games():
    """Saves the current GAMES dict to the JSON file."""
    with open(GAMES_FILE, "w") as f:
        json.dump(GAMES, f, indent=4)

# --- Bot Events ---
@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")

# --- Admin Commands (Owner Only) ---

@bot.command(name="end")
@commands.is_owner()
async def end_game(ctx: commands.Context, game_name: str):
    """Stops a game process (Windows)."""
    game_name = game_name.lower()
    if game_name not in GAMES:
        await ctx.send(f"❌ Unknown game: `{game_name}`.")
        return

    process_name = GAMES[game_name]["process_name"]
    await ctx.send(f"🛑 Stopping **{game_name}** (`{process_name}`)...")
    
    try:
        # 1. Kill the process using taskkill
        subprocess.run(["taskkill", "/F", "/IM", process_name], 
                         check=False, 
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         creationflags=subprocess.CREATE_NO_WINDOW)
        await ctx.send(f"✅ {game_name} has been stopped.")
    except Exception as e:
        await ctx.send(f"⚠️ Failed to stop {game_name}: {e}")

@bot.command(name="start")
@commands.is_owner()
async def start_game(ctx: commands.Context, game_name: str):
    """Starts a game via Steam (Windows)."""
    game_name = game_name.lower()
    if game_name not in GAMES:
        await ctx.send(f"❌ Unknown game: `{game_name}`.")
        return

    game_info = GAMES[game_name]
    process_name = game_info["process_name"]
    appid = game_info["appid"]

    # --- Check status first to avoid double-launch ---
    try:
        cmd = ["tasklist", "/FI", f"IMAGENAME eq {process_name}"]
        result = subprocess.run(cmd, 
                                stdout=subprocess.PIPE, 
                                text=True, 
                                creationflags=subprocess.CREATE_NO_WINDOW)
        
        if process_name.lower() in result.stdout.lower():
            await ctx.send(f"ℹ️ **{game_name}** (`{process_name}`) is already running.")
            return
    except Exception as e:
        await ctx.send(f"⚠️ Failed to check status before starting: {e}")
        return # Don't proceed if status check failed
    # --- End status check ---

    await ctx.send(f"🚀 Starting **{game_name}** (AppID: `{appid}`)...")
    try:
        # 2. Relaunch using 'start' command and shell=True
        subprocess.Popen(f"start steam://rungameid/{appid}", 
                         shell=True, 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL)
                         
        await ctx.send(f"✅ {game_name} has been launched successfully!")
    except Exception as e:
        await ctx.send(f"⚠️ Failed to start {game_name}: {e}")

@bot.command()
@commands.is_owner()
async def restart(ctx: commands.Context, game_name: str):
    """Stops and then starts a game (Windows)."""
    await ctx.send(f"🔄 Beginning restart sequence for **{game_name}**...")
    
    # 1. Invoke the 'end' command
    end_command = bot.get_command("end")
    if end_command:
        await ctx.invoke(end_command, game_name=game_name)
    else:
        await ctx.send("Error: 'end' command not found.")
        return

    # Give it a few seconds to fully shut down
    await asyncio.sleep(3) 

    # 2. Invoke the 'start' command
    start_command = bot.get_command("start")
    if start_command:
        await ctx.invoke(start_command, game_name=game_name)
    else:
        await ctx.send("Error: 'start' command not found.")
        return
    
    await ctx.send(f"✅ Restart sequence for **{game_name}** is complete.")

@bot.command()
@commands.is_owner()
async def add_game(ctx: commands.Context, game_name: str, appid: str, process_name: str):
    """Adds a new game to the list. (Windows)
    
    Usage: !add_game <nickname> <appid> <process_name.exe>
    Example: !add_game valheim 892970 valheim_server.exe
    """
    game_name = game_name.lower()
    if game_name in GAMES:
        await ctx.send(f"⚠️ `{game_name}` already exists.")
        return
        
    if not appid.isdigit():
        await ctx.send("❌ AppID must be a number.")
        return

    GAMES[game_name] = {
        "appid": appid,
        "process_name": process_name
    }
    save_games()
    await ctx.send(f"✅ Added `{game_name}` (AppID: `{appid}`, Process: `{process_name}`).")

@bot.command()
@commands.is_owner()
async def remove_game(ctx: commands.Context, game_name: str):
    """Removes a game from the list."""
    game_name = game_name.lower()
    if game_name not in GAMES:
        await ctx.send(f"❌ `{game_name}` not found.")
        return
        
    del GAMES[game_name]
    save_games()
    await ctx.send(f"✅ Removed `{game_name}` from the list.")

# --- Public Commands ---
@bot.command()
async def status(ctx: commands.Context, game_name: str):
    """Checks if a game process is running (Windows)."""
    game_name = game_name.lower()
    if game_name not in GAMES:
        await ctx.send(f"❌ Unknown game: `{game_name}`. Available: {', '.join(GAGES.keys())}")
        return

    process_name = GAMES[game_name]["process_name"]
    try:
        # 1. Use tasklist to find the process
        cmd = ["tasklist", "/FI", f"IMAGENAME eq {process_name}"]
        result = subprocess.run(cmd, 
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE, 
                                 text=True, 
                                 creationflags=subprocess.CREATE_NO_WINDOW)

        # 2. Check if the process name is in the output
        if process_name.lower() in result.stdout.lower():
            await ctx.send(f"✅ **{game_name}** (`{process_name}`) is **running**.")
        else:
            await ctx.send(f"❌ **{game_name}** (`{process_name}`) is **not running**.")
    except Exception as e:
        await ctx.send(f"⚠️ Failed to check status for {game_name}: {e}")

@bot.command(name="list") # Renamed to 'list' for brevity
async def list_games(ctx: commands.Context):
    """Lists all configured games."""
    if not GAMES:
        await ctx.send("🤷 No games have been added yet. Use `!add_game` to add one.")
        return
        
    embed = discord.Embed(title="🎮 Configured Games", color=discord.Color.blue())
    for name, info in GAMES.items():
        embed.add_field(
            name=f"**{name}**", 
            value=f"AppID: `{info['appid']}`\nProcess: `{info['process_name']}`", 
            inline=False
        )
    await ctx.send(embed=embed)


# --- Run Bot ---
try:
    bot.run(TOKEN)
except discord.errors.LoginFailure:
    print("Error: Invalid Discord token. Please check your DISCORD_TOKEN environment variable.")
except discord.errors.PrivilegedIntentsRequired:
    print("Error: Privileged Intents are not enabled.")
    print("Please enable 'Message Content Intent' in the Discord Developer Portal.")