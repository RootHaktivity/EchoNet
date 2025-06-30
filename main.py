import discord
from discord.ext import commands, tasks
import asyncio
import datetime
import json
import os

intents = discord.Intents.default()
intents.guilds = True
intents.guild_messages = True
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")

temp_channels = {}

SETTINGS_FILE = "echonet_settings.json"
MAIN_MENU_TAG = "[EchoNet Main Menu]"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)

def load_data():
    global temp_channels
    if os.path.exists("channels.json"):
        try:
            with open("channels.json", "r") as f:
                data = json.load(f)
                for channel_id, info in data.items():
                    temp_channels[int(channel_id)] = {
                        "owner_id": info["owner_id"],
                        "expires_at": datetime.datetime.fromisoformat(info["expires_at"]),
                        "request_only": info["request_only"],
                        "pending_requests": info.get("pending_requests", []),
                        "menu_message_id": info.get("menu_message_id"),
                        "menu_channel_id": info.get("menu_channel_id"),
                        "blocked_users": info.get("blocked_users", [])
                    }
        except:
            temp_channels = {}

def save_data():
    data = {}
    for channel_id, info in temp_channels.items():
        data[str(channel_id)] = {
            "owner_id": info["owner_id"],
            "expires_at": info["expires_at"].isoformat(),
            "request_only": info["request_only"],
            "pending_requests": info.get("pending_requests", []),
            "menu_message_id": info.get("menu_message_id"),
            "menu_channel_id": info.get("menu_channel_id"),
            "blocked_users": info.get("blocked_users", [])
        }
    with open("channels.json", "w") as f:
        json.dump(data, f)

# --- Persistent Views ---

class ApproveDenyView(discord.ui.View):
    def __init__(self, cid=None, requester_id=None, guild_id=None, timeout=300):
        super().__init__(timeout=timeout)
        self.cid = cid
        self.requester_id = requester_id
        self.guild_id = guild_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, custom_id="approve_request")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cid or not self.requester_id or not self.guild_id:
            await interaction.response.send_message("❌ Could not process approval - missing information.")
            return
            
        guild = bot.get_guild(self.guild_id)
        if not guild:
            await interaction.response.send_message("❌ Could not find the server.")
            return
            
        channel = guild.get_channel(self.cid)
        requester = guild.get_member(self.requester_id)
        
        if not channel or not requester:
            await interaction.response.send_message("❌ Could not find channel or user.")
            return
            
        try:
            # Grant connect permission
            overwrites = channel.overwrites
            overwrites[requester] = discord.PermissionOverwrite(connect=True, view_channel=True)
            await channel.edit(overwrites=overwrites, reason="Approved join request")
            
            # Remove from pending
            if self.cid in temp_channels and self.requester_id in temp_channels[self.cid]["pending_requests"]:
                temp_channels[self.cid]["pending_requests"].remove(self.requester_id)
                save_data()
                
            await interaction.response.send_message(
                f"✅ You approved {requester.mention} to join **{channel.name}**."
            )
            
            try:
                await requester.send(f"✅ Your request to join **{channel.name}** was approved!")
            except:
                pass
                
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to edit this channel. Please ensure I have the 'Manage Channels' permission in the category and channel.")
        except Exception as e:
            await interaction.response.send_message(f"❌ Error processing approval: {str(e)}")

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, custom_id="deny_request")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cid or not self.requester_id or not self.guild_id:
            await interaction.response.send_message("❌ Could not process denial - missing information.")
            return
            
        guild = bot.get_guild(self.guild_id)
        if not guild:
            await interaction.response.send_message("❌ Could not find the server.")
            return
            
        channel = guild.get_channel(self.cid)
        requester = guild.get_member(self.requester_id)
        
        if not channel:
            await interaction.response.send_message("❌ Could not find channel.")
            return
            
        try:
            # Remove from pending
            if self.cid in temp_channels and self.requester_id in temp_channels[self.cid]["pending_requests"]:
                temp_channels[self.cid]["pending_requests"].remove(self.requester_id)
                save_data()
                
            requester_name = requester.mention if requester else f"User ID {self.requester_id}"
            await interaction.response.send_message(
                f"❌ You denied {requester_name}'s request to join **{channel.name}**."
            )
            
            if requester:
                try:
                    await requester.send(f"❌ Your request to join **{channel.name}** was denied.")
                except:
                    pass
                    
        except Exception as e:
            await interaction.response.send_message(f"❌ Error processing denial: {str(e)}")

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
            await channel.delete(reason="Time limit expired")
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
    # Register persistent views so buttons always work
    bot.add_view(MainMenu())
    bot.add_view(ApproveDenyView())
    print("🔄 Background tasks started")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    raise error

# --- Purge helper ---

async def purge_menu_text_channel(menu_text_channel):
    async for msg in menu_text_channel.history(limit=100):
        # Only keep the main menu message (by content tag)
        if not (msg.author == menu_text_channel.guild.me and msg.content.startswith(MAIN_MENU_TAG)):
            try:
                await msg.delete()
            except:
                pass

async def ensure_main_menu(menu_text_channel):
    # Check if the main menu is present, if not, post it
    found_main_menu = None
    async for msg in menu_text_channel.history(limit=20):
        if msg.author == menu_text_channel.guild.me and msg.content.startswith(MAIN_MENU_TAG):
            found_main_menu = msg
            break
    if not found_main_menu:
        embed = discord.Embed(
            title="🎤 Voice Channel Creator",
            description="Create your own temporary voice channel!",
            color=0x00ff00
        )
        embed.add_field(
            name="Features",
            value="• Custom duration\n• Access control\n• Channel management",
            inline=False
        )
        view = MainMenu()
        main_menu_msg = await menu_text_channel.send(f"{MAIN_MENU_TAG}", embed=embed, view=view)
        return main_menu_msg
    return found_main_menu

async def delete_management_menu_and_restore_main(menu_text_channel, management_msg, delay=300):
    await asyncio.sleep(delay)
    try:
        await management_msg.delete()
    except:
        pass
    # Purge all other messages except the main menu
    await purge_menu_text_channel(menu_text_channel)
    # Ensure main menu is present
    await ensure_main_menu(menu_text_channel)

# --- UI Classes ---

class MainMenu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view

    @discord.ui.button(label="🎤 Create Voice Channel", style=discord.ButtonStyle.green, emoji="🎤", custom_id="mainmenu_create")
    async def create_channel(self, interaction, button):
        settings = load_settings()
        guild_id = str(interaction.guild.id)
        if guild_id not in settings:
            await interaction.response.send_message(
                "❌ Setup not complete. Please ask an admin to run `!echonetsetup` first.",
                ephemeral=True
            )
            return

        category_id = settings[guild_id]["category_id"]
        text_channel_id = settings[guild_id]["text_channel_id"]
        category = interaction.guild.get_channel(category_id)
        text_channel = interaction.guild.get_channel(text_channel_id)

        if not category or not text_channel:
            await interaction.response.send_message(
                "❌ The saved category or text channel no longer exists. Please ask an admin to run `!echonetsetup` again.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="⏰ Channel Duration",
            description="How long should your voice channel last?",
            color=0x00ff00
        )
        view = DurationView(interaction.user.id, interaction.channel, category=category, menu_text_channel=text_channel)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🛠️ Manage My Channel", style=discord.ButtonStyle.blurple, emoji="🛠️", custom_id="mainmenu_manage")
    async def manage_channel(self, interaction, button):
        # Find the user's owned channels
        owned = [cid for cid, info in temp_channels.items() if info["owner_id"] == interaction.user.id]
        if not owned:
            await interaction.response.send_message("❌ You don't own any active voice channels.", ephemeral=True)
            return
        
        # If only one channel, manage it directly
        if len(owned) == 1:
            cid = owned[0]
            channel = interaction.guild.get_channel(cid)
            if not channel:
                await interaction.response.send_message("❌ Channel not found!", ephemeral=True)
                return
            embed = discord.Embed(
                title=f"Manage Channel: {channel.name}",
                description="Use the buttons below to manage your channel.",
                color=0x00ff00
            )
            view = ChannelActionsView(cid, interaction.user.id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            # Multiple channels - show list to pick from
            embed = discord.Embed(title="Select a Channel to Manage", color=0x00ff00)
            channel_options = []
            for cid in owned:
                channel = interaction.guild.get_channel(cid)
                if channel:
                    embed.add_field(name=channel.name, value=f"ID: {cid}", inline=False)
                    channel_options.append((channel.name, cid))
            
            if not channel_options:
                await interaction.response.send_message("❌ None of your channels were found!", ephemeral=True)
                return
                
            view = SelectChannelView(interaction.user.id, channel_options)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="📋 List Channels", style=discord.ButtonStyle.primary, emoji="📋", custom_id="mainmenu_list")
    async def list_channels(self, interaction, button):
        view = ListChannelsView(interaction.user.id)
        await view.send_channel_list(interaction)

class SelectChannelView(discord.ui.View):
    def __init__(self, user_id, channel_options):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.channel_options = channel_options
        
        # Create select menu
        options = []
        for name, cid in channel_options[:25]:  # Discord limit of 25 options
            options.append(discord.SelectOption(label=name, value=str(cid)))
        
        select = discord.ui.Select(placeholder="Choose a channel to manage...", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def select_callback(self, interaction: discord.Interaction):
        cid = int(interaction.data['values'][0])
        channel = interaction.guild.get_channel(cid)
        if not channel:
            await interaction.response.send_message("❌ Channel not found!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"Manage Channel: {channel.name}",
            description="Use the buttons below to manage your channel.",
            color=0x00ff00
        )
        view = ChannelActionsView(cid, self.user_id)
        await interaction.response.edit_message(embed=embed, view=view)

class DurationView(discord.ui.View):
    def __init__(self, user_id, channel, category=None, menu_text_channel=None):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.channel = channel
        self.category = category
        self.menu_text_channel = menu_text_channel
        self.days = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="1 Day", style=discord.ButtonStyle.green)
    async def one_day(self, interaction, button):
        self.days = 1
        await self.show_access_menu(interaction)

    @discord.ui.button(label="1 Week", style=discord.ButtonStyle.blurple)
    async def one_week(self, interaction, button):
        self.days = 7
        await self.show_access_menu(interaction)

    @discord.ui.button(label="2 Weeks", style=discord.ButtonStyle.blurple)
    async def two_weeks(self, interaction, button):
        self.days = 14
        await self.show_access_menu(interaction)

    @discord.ui.button(label="Custom", style=discord.ButtonStyle.gray)
    async def custom_duration(self, interaction, button):
        await interaction.response.send_message("Please type the number of days (1-60 max):", ephemeral=True)

        def check(m):
            return m.author.id == self.user_id and m.channel == self.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=30)
            try:
                days = int(msg.content)
                if days < 1 or days > 60:
                    await interaction.followup.send("❌ Please enter a number between 1 and 60 days!", ephemeral=True)
                    return

                self.days = days
                embed = discord.Embed(
                    title="🔐 Channel Access Type",
                    description="Who can join your channel?",
                    color=0x00ff00
                )
                view = AccessTypeView(self.user_id, self.days, self.channel, self.category, self.menu_text_channel)
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            except ValueError:
                await interaction.followup.send("❌ Please enter a valid number!", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timed out! Please try again.", ephemeral=True)

    async def show_access_menu(self, interaction):
        embed = discord.Embed(
            title="🔐 Channel Access Type",
            description="Who can join your channel?",
            color=0x00ff00
        )
        view = AccessTypeView(self.user_id, self.days, self.channel, self.category, self.menu_text_channel)
        await interaction.response.edit_message(embed=embed, view=view)

class AccessTypeView(discord.ui.View):
    def __init__(self, user_id, days, channel, category=None, menu_text_channel=None):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.days = days
        self.channel = channel
        self.category = category
        self.menu_text_channel = menu_text_channel

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="🌐 Open (Anyone can join)", style=discord.ButtonStyle.green)
    async def open_access(self, interaction, button):
        await self.ask_channel_name(interaction, request_only=False)

    @discord.ui.button(label="🔒 Request Only", style=discord.ButtonStyle.red)
    async def request_access(self, interaction, button):
        await self.ask_channel_name(interaction, request_only=True)

    async def ask_channel_name(self, interaction, request_only):
        await interaction.response.send_message("Please type the name you want for your voice channel (1-100 characters):", ephemeral=True)

        def check(m):
            return m.author.id == self.user_id and m.channel == self.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            channel_name = msg.content.strip()
            if not (1 <= len(channel_name) <= 100):
                await interaction.followup.send("❌ Channel name must be between 1 and 100 characters!", ephemeral=True)
                return
            await self.create_channel(interaction, request_only, channel_name)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timed out! Please try again.", ephemeral=True)

    async def create_channel(self, interaction, request_only, channel_name):
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=self.days)
        guild = interaction.guild
        user = interaction.user

        category = self.category
        if not category:
            await interaction.followup.send("❌ No category set. Please ask an admin to run `!echonetsetup`.", ephemeral=True)
            return

        if request_only:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True),
                user: discord.PermissionOverwrite(manage_channels=True, connect=True, view_channel=True)
            }
        else:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                user: discord.PermissionOverwrite(manage_channels=True, connect=True, view_channel=True)
            }

        bot_member = guild.me
        overwrites[bot_member] = discord.PermissionOverwrite(manage_channels=True, view_channel=True, connect=True)

        try:
            channel = await guild.create_voice_channel(
                name=channel_name,
                overwrites=overwrites,
                category=category,
                reason="User-created custom voice channel"
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to create channels in that category. Please ensure I have the 'Manage Channels' permission.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"❌ Error creating channel: {str(e)}", ephemeral=True)
            return

        menu_text_channel = self.menu_text_channel
        if not menu_text_channel:
            await interaction.followup.send("❌ Could not find the menu text channel! Please ask an admin to run `!echonetsetup`.", ephemeral=True)
            return

        # Purge all messages except the main menu
        await purge_menu_text_channel(menu_text_channel)

        access_type = "🔒 Request Only" if request_only else "🌐 Open"
        embed = discord.Embed(
            title="✅ Voice Channel Created!",
            description=f"Channel <#{channel.id}> has been created by {user.mention}",
            color=0x00ff00
        )
        embed.add_field(name="Channel Name", value=channel_name, inline=True)
        embed.add_field(name="Duration", value=f"{self.days} day(s)", inline=True)
        embed.add_field(name="Access Type", value=access_type, inline=True)
        embed.add_field(name="Owner", value=user.mention, inline=True)
        embed.add_field(name="Channel ID", value=str(channel.id), inline=False)

        view = ChannelActionsView(channel.id, user.id)
        menu_message = await menu_text_channel.send(embed=embed, view=view)

        await interaction.followup.send(f"✅ Your voice channel **{channel_name}** has been created! Check <#{menu_text_channel.id}> to manage it.", ephemeral=True)

        temp_channels[channel.id] = {
            "owner_id": user.id,
            "expires_at": expires_at,
            "request_only": request_only,
            "pending_requests": [],
            "menu_message_id": menu_message.id,
            "menu_channel_id": menu_text_channel.id,
            "blocked_users": []
        }
        save_data()

        # Schedule deletion of the management menu and re-post the main menu if needed
        bot.loop.create_task(delete_management_menu_and_restore_main(menu_text_channel, menu_message))

class ChannelActionsView(discord.ui.View):
    def __init__(self, channel_id, owner_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @discord.ui.button(label="🗑️ Delete Channel", style=discord.ButtonStyle.danger)
    async def delete_channel(self, interaction, button):
        try:
            channel = interaction.guild.get_channel(self.channel_id)
            if channel:
                await channel.delete(reason="Deleted by owner via button")
                await interaction.response.send_message("✅ Your voice channel has been deleted!", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Channel not found (may already be deleted).", ephemeral=True)

            info = temp_channels.get(self.channel_id)
            if info and "menu_message_id" in info and "menu_channel_id" in info:
                menu_channel = bot.get_channel(info["menu_channel_id"])
                if menu_channel:
                    try:
                        menu_msg = await menu_channel.fetch_message(info["menu_message_id"])
                        await menu_msg.delete()
                    except Exception:
                        pass

            if self.channel_id in temp_channels:
                del temp_channels[self.channel_id]
                save_data()
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to delete channel: {str(e)}", ephemeral=True)

    @discord.ui.button(label="✏️ Edit Channel", style=discord.ButtonStyle.secondary)
    async def edit_channel(self, interaction, button):
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Channel not found!", ephemeral=True)
            return

        embed = discord.Embed(
            title="✏️ Edit Channel Options",
            description=f"What would you like to edit for **{channel.name}**?",
            color=0x0099ff
        )
        view = EditChannelView(self.channel_id, self.owner_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class EditChannelView(discord.ui.View):
    def __init__(self, channel_id, owner_id):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @discord.ui.button(label="📝 Rename Channel", style=discord.ButtonStyle.primary)
    async def rename_channel(self, interaction, button):
        await interaction.response.send_message("Please type the new name for your channel (1-100 characters):", ephemeral=True)

        def check(m):
            return m.author.id == self.owner_id and m.channel == interaction.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            new_name = msg.content.strip()
            if not (1 <= len(new_name) <= 100):
                await interaction.followup.send("❌ Channel name must be between 1 and 100 characters!", ephemeral=True)
                return

            channel = interaction.guild.get_channel(self.channel_id)
            if channel:
                await channel.edit(name=new_name, reason="Renamed by owner")
                await interaction.followup.send(f"✅ Channel renamed to **{new_name}**!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Channel not found!", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timed out! Please try again.", ephemeral=True)

    @discord.ui.button(label="⏰ Change Duration", style=discord.ButtonStyle.primary)
    async def change_duration(self, interaction, button):
        await interaction.response.send_message("Please type the new duration in days (1-60 max):", ephemeral=True)

        def check(m):
            return m.author.id == self.owner_id and m.channel == interaction.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            try:
                days = int(msg.content)
                if days < 1 or days > 60:
                    await interaction.followup.send("❌ Please enter a number between 1 and 60 days!", ephemeral=True)
                    return

                new_expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=days)
                if self.channel_id in temp_channels:
                    temp_channels[self.channel_id]["expires_at"] = new_expires_at
                    save_data()
                    await interaction.followup.send(f"✅ Channel duration changed to {days} day(s)!", ephemeral=True)
                else:
                    await interaction.followup.send("❌ Channel info not found!", ephemeral=True)
            except ValueError:
                await interaction.followup.send("❌ Please enter a valid number!", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timed out! Please try again.", ephemeral=True)

    @discord.ui.button(label="🔐 Change Access Type", style=discord.ButtonStyle.primary)
    async def change_access_type(self, interaction, button):
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel info not found!", ephemeral=True)
            return

        current_request_only = temp_channels[self.channel_id]["request_only"]
        new_request_only = not current_request_only
        
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Channel not found!", ephemeral=True)
            return

        guild = interaction.guild
        user = interaction.user

        if new_request_only:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True),
                user: discord.PermissionOverwrite(manage_channels=True, connect=True, view_channel=True)
            }
            access_type = "🔒 Request Only"
        else:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                user: discord.PermissionOverwrite(manage_channels=True, connect=True, view_channel=True)
            }
            access_type = "🌐 Open"

        bot_member = guild.me
        overwrites[bot_member] = discord.PermissionOverwrite(manage_channels=True, view_channel=True, connect=True)

        try:
            await channel.edit(overwrites=overwrites, reason="Access type changed by owner")
            temp_channels[self.channel_id]["request_only"] = new_request_only
            save_data()
            await interaction.response.send_message(f"✅ Channel access changed to **{access_type}**!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to edit this channel.", ephemeral=True)

    @discord.ui.button(label="🚫 Manage Blocked Users", style=discord.ButtonStyle.secondary)
    async def manage_blocked_users(self, interaction, button):
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel info not found!", ephemeral=True)
            return

        blocked_users = temp_channels[self.channel_id]["blocked_users"]
        
        embed = discord.Embed(
            title="🚫 Blocked Users Management",
            description="Choose an action:",
            color=0xff0000
        )
        
        if blocked_users:
            blocked_mentions = []
            for user_id in blocked_users:
                user = interaction.guild.get_member(user_id)
                if user:
                    blocked_mentions.append(user.mention)
            if blocked_mentions:
                embed.add_field(name="Currently Blocked", value="\n".join(blocked_mentions), inline=False)

        view = BlockedUsersView(self.channel_id, self.owner_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="👑 Transfer Ownership", style=discord.ButtonStyle.secondary)
    async def transfer_ownership(self, interaction, button):
        await interaction.response.send_message("Please mention the user you want to transfer ownership to:", ephemeral=True)

        def check(m):
            return m.author.id == self.owner_id and m.channel == interaction.channel and m.mentions

        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            new_owner = msg.mentions[0]
            
            if new_owner.id == self.owner_id:
                await interaction.followup.send("❌ You're already the owner!", ephemeral=True)
                return

            if new_owner.bot:
                await interaction.followup.send("❌ Cannot transfer ownership to a bot!", ephemeral=True)
                return

            channel = interaction.guild.get_channel(self.channel_id)
            if not channel:
                await interaction.followup.send("❌ Channel not found!", ephemeral=True)
                return

            # Update permissions
            overwrites = channel.overwrites
            old_owner = interaction.guild.get_member(self.owner_id)
            if old_owner:
                overwrites[old_owner] = discord.PermissionOverwrite(connect=True, view_channel=True)
            overwrites[new_owner] = discord.PermissionOverwrite(manage_channels=True, connect=True, view_channel=True)
            
            await channel.edit(overwrites=overwrites, reason="Ownership transferred")
            
            if self.channel_id in temp_channels:
                temp_channels[self.channel_id]["owner_id"] = new_owner.id
                save_data()

            await interaction.followup.send(f"✅ Channel ownership transferred to {new_owner.mention}!", ephemeral=True)
            try:
                await new_owner.send(f"🎉 You are now the owner of voice channel **{channel.name}**!")
            except:
                pass
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timed out! Please try again.", ephemeral=True)

    @discord.ui.button(label="👥 Change User Limit", style=discord.ButtonStyle.secondary)
    async def change_user_limit(self, interaction, button):
        await interaction.response.send_message("Please type the new user limit (0 for unlimited, max 99):", ephemeral=True)

        def check(m):
            return m.author.id == self.owner_id and m.channel == interaction.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            try:
                limit = int(msg.content)
                if limit < 0 or limit > 99:
                    await interaction.followup.send("❌ Please enter a number between 0 and 99!", ephemeral=True)
                    return

                channel = interaction.guild.get_channel(self.channel_id)
                if channel:
                    await channel.edit(user_limit=limit, reason="User limit changed by owner")
                    limit_text = "unlimited" if limit == 0 else str(limit)
                    await interaction.followup.send(f"✅ User limit changed to **{limit_text}**!", ephemeral=True)
                else:
                    await interaction.followup.send("❌ Channel not found!", ephemeral=True)
            except ValueError:
                await interaction.followup.send("❌ Please enter a valid number!", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timed out! Please try again.", ephemeral=True)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content="❌ Edit cancelled.", embed=None, view=None)

class BlockedUsersView(discord.ui.View):
    def __init__(self, channel_id, owner_id):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @discord.ui.button(label="➕ Block User", style=discord.ButtonStyle.red)
    async def block_user(self, interaction, button):
        await interaction.response.send_message("Please mention the user you want to block:", ephemeral=True)

        def check(m):
            return m.author.id == self.owner_id and m.channel == interaction.channel and m.mentions

        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            user_to_block = msg.mentions[0]
            
            if user_to_block.id == self.owner_id:
                await interaction.followup.send("❌ You cannot block yourself!", ephemeral=True)
                return

            if user_to_block.bot:
                await interaction.followup.send("❌ Cannot block bots!", ephemeral=True)
                return

            if self.channel_id not in temp_channels:
                await interaction.followup.send("❌ Channel info not found!", ephemeral=True)
                return

            blocked_users = temp_channels[self.channel_id]["blocked_users"]
            if user_to_block.id in blocked_users:
                await interaction.followup.send("❌ User is already blocked!", ephemeral=True)
                return

            channel = interaction.guild.get_channel(self.channel_id)
            if channel:
                overwrites = channel.overwrites
                overwrites[user_to_block] = discord.PermissionOverwrite(connect=False, view_channel=True)
                await channel.edit(overwrites=overwrites, reason="User blocked by owner")
                
                # Disconnect user if they're in the channel
                if user_to_block.voice and user_to_block.voice.channel == channel:
                    await user_to_block.move_to(None, reason="Blocked by channel owner")

            blocked_users.append(user_to_block.id)
            save_data()
            await interaction.followup.send(f"✅ {user_to_block.mention} has been blocked!", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timed out! Please try again.", ephemeral=True)

    @discord.ui.button(label="➖ Unblock User", style=discord.ButtonStyle.green)
    async def unblock_user(self, interaction, button):
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel info not found!", ephemeral=True)
            return

        blocked_users = temp_channels[self.channel_id]["blocked_users"]
        if not blocked_users:
            await interaction.response.send_message("❌ No users are currently blocked!", ephemeral=True)
            return

        await interaction.response.send_message("Please mention the user you want to unblock:", ephemeral=True)

        def check(m):
            return m.author.id == self.owner_id and m.channel == interaction.channel and m.mentions

        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            user_to_unblock = msg.mentions[0]
            
            if user_to_unblock.id not in blocked_users:
                await interaction.followup.send("❌ User is not blocked!", ephemeral=True)
                return

            channel = interaction.guild.get_channel(self.channel_id)
            if channel:
                overwrites = channel.overwrites
                if user_to_unblock in overwrites:
                    del overwrites[user_to_unblock]
                    await channel.edit(overwrites=overwrites, reason="User unblocked by owner")

            blocked_users.remove(user_to_unblock.id)
            save_data()
            await interaction.followup.send(f"✅ {user_to_unblock.mention} has been unblocked!", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timed out! Please try again.", ephemeral=True)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content="❌ Cancelled.", embed=None, view=None)

class ListChannelsView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Closed.", embed=None, view=None)

    async def send_channel_list(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = discord.Embed(title="Active Voice Channels", color=0x00ff00)
        
        if not temp_channels:
            embed.description = "No active voice channels found."
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        view = discord.ui.View(timeout=120)
        channel_count = 0

        for channel_id, info in temp_channels.items():
            channel = guild.get_channel(channel_id)
            if not channel:
                continue
            owner = guild.get_member(info["owner_id"])
            if not owner:
                continue

            channel_count += 1
            access_type = "🔒 Request Only" if info["request_only"] else "🌐 Open"
            embed.add_field(
                name=f"{channel.name}",
                value=f"Owner: {owner.mention}\nAccess: {access_type}\nUsers: {len(channel.members)}/{channel.user_limit or '∞'}",
                inline=False
            )

            if info["request_only"]:
                button = discord.ui.Button(label=f"Request to Join {channel.name}", style=discord.ButtonStyle.blurple)
                async def request_callback(interact, cid=channel_id, owner_id=info["owner_id"]):
                    if interact.user.id == owner_id:
                        await interact.response.send_message("You are the owner of this channel!", ephemeral=True)
                        return
                    channel_info = temp_channels.get(cid)
                    if not channel_info:
                        await interact.response.send_message("Channel info not found!", ephemeral=True)
                        return
                    if interact.user.id in channel_info["pending_requests"]:
                        await interact.response.send_message("You already have a pending request!", ephemeral=True)
                        return
                    if interact.user.id in channel_info["blocked_users"]:
                        await interact.response.send_message("You are blocked from this channel!", ephemeral=True)
                        return
                    channel_info["pending_requests"].append(interact.user.id)
                    save_data()
                    owner_member = interact.guild.get_member(owner_id)
                    requester = interact.user

                    if owner_member:
                        try:
                            channel = interact.guild.get_channel(cid)
                            await owner_member.send(
                                f"{requester.mention} wants to join your voice channel **{channel.name}**.",
                                view=ApproveDenyView(cid=cid, requester_id=requester.id, guild_id=interact.guild.id)
                            )
                            await interact.response.send_message("Request sent to the channel owner!", ephemeral=True)
                        except Exception:
                            await interact.response.send_message("Could not DM the channel owner.", ephemeral=True)
                    else:
                        await interact.response.send_message("Channel owner not found!", ephemeral=True)
                button.callback = request_callback
            else:
                button = discord.ui.Button(label=f"Join {channel.name}", style=discord.ButtonStyle.green)
                async def join_callback(interact, ch=channel, cid=channel_id):
                    if interact.user.voice and interact.user.voice.channel == ch:
                        await interact.response.send_message("You are already in this channel!", ephemeral=True)
                        return
                    channel_info = temp_channels.get(cid)
                    if channel_info and interact.user.id in channel_info["blocked_users"]:
                        await interact.response.send_message("You are blocked from this channel!", ephemeral=True)
                        return
                    try:
                        await interact.user.move_to(ch)
                        await interact.response.send_message(f"Moved you to {ch.name}!", ephemeral=True)
                    except Exception:
                        await interact.response.send_message(f"Could not move you to {ch.name}. Please join manually.", ephemeral=True)
                button.callback = join_callback

            view.add_item(button)

        if channel_count == 0:
            embed.description = "No active voice channels found."

        view.add_item(self.children[0])  # Add the close button
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# --- Commands ---

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

    # Purge all messages except the main menu
    await purge_menu_text_channel(menu_text_channel)

    # Ensure main menu is present
    await ensure_main_menu(menu_text_channel)
    await ctx.send(f"✅ Main menu is ready in <#{menu_text_channel.id}>.")

@bot.command(name="echonetsetup")
@commands.has_permissions(manage_channels=True)
async def echonetsetup_command(ctx):
    def check_author(m):
        return m.author == ctx.author and m.channel == ctx.channel

    guild = ctx.guild

    # Step 1: Pick category for new voice channels
    categories = [c for c in guild.categories]
    if not categories:
        await ctx.send("❌ No categories found. Please create a category first.")
        return

    category_list = "\n".join(f"{i+1}. {c.name}" for i, c in enumerate(categories))
    await ctx.send(f"Please type the number of the category to use for new voice channels:\n{category_list}")

    try:
        cat_msg = await bot.wait_for("message", check=check_author, timeout=60)
        cat_idx = int(cat_msg.content.strip()) - 1
        if cat_idx < 0 or cat_idx >= len(categories):
            await ctx.send("❌ Invalid selection.")
            return
        category = categories[cat_idx]
    except (ValueError, asyncio.TimeoutError):
        await ctx.send("❌ Invalid or timed out. Please try again.")
        return

    # Step 2: Pick text channel for menu
    text_channels = [ch for ch in guild.text_channels]
    if not text_channels:
        await ctx.send("❌ No text channels found. Please create one first.")
        return

    text_list = "\n".join(f"{i+1}. {ch.name}" for i, ch in enumerate(text_channels))
    await ctx.send(f"Please type the number of the text channel to use for the menu:\n{text_list}")

    try:
        txt_msg = await bot.wait_for("message", check=check_author, timeout=60)
        txt_idx = int(txt_msg.content.strip()) - 1
        if txt_idx < 0 or txt_idx >= len(text_channels):
            await ctx.send("❌ Invalid selection.")
            return
        text_channel = text_channels[txt_idx]
    except (ValueError, asyncio.TimeoutError):
        await ctx.send("❌ Invalid or timed out. Please try again.")
        return

    # Save settings
    settings = load_settings()
    settings[str(guild.id)] = {
        "category_id": category.id,
        "text_channel_id": text_channel.id
    }
    save_settings(settings)
    await ctx.send(f"✅ Setup complete! New voice channels will be created in **{category.name}**, and the menu will be posted in **{text_channel.name}**.")

@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="🤖 Bot Commands",
        description="Here are the available commands:",
        color=0x0099ff
    )
    embed.add_field(name="!voice", value="Show the main menu in the configured text channel", inline=False)
    embed.add_field(name="!echonetsetup", value="Set the default category and menu text channel (admin only)", inline=False)
    embed.add_field(name="!help", value="Show this help message", inline=False)
    await ctx.send(embed=embed)

bot.run(os.getenv("BOT_TOKEN"))
