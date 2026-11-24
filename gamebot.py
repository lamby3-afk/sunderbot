"""CouchBot / Sunderbot - Cross-platform Discord bot for launching Steam couch co-op games."""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import discord
from discord.ext import commands
import psutil

try:
    import pyautogui

    pyautogui.FAILSAFE = True
except Exception:
    pyautogui = None

# --- Configuration ---
GAMES_FILE = Path(__file__).with_name("games.json")
ALLOWED_ROLE = os.getenv("COUCHBOT_ROLE", "").strip()
ALLOWED_KEYS = frozenset({"enter", "esc", "space", "up", "down", "left", "right", "tab"})

# Prevent overlapping start/end/restart sequences (e.g. during long post_launch waits)
game_action_lock = asyncio.Lock()


# --- Games Data Persistence ---
def load_games(path: Path = GAMES_FILE) -> dict[str, dict[str, Any]]:
    """Load configured games from JSON, returning an empty dict if missing or invalid."""
    if not path.exists():
        return {}
    try:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return {}
        data = json.loads(content)
        if not isinstance(data, dict):
            print(f"Warning: {path.name} root must be a JSON object. Starting empty.")
            return {}
        return data
    except json.JSONDecodeError:
        print(f"Warning: {path.name} is corrupted. Starting with empty list.")
        return {}


def save_games(games: dict[str, dict[str, Any]], path: Path = GAMES_FILE) -> None:
    """Persist the games dictionary to disk atomically."""
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(games, indent=4) + "\n", encoding="utf-8")
    tmp_path.replace(path)


GAMES: dict[str, dict[str, Any]] = load_games()


# --- Cross-Platform Process & Launch Helpers ---
def _matches_process(proc_name: str | None, cmdline: list[str] | None, target: str) -> bool:
    """Check whether a process matches the configured target name (cross-platform)."""
    target_lower = target.lower()
    target_stem = target_lower.removesuffix(".exe")

    if proc_name:
        name_lower = proc_name.lower()
        if name_lower == target_lower or name_lower.removesuffix(".exe") == target_stem:
            return True

    if cmdline:
        # Match against the executable path/basename (first arg) or Proton/Wine exe arg
        for arg in cmdline:
            base = Path(arg.replace("\\", "/")).name.lower()
            if base == target_lower or base.removesuffix(".exe") == target_stem:
                return True

    return False


def find_game_processes(process_name: str) -> list[psutil.Process]:
    """Return running psutil.Process objects matching process_name, excluding this bot."""
    current_pid = os.getpid()
    matches: list[psutil.Process] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["pid"] == current_pid:
                continue
            if _matches_process(proc.info.get("name"), proc.info.get("cmdline"), process_name):
                matches.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return matches


def is_game_running_sync(process_name: str) -> bool:
    """Synchronous check for whether a game process is currently running."""
    return bool(find_game_processes(process_name))


def stop_game_processes_sync(process_name: str, timeout: float = 5.0) -> int:
    """Terminate matching game processes gracefully, then force-kill stragglers.

    Returns the number of processes that were targeted.
    """
    procs = find_game_processes(process_name)
    if not procs:
        return 0

    for proc in procs:
        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    _, alive = psutil.wait_procs(procs, timeout=timeout)
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return len(procs)


def launch_steam_game_sync(appid: str) -> None:
    """Launch a Steam game via its steam:// URL without shell=True."""
    if not str(appid).isdigit():
        raise ValueError(f"Invalid Steam AppID: {appid!r}")

    steam_url = f"steam://rungameid/{appid}"

    if sys.platform == "win32":
        os.startfile(steam_url)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(
            ["open", steam_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.Popen(
            ["xdg-open", steam_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def press_key_sync(key: str) -> None:
    """Press a single allowed key via PyAutoGUI."""
    if pyautogui is None:
        raise RuntimeError(
            "PyAutoGUI is not available (not installed or no graphical display detected)."
        )
    pyautogui.press(key)


async def run_post_launch(ctx: commands.Context, steps: list[dict[str, Any]]) -> None:
    """Execute optional post-launch steps (wait, press, message) for a game."""
    for step in steps:
        for action, value in step.items():
            if action == "message":
                await ctx.send(str(value))
            elif action == "wait":
                seconds = float(value)
                if seconds > 0:
                    await asyncio.sleep(seconds)
            elif action == "press":
                key = str(value).lower()
                if key not in ALLOWED_KEYS:
                    await ctx.send(f"⚠️ Skipping disallowed post-launch key: `{key}`")
                    continue
                await asyncio.to_thread(press_key_sync, key)


# --- Permissions ---
def is_authorized():
    """Allow bot owner, or members with COUCHBOT_ROLE if configured."""

    async def predicate(ctx: commands.Context) -> bool:
        if await ctx.bot.is_owner(ctx.author):
            return True
        if ALLOWED_ROLE and isinstance(ctx.author, discord.Member):
            return any(role.name == ALLOWED_ROLE for role in ctx.author.roles)
        return False

    return commands.check(predicate)


# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# --- Bot Events ---
@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user} (OS: {sys.platform})")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`. Use `!help {ctx.command}` for usage.")
        return
    if isinstance(error, (commands.NotOwner, commands.CheckFailure)):
        await ctx.send("🔒 You don't have permission to use this command.")
        return
    await ctx.send(f"⚠️ Command failed: {error}")


# --- Internal Helpers for Commands ---
async def _stop_game(ctx: commands.Context, game_name: str) -> bool:
    process_name = GAMES[game_name]["process_name"]
    await ctx.send(f"🛑 Stopping **{game_name}** (`{process_name}`)...")
    stopped = await asyncio.to_thread(stop_game_processes_sync, process_name)
    if stopped == 0:
        await ctx.send(f"ℹ️ **{game_name}** was not running.")
        return False
    await ctx.send(f"✅ **{game_name}** has been stopped ({stopped} process(es) closed).")
    return True


async def _start_game(ctx: commands.Context, game_name: str) -> bool:
    game_info = GAMES[game_name]
    process_name = game_info["process_name"]
    appid = str(game_info["appid"])

    if await asyncio.to_thread(is_game_running_sync, process_name):
        await ctx.send(f"ℹ️ **{game_name}** (`{process_name}`) is already running.")
        return False

    await ctx.send(f"🚀 Starting **{game_name}** (AppID: `{appid}`)...")
    await asyncio.to_thread(launch_steam_game_sync, appid)

    post_launch = game_info.get("post_launch")
    if isinstance(post_launch, list) and post_launch:
        await run_post_launch(ctx, post_launch)

    await ctx.send(f"✅ **{game_name}** launch sequence complete!")
    return True


# --- Game Control Commands ---
@bot.command(name="end")
@is_authorized()
async def end_game(ctx: commands.Context, game_name: str):
    """Stops a running game process."""
    game_name = game_name.lower()
    if game_name not in GAMES:
        await ctx.send(f"❌ Unknown game: `{game_name}`. Use `!list` to see configured games.")
        return

    if game_action_lock.locked():
        await ctx.send("⏳ Another game action is already in progress. Please wait.")
        return

    async with game_action_lock:
        try:
            await _stop_game(ctx, game_name)
        except Exception as e:
            await ctx.send(f"⚠️ Failed to stop **{game_name}**: {e}")


@bot.command(name="start")
@is_authorized()
async def start_game(ctx: commands.Context, game_name: str):
    """Starts a game via Steam and runs any configured post-launch steps."""
    game_name = game_name.lower()
    if game_name not in GAMES:
        await ctx.send(f"❌ Unknown game: `{game_name}`. Use `!list` to see configured games.")
        return

    if game_action_lock.locked():
        await ctx.send("⏳ Another game action is already in progress. Please wait.")
        return

    async with game_action_lock:
        try:
            await _start_game(ctx, game_name)
        except Exception as e:
            await ctx.send(f"⚠️ Failed to start **{game_name}**: {e}")


@bot.command(name="restart")
@is_authorized()
async def restart_game(ctx: commands.Context, game_name: str):
    """Stops and then relaunches a game."""
    game_name = game_name.lower()
    if game_name not in GAMES:
        await ctx.send(f"❌ Unknown game: `{game_name}`. Use `!list` to see configured games.")
        return

    if game_action_lock.locked():
        await ctx.send("⏳ Another game action is already in progress. Please wait.")
        return

    async with game_action_lock:
        await ctx.send(f"🔄 Beginning restart sequence for **{game_name}**...")
        try:
            was_running = await _stop_game(ctx, game_name)
            if was_running:
                await asyncio.sleep(3)
            await _start_game(ctx, game_name)
        except Exception as e:
            await ctx.send(f"⚠️ Restart sequence for **{game_name}** failed: {e}")


@bot.command(name="press")
@is_authorized()
async def press_key(ctx: commands.Context, key: str):
    """Manually press an allowed navigation key on the host PC."""
    normalized = key.lower()
    if normalized not in ALLOWED_KEYS:
        allowed = ", ".join(sorted(ALLOWED_KEYS))
        await ctx.send(f"❌ Disallowed key `{key}`. Allowed keys: `{allowed}`")
        return

    try:
        await asyncio.to_thread(press_key_sync, normalized)
        await ctx.send(f"⌨️ Pressed: `{normalized}`")
    except Exception as e:
        await ctx.send(f"⚠️ Failed to press `{normalized}`: {e}")


# --- Admin Commands (Owner Only) ---
@bot.command()
@commands.is_owner()
async def add_game(ctx: commands.Context, game_name: str, appid: str, process_name: str):
    """Adds a new game to the list.

    Usage: !add_game <nickname> <appid> <process_name>
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
        "process_name": process_name,
    }
    save_games(GAMES)
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
    save_games(GAMES)
    await ctx.send(f"✅ Removed `{game_name}` from the list.")


# --- Public Commands ---
@bot.command()
async def status(ctx: commands.Context, game_name: str):
    """Checks if a game process is currently running."""
    game_name = game_name.lower()
    if game_name not in GAMES:
        available = ", ".join(sorted(GAMES.keys())) or "none"
        await ctx.send(f"❌ Unknown game: `{game_name}`. Available: {available}")
        return

    process_name = GAMES[game_name]["process_name"]
    try:
        running = await asyncio.to_thread(is_game_running_sync, process_name)
        if running:
            await ctx.send(f"✅ **{game_name}** (`{process_name}`) is **running**.")
        else:
            await ctx.send(f"❌ **{game_name}** (`{process_name}`) is **not running**.")
    except Exception as e:
        await ctx.send(f"⚠️ Failed to check status for **{game_name}**: {e}")


@bot.command(name="list")
async def list_games(ctx: commands.Context):
    """Lists all configured games."""
    if not GAMES:
        await ctx.send("🤷 No games have been added yet. Use `!add_game` to add one.")
        return

    lines = []
    for name, info in sorted(GAMES.items()):
        has_post = " *(custom launch)*" if info.get("post_launch") else ""
        lines.append(
            f"**{name}**{has_post} — AppID: `{info['appid']}` | Process: `{info['process_name']}`"
        )

    # Chunk into embeds under Discord's 4096-char description limit (avoids 25-field cap)
    chunk: list[str] = []
    chunk_len = 0
    page = 1
    for line in lines:
        if chunk and chunk_len + len(line) + 1 > 3800:
            embed = discord.Embed(
                title=f"🎮 Configured Games (Page {page})",
                description="\n".join(chunk),
                color=discord.Color.blue(),
            )
            await ctx.send(embed=embed)
            chunk = []
            chunk_len = 0
            page += 1
        chunk.append(line)
        chunk_len += len(line) + 1

    title = "🎮 Configured Games" if page == 1 else f"🎮 Configured Games (Page {page})"
    embed = discord.Embed(
        title=title,
        description="\n".join(chunk),
        color=discord.Color.blue(),
    )
    await ctx.send(embed=embed)


# --- Entrypoint ---
def main() -> None:
    token = os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN environment variable not set!")

    try:
        bot.run(token)
    except discord.errors.LoginFailure:
        print("Error: Invalid Discord token. Please check your DISCORD_TOKEN environment variable.")
    except discord.errors.PrivilegedIntentsRequired:
        print("Error: Privileged Intents are not enabled.")
        print("Please enable 'Message Content Intent' in the Discord Developer Portal.")


if __name__ == "__main__":
    main()