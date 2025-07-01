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
    print(f"Available env vars: {list(os.environ.keys())}")
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

@tasks.loop(minutes=30)
async def clean_menu_channels():
    """Periodically clean menu text channels across all servers."""
    settings = load_settings()
    for guild_id, guild_settings in settings.items():
        try:
            guild = bot.get_guild(int(guild_id))
            if not guild:
                continue
                
            text_channel_id = guild_settings.get("text_channel_id")
            if not text_channel_id:
                continue
                
            text_channel = guild.get_channel(text_channel_id)
            if not text_channel:
                continue
                
            # Check if there are any non-bot messages or old bot messages
            should_clean = False
            async for message in text_channel.history(limit=50):
                if (not message.pinned and 
                    (message.author != guild.me or 
                     not message.content.startswith(MAIN_MENU_TAG))):
                    should_clean = True
                    break
            
            if should_clean:
                from menus import purge_menu_text_channel, ensure_main_menu
                await purge_menu_text_channel(text_channel)
                await ensure_main_menu(text_channel)
                
        except Exception as e:
            print(f"Error cleaning menu channel for guild {guild_id}: {e}")

@bot.event
async def on_ready():
    print(f"✅ Bot logged in as {bot.user}")
    load_data()
    check_expired_channels.start()
    clean_menu_channels.start()
    bot.add_view(MainMenu())
    bot.add_view(ApproveDenyView())
    print("🔄 Background tasks started")
    print(f"📊 Loaded {len(temp_channels)} active channels")

@bot.event
async def on_guild_join(guild):
    """Send welcome message when bot joins a new server."""
    # Find a channel where the bot can send messages
    channel = None
    
    # Try to find system channel first
    if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
        channel = guild.system_channel
    else:
        # Find any text channel where bot can send messages
        for text_channel in guild.text_channels:
            if text_channel.permissions_for(guild.me).send_messages:
                channel = text_channel
                break
    
    if channel:
        embed = discord.Embed(
            title="🎉 Thanks for adding EchoNet!",
            description="I'm here to help you create awesome temporary voice channels!",
            color=0x00ff00
        )
        
        embed.add_field(
            name="🚀 Quick Setup (2 steps)",
            value="**Step 1:** Run `!echonetsetup` (requires Manage Channels permission)\n**Step 2:** Run `!voice` to create the interactive menu",
            inline=False
        )
        
        embed.add_field(
            name="✨ What I Can Do",
            value="• Create temporary voice channels (1-60 days)\n• Set access control (Open/Request Only)\n• Automatic cleanup when expired\n• Full channel management tools\n• User blocking and invitation system",
            inline=False
        )
        
        embed.add_field(
            name="🔧 Required Permissions",
            value="Make sure I have these permissions:\n• **Manage Channels** (create/delete channels)\n• **Send Messages** & **Embed Links**\n• **Manage Messages** (keep menus clean)\n• **Read Message History**",
            inline=False
        )
        
        embed.add_field(
            name="📚 Need Help?",
            value="• `!help` - Complete setup and usage guide\n• `!echonetdiagnose` - Check permission issues\n• `!echonetstats` - View server statistics",
            inline=False
        )
        
        embed.set_footer(text="EchoNet Bot - Ready to make voice channels awesome!")
        
        try:
            await channel.send(embed=embed)
        except:
            pass  # Silently fail if we can't send the message

@bot.event
async def on_message(message):
    """Handle messages and keep menu channels clean."""
    # Process commands first
    await bot.process_commands(message)
    
    # Don't process bot's own messages
    if message.author == bot.user:
        return
        
    # Check if this message is in a menu text channel
    settings = load_settings()
    guild_id = str(message.guild.id) if message.guild else None
    
    if guild_id and guild_id in settings:
        text_channel_id = settings[guild_id].get("text_channel_id")
        if text_channel_id == message.channel.id:
            # This is a menu channel, delete the user's message after a short delay
            try:
                await asyncio.sleep(2)  # Give users a moment to see their message was received
                await message.delete()
            except:
                pass  # Ignore if we can't delete (permissions, message already deleted, etc.)

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
        await ctx.send(f"❌ Cannot set up menu due to missing permissions:\\n{perm_error}\\n\\nPlease grant these permissions and try again.")
        return
    await purge_menu_text_channel(menu_text_channel)
    await ensure_main_menu(menu_text_channel)

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
                value="\\n".join(channel_info), 
                inline=False
            )
    await ctx.send(embed=embed)

@bot.command(name="echonetguide")
@commands.has_permissions(manage_channels=True)
async def echonetguide_command(ctx):
    """Comprehensive setup and usage guide."""
    settings = load_settings()
    guild_id = str(ctx.guild.id)
    is_setup = guild_id in settings
    
    embed = discord.Embed(
        title="📖 EchoNet Complete Setup Guide",
        description="Follow this guide to set up and use EchoNet in your server.",
        color=0x3498db
    )
    
    if not is_setup:
        embed.add_field(
            name="🟥 Step 1: Initial Setup (Not Done)",
            value="Run `!echonetsetup` to begin setup.\n\n**This will:**\n• Ask for category names\n• Ask for text channel name\n• Create categories and channels\n• Set up permissions",
            inline=False
        )
        embed.add_field(
            name="⬜ Step 2: Create Menu (Waiting)",
            value="After setup, run `!voice` to create the interactive menu.",
            inline=False
        )
    else:
        text_channel_id = settings[guild_id].get("text_channel_id")
        text_channel = ctx.guild.get_channel(text_channel_id) if text_channel_id else None
        
        embed.add_field(
            name="✅ Step 1: Initial Setup (Complete)",
            value="Setup is complete! Your categories and channels are ready.",
            inline=False
        )
        
        if text_channel:
            embed.add_field(
                name="✅ Step 2: Create Menu",
                value=f"Your menu channel is {text_channel.mention}.\nRun `!voice` to refresh the menu if needed.",
                inline=False
            )
        else:
            embed.add_field(
                name="🟨 Step 2: Create Menu (Channel Missing)",
                value="Your text channel is missing. Run `!echonetsetup` again to recreate it.",
                inline=False
            )
    
    embed.add_field(
        name="🎯 How Users Create Channels",
        value="1. Go to your EchoNet menu channel\n2. Click '🎤 Create Voice Channel'\n3. Enter channel name\n4. Choose duration (1-60 days)\n5. Pick access type (Open/Request Only)\n6. Click 'Create Channel'",
        inline=False
    )
    
    embed.add_field(
        name="🛠️ Channel Management Features",
        value="**Channel owners can:**\n• Transfer ownership\n• Invite/kick users\n• Block/unblock users\n• Change access type\n• Set user limits\n• Extend duration\n• View channel stats\n• Delete channel early",
        inline=False
    )
    
    embed.add_field(
        name="🔧 Admin Commands",
        value="`!echonetsetup` - Initial setup\n`!echonetdiagnose` - Check permissions\n`!echonetstats` - View statistics\n`!voice` - Create/refresh menu\n`!help` - Show help guide",
        inline=False
    )
    
    embed.set_footer(text="Need more help? Use !help for detailed guides!")
    await ctx.send(embed=embed)

@bot.command(name="help")
async def help_command(ctx):
    # Check if user is admin to show appropriate help
    is_admin = ctx.author.guild_permissions.manage_channels
    
    if is_admin and not ctx.message.content.endswith(" user"):
        # Show admin help by default for admins
        embed = discord.Embed(
            title="🎤 EchoNet Voice Channel Bot - Admin Guide",
            description="**Welcome to EchoNet!** Here's everything you need to know to set up and manage the bot.",
            color=0x00ff00
        )
        
        embed.add_field(
            name="🚀 Initial Setup (Required)",
            value="**Step 1:** Run `!echonetsetup`\n• Bot will ask for category names and text channel name\n• Creates categories and channels automatically\n• Sets up proper permissions\n\n**Step 2:** Run `!voice`\n• Creates the interactive menu in your text channel\n• Users can now start creating channels!",
            inline=False
        )
        
        embed.add_field(
            name="👑 Admin Commands",
            value="`!echonetsetup` - Initial bot setup (run this first!)\n`!echonetdiagnose` - Check bot permissions\n`!echonetstats` - View server statistics\n`!help user` - Show user help guide",
            inline=False
        )
        
        embed.add_field(
            name="🔧 Bot Permissions Required",
            value="**Essential permissions:**\n• Manage Channels (create/delete channels)\n• Send Messages & Embed Links\n• Read Message History\n• Manage Messages (keep menu clean)\n• View Channels",
            inline=False
        )
        
        embed.add_field(
            name="🎯 What EchoNet Does",
            value="• **Creates temporary voice channels** with custom durations\n• **Automatic cleanup** - channels expire and are deleted\n• **Access control** - open or request-only channels\n• **Channel management** - kick, block, transfer ownership\n• **Clean interface** - interactive buttons in your text channel",
            inline=False
        )
        
        embed.add_field(
            name="🛠️ Troubleshooting",
            value="**Common issues:**\n• `!echonetdiagnose` - checks permissions\n• If setup fails, check bot has Manage Channels permission\n• If menu disappears, run `!voice` again\n• Users need 'Connect' permission for voice channels",
            inline=False
        )
        
        embed.set_footer(text="EchoNet Bot - Need user help? Use !help user")
    else:
        # Show user help
        embed = discord.Embed(
            title="🎤 EchoNet Voice Channel Bot - User Guide",
            description="Create your own temporary voice channels with custom settings!",
            color=0x3498db
        )
        
        embed.add_field(
            name="🎮 How to Get Started",
            value="1. **Find the menu** - Look for the EchoNet menu in your server\n2. **Click 'Create Voice Channel'** - Green button to start\n3. **Choose settings** - Pick duration and access type\n4. **Manage your channel** - Use the management buttons",
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Channel Settings",
            value="**Duration:** 1 day to 2 months\n**Access Types:**\n• 🌐 **Open** - Anyone can join\n• 🔒 **Request Only** - Users must request access\n\n**User Limits:** Set max number of users (0-99)",
            inline=False
        )
        
        embed.add_field(
            name="🛠️ Managing Your Channel",
            value="**Owner Controls:**\n• Kick/invite users\n• Block/unblock users\n• Transfer ownership\n• Change access type\n• Extend duration\n• Set user limits\n• Delete channel early",
            inline=False
        )
        
        embed.add_field(
            name="🔐 Joining Private Channels",
            value="**For Request-Only channels:**\n1. Click '🔐 Join [Channel Name]' button\n2. Wait for owner approval\n3. You'll get a DM when approved/denied\n\n**Note:** Channel owners get DM notifications for requests",
            inline=False
        )
        
        embed.add_field(
            name="👤 User Commands",
            value="`!voice` - Open the main menu\n`!help` - Show this help message",
            inline=False
        )
        
        embed.add_field(
            name="💡 Tips",
            value="• Channels automatically delete when they expire\n• You can extend duration before expiration\n• Blocked users can't see or join your channel\n• Only channel owners can manage settings",
            inline=False
        )
        
        embed.set_footer(text="EchoNet Bot - Making voice channels easy!")
    
    await ctx.send(embed=embed)

if __name__ == "__main__":
    print("🚀 Starting EchoNet Discord bot...")
    try:
        bot.run(token)
    except Exception as e:
        print(f"❌ Bot failed to start: {e}")
        raise
        
