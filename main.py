import discord
from discord.ext import commands, tasks
import asyncio
import datetime
import os

# Optional: load from .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # It's okay if python-dotenv isn't installed

token = os.getenv('DISCORD_BOT_TOKEN')
if not token:
    print("❌ Error: DISCORD_BOT_TOKEN environment variable not set!")
    print("Set it in your environment or in a .env file (DISCORD_BOT_TOKEN=...)")
    exit(1)

# Import our custom modules
from data import load_settings, save_settings, load_temp_channels, save_temp_channels
from perms import check_text_channel_permissions, format_permission_error
from setup import setup_echonet, diagnose_permissions
from menus import (
    MainMenu, 
    ApproveDenyView, 
    ensure_main_menu, 
    purge_menu_text_channel,
    MAIN_MENU_TAG
)

# Bot setup
intents = discord.Intents.default()
intents.guilds = True
intents.guild_messages = True
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")

temp_channels = {}

def save_data():
    save_temp_channels(temp_channels)

def load_data():
    global temp_channels
    temp_channels = load_temp_channels()

@tasks.loop(minutes=5)
async def check_expired_channels():
    now = datetime.datetime.utcnow()
    to_delete = []
    for channel_id, info in temp_channels.items():
        if now >= info["expires_at"]:
            to_delete.append(channel_id)
    for channel_id in to_delete:
        channel = None
        for guild in bot.guilds:
            channel = guild.get_channel(channel_id)
            if channel:
                break
        if channel:
            from perms import check_voice_channel_permissions
            missing_perms = check_voice_channel_permissions(channel)
            if not missing_perms:
                owner = None
                for guild in bot.guilds:
                    owner = guild.get_member(temp_channels[channel_id]["owner_id"])
                    if owner:
                        break
                if owner:
                    try:
                        await owner.send(f"⏰ Your voice channel **{channel.name}** has expired and been deleted.")
                    except:
                        pass
                try:
                    await channel.delete(reason="Time limit expired")
                except:
                    pass
            info = temp_channels.get(channel_id)
            if info and "menu_message_id" in info and "menu_channel_id" in info:
                menu_channel = bot.get_channel(info["menu_channel_id"])
                if menu_channel:
                    try:
                        menu_msg = await menu_channel.fetch_message(info["menu_message_id"])
                        await menu_msg.delete()
                    except Exception:
                        pass
        if channel_id in temp_channels:
            del temp_channels[channel_id]
    if to_delete:
        save_data()

@bot.event
async def on_ready():
    print(f"✅ Bot logged in as {bot.user}")
    load_data()
    check_expired_channels.start()
    bot.add_view(MainMenu())
    bot.add_view(ApproveDenyView())
    print("🔄 Background tasks started")
    print(f"📊 Loaded {len(temp_channels)} active channels")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
        return
    else:
        print(f"Command error: {error}")
        await ctx.send(f"❌ An error occurred: {str(error)}")

@bot.command(name="voice")
async def voice_command(ctx):
    settings = load_settings()
    guild_id = str(ctx.guild.id)
    if guild_id not in settings:
        await ctx.send("❌ Setup not complete. Please ask an admin to run `!echonetsetup` first.")
        return
    text_channel_id = settings[guild_id]["text_channel_id"]
    menu_text_channel = ctx.guild.get_channel(text_channel_id)
    if not menu_text_channel:
        await ctx.send("❌ The saved menu text channel no longer exists. Please ask an admin to run `!echonetsetup` again.")
        return
    missing_perms = check_text_channel_permissions(menu_text_channel)
    if missing_perms:
        perm_error = format_permission_error(missing_perms, f"Text Channel {menu_text_channel.name}")
        await ctx.send(f"❌ Cannot set up menu due to missing permissions:\n{perm_error}\n\nPlease grant these permissions and try again.")
        return
    await purge_menu_text_channel(menu_text_channel)
    await ensure_main_menu(menu_text_channel)
    await ctx.send(f"✅ Main menu is ready in <#{menu_text_channel.id}>.")

@bot.command(name="echonetsetup")
@commands.has_permissions(manage_channels=True)
async def echonetsetup_command(ctx):
    await setup_echonet(ctx, bot)

@bot.command(name="echonetdiagnose")
@commands.has_permissions(manage_channels=True)
async def echonetdiagnose_command(ctx):
    await diagnose_permissions(ctx)

@bot.command(name="echonetstats")
@commands.has_permissions(manage_channels=True)
async def echonetstats_command(ctx):
    guild_channels = [cid for cid, info in temp_channels.items() 
                     if ctx.guild.get_channel(cid) is not None]
    embed = discord.Embed(
        title="📊 EchoNet Statistics",
        color=0x00ff00
    )
    embed.add_field(name="Active Channels (This Server)", value=str(len(guild_channels)), inline=True)
    embed.add_field(name="Total Active Channels", value=str(len(temp_channels)), inline=True)
    embed.add_field(name="Servers Using EchoNet", value=str(len(bot.guilds)), inline=True)
    if guild_channels:
        channel_info = []
        for cid in guild_channels[:5]:
            channel = ctx.guild.get_channel(cid)
            if channel:
                info = temp_channels[cid]
                owner = ctx.guild.get_member(info["owner_id"])
                owner_name = owner.display_name if owner else "Unknown"
                expires = info["expires_at"].strftime("%Y-%m-%d %H:%M UTC")
                channel_info.append(f"**{channel.name}** - {owner_name} (expires {expires})")
        if channel_info:
            embed.add_field(
                name="Recent Channels", 
                value="\n".join(channel_info), 
                inline=False
            )
    await ctx.send(embed=embed)

@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="🎤 EchoNet Voice Channel Bot",
        description="Create and manage temporary voice channels!",
        color=0x00ff00
    )
    embed.add_field(
        name="👤 User Commands",
        value="`!voice` - Set up the main menu\n`!help` - Show this help message",
        inline=False
    )
    embed.add_field(
        name="👑 Admin Commands",
        value="`!echonetsetup` - Initial bot setup\n`!echonetdiagnose` - Check permissions\n`!echonetstats` - Show statistics",
        inline=False
    )
    embed.add_field(
        name="✨ Features",
        value="• Create temporary voice channels\n• Set custom duration (1-60 days)\n• Choose access type (Open/Request Only)\n• Full channel management\n• User blocking system\n• Ownership transfer",
        inline=False
    )
    embed.add_field(
        name="🔧 Setup Instructions",
        value="1. Run `!echonetsetup` to configure the bot\n2. Run `!voice` to create the main menu\n3. Users can now create channels!",
        inline=False
    )
    embed.set_footer(text="EchoNet Bot - Making voice channels easy!")
    await ctx.send(embed=embed)

if __name__ == "__main__":
    try:
        bot.run(token)
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
