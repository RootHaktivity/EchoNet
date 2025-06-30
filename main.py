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
intents.members = True  # Required for member info and kicking

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")

temp_channels = {}

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

@tasks.loop(minutes=5)
async def refresh_vc_menu():
    for guild in bot.guilds:
        vc_menu_channel = discord.utils.get(guild.text_channels, name="vc-menu")
        if vc_menu_channel:
            try:
                async for msg in vc_menu_channel.history(limit=100):
                    if not msg.pinned:
                        await msg.delete()
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
                await vc_menu_channel.send(embed=embed, view=MainMenu(None, vc_menu_channel))
            except Exception:
                pass

@bot.event
async def on_ready():
    print(f"✅ Bot logged in as {bot.user}")
    load_data()
    check_expired_channels.start()
    refresh_vc_menu.start()
    print("🔄 Background tasks started")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    raise error

# --- Class Definitions in correct order ---

class ChannelActionsView(discord.ui.View):
    def __init__(self, channel_id, owner_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.owner_id = owner_id

    @discord.ui.button(label="🗑️ Delete Channel", style=discord.ButtonStyle.danger)
    async def delete_channel(self, interaction, button):  # Fixed parameter order
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Only the channel owner can delete it!", ephemeral=True)
            return

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
    async def edit_channel(self, interaction, button):  # Fixed parameter order
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Only the channel owner can edit it!", ephemeral=True)
            return

        embed = discord.Embed(
            title="✏️ Edit Channel",
            description="What would you like to edit?",
            color=0x0099ff
        )
        view = EditChannelView(self.channel_id, self.owner_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="📋 List Channels", style=discord.ButtonStyle.primary)
    async def list_channels(self, interaction, button):  # Fixed parameter order
        view = ListChannelsView(interaction.user.id)
        await view.send_channel_list(interaction)

    @discord.ui.button(label="🎤 Create Voice Channel", style=discord.ButtonStyle.green)
    async def create_voice_channel(self, interaction, button):  # Fixed parameter order
        embed = discord.Embed(
            title="🎤 Voice Channel Creator",
            description="Create your own temporary voice channel!",
            color=0x00ff00
        )
        view = MainMenu(interaction.user.id, interaction.channel)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="👥 Manage Users", style=discord.ButtonStyle.secondary)
    async def manage_users(self, interaction, button):  # Fixed parameter order
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Only the channel owner can manage users!", ephemeral=True)
            return

        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Your voice channel was not found!", ephemeral=True)
            return

        members = [m for m in channel.members if m.id != self.owner_id]
        if not members:
            await interaction.response.send_message("ℹ️ No other users in your voice channel.", ephemeral=True)
            return

        view = ManageUsersView(self.channel_id, self.owner_id, members)
        embed = discord.Embed(title="Manage Users", description="Select a user to kick or block/unblock.", color=0x00ff00)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ManageUsersView(discord.ui.View):
    def __init__(self, channel_id, owner_id, members):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        self.owner_id = owner_id
        self.members = members

        options = [discord.SelectOption(label=m.display_name, value=str(m.id)) for m in members]
        self.user_select = discord.ui.Select(placeholder="Select a user", options=options, min_values=1, max_values=1)
        self.user_select.callback = self.user_selected
        self.add_item(self.user_select)

    async def user_selected(self, interaction: discord.Interaction):
        user_id = int(self.user_select.values[0])
        member = interaction.guild.get_member(user_id)
        if not member:
            await interaction.response.send_message("❌ User not found.", ephemeral=True)
            return

        view = UserActionView(self.channel_id, self.owner_id, member)
        embed = discord.Embed(title=f"Manage {member.display_name}", color=0x00ff00)
        await interaction.response.edit_message(embed=embed, view=view)

class UserActionView(discord.ui.View):
    def __init__(self, channel_id, owner_id, member):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        self.owner_id = owner_id
        self.member = member

    @discord.ui.button(label="Kick User", style=discord.ButtonStyle.danger)
    async def kick_user(self, interaction, button):  # Fixed parameter order
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Only the channel owner can kick users!", ephemeral=True)
            return

        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Voice channel not found!", ephemeral=True)
            return

        if self.member not in channel.members:
            await interaction.response.send_message("❌ User is not in your voice channel.", ephemeral=True)
            return

        try:
            await self.member.move_to(None)
            await interaction.response.send_message(f"✅ Kicked {self.member.display_name} from the voice channel.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to kick user: {e}", ephemeral=True)

    @discord.ui.button(label="Block User", style=discord.ButtonStyle.red)
    async def block_user(self, interaction, button):  # Fixed parameter order
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Only the channel owner can block users!", ephemeral=True)
            return

        channel_info = temp_channels.get(self.channel_id)
        if not channel_info:
            await interaction.response.send_message("❌ Channel info not found!", ephemeral=True)
            return

        if self.member.id in channel_info.get("blocked_users", []):
            await interaction.response.send_message(f"ℹ️ {self.member.display_name} is already blocked.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Voice channel not found!", ephemeral=True)
            return

        await channel.set_permissions(self.member, connect=False)
        channel_info.setdefault("blocked_users", []).append(self.member.id)
        save_data()
        await interaction.response.send_message(f"✅ Blocked {self.member.display_name} from joining the voice channel.", ephemeral=True)

    @discord.ui.button(label="Unblock User", style=discord.ButtonStyle.green)
    async def unblock_user(self, interaction, button):  # Fixed parameter order
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Only the channel owner can unblock users!", ephemeral=True)
            return

        channel_info = temp_channels.get(self.channel_id)
        if not channel_info:
            await interaction.response.send_message("❌ Channel info not found!", ephemeral=True)
            return

        if self.member.id not in channel_info.get("blocked_users", []):
            await interaction.response.send_message(f"ℹ️ {self.member.display_name} is not blocked.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Voice channel not found!", ephemeral=True)
            return

        await channel.set_permissions(self.member, overwrite=None)
        channel_info["blocked_users"].remove(self.member.id)
        save_data()
        await interaction.response.send_message(f"✅ Unblocked {self.member.display_name}.", ephemeral=True)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def go_back(self, interaction, button):  # Fixed parameter order
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Voice channel not found!", ephemeral=True)
            return

        members = [m for m in channel.members if m.id != self.owner_id]
        view = ManageUsersView(self.channel_id, self.owner_id, members)
        embed = discord.Embed(title="Manage Users", description="Select a user to kick or block/unblock.", color=0x00ff00)
        await interaction.response.edit_message(embed=embed, view=view)

class EditChannelView(discord.ui.View):
    def __init__(self, channel_id, owner_id):
        super().__init__(timeout=60)
        self.channel_id = channel_id
        self.owner_id = owner_id

    @discord.ui.button(label="📝 Change Name", style=discord.ButtonStyle.secondary)
    async def change_name(self, interaction, button):  # Fixed parameter order
        await interaction.response.send_message("Please type the new name for your channel:", ephemeral=True)

        def check(m):
            return m.author.id == self.owner_id and isinstance(m.channel, discord.DMChannel)

        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            new_name = msg.content.strip()
            if not (1 <= len(new_name) <= 100):
                await msg.channel.send("❌ Channel name must be between 1 and 100 characters!")
                return

            channel = bot.get_channel(self.channel_id)
            if channel:
                await channel.edit(name=new_name)
                await msg.channel.send(f"✅ Channel name changed to: **{new_name}**")
            else:
                await msg.channel.send("❌ Channel not found!")
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timed out! Please try again.", ephemeral=True)

    @discord.ui.button(label="🔄 Toggle Access", style=discord.ButtonStyle.secondary)
    async def toggle_access(self, interaction, button):  # Fixed parameter order
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found!", ephemeral=True)
            return

        channel_info = temp_channels[self.channel_id]
        channel = bot.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Channel not found!", ephemeral=True)
            return

        guild = channel.guild
        current_access = "Request Only" if channel_info["request_only"] else "Open"
        new_access_request_only = not channel_info["request_only"]
        new_access = "Request Only" if new_access_request_only else "Open"

        if new_access_request_only:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True),
                guild.get_member(self.owner_id): discord.PermissionOverwrite(manage_channels=True, connect=True, view_channel=True),
                guild.me: discord.PermissionOverwrite(manage_channels=True, view_channel=True, connect=True)
            }
        else:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                guild.get_member(self.owner_id): discord.PermissionOverwrite(manage_channels=True, connect=True, view_channel=True),
                guild.me: discord.PermissionOverwrite(manage_channels=True, view_channel=True, connect=True)
            }

        await channel.edit(overwrites=overwrites)
        channel_info["request_only"] = new_access_request_only
        save_data()

        await interaction.response.send_message(f"✅ Access changed from **{current_access}** to **{new_access}**!", ephemeral=True)

class ApprovalView(discord.ui.View):
    def __init__(self, channel_id, requester_id):
        super().__init__(timeout=300)
        self.channel_id = channel_id
        self.requester_id = requester_id

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction, button):  # Fixed parameter order
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found!", ephemeral=True)
            return

        channel_info = temp_channels[self.channel_id]
        if self.requester_id in channel_info["pending_requests"]:
            channel_info["pending_requests"].remove(self.requester_id)

        channel = bot.get_channel(self.channel_id)
        if channel:
            requester = interaction.guild.get_member(self.requester_id)
            if requester:
                await channel.set_permissions(requester, connect=True, view_channel=True)
                await interaction.response.send_message(f"✅ Approved {requester.mention} to join the channel!", ephemeral=True)
                try:
                    await requester.send(f"✅ Your request to join **{channel.name}** has been approved!")
                except:
                    pass
            else:
                await interaction.response.send_message("❌ Requester not found!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Channel not found!", ephemeral=True)

        save_data()

    @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction, button):  # Fixed parameter order
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found!", ephemeral=True)
            return

        channel_info = temp_channels[self.channel_id]
        if self.requester_id in channel_info["pending_requests"]:
            channel_info["pending_requests"].remove(self.requester_id)

        requester = interaction.guild.get_member(self.requester_id)
        if requester:
            await interaction.response.send_message(f"❌ Denied {requester.mention}'s request.", ephemeral=True)
            try:
                channel = bot.get_channel(self.channel_id)
                channel_name = channel.name if channel else "the channel"
                await requester.send(f"❌ Your request to join **{channel_name}** has been denied.")
            except:
                pass
        else:
            await interaction.response.send_message("❌ Requester not found!", ephemeral=True)

        save_data()

class ListChannelsView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):  # Fixed parameter order
        await interaction.message.delete()

    async def send_channel_list(self, interaction: discord.Interaction):
        guild = interaction.guild
        view = discord.ui.View(timeout=120)
        embed = discord.Embed(title="Active Voice Channels", color=0x00ff00)

        for channel_id, info in temp_channels.items():
            channel = guild.get_channel(channel_id)
            if not channel:
                continue
            owner = guild.get_member(info["owner_id"])
            if not owner:
                continue

            embed.add_field(name=channel.name, value=f"Owner: {owner.mention}", inline=False)

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
                    channel_info["pending_requests"].append(interact.user.id)
                    save_data()
                    owner_member = interact.guild.get_member(owner_id)
                    if owner_member:
                        embed_req = discord.Embed(
                            title="🚪 Join Request",
                            description=f"{interact.user.mention} wants to join your voice channel!",
                            color=0x0099ff
                        )
                        view_req = ApprovalView(cid, interact.user.id)
                        try:
                            await owner_member.send(embed=embed_req, view=view_req)
                            await interact.response.send_message("Request sent to the channel owner!", ephemeral=True)
                        except:
                            await interact.response.send_message("Couldn't send request to owner!", ephemeral=True)
                    else:
                        await interact.response.send_message("Channel owner not found!", ephemeral=True)
                button.callback = request_callback
            else:
                button = discord.ui.Button(label=f"Join {channel.name}", style=discord.ButtonStyle.green)
                async def join_callback(interact, ch=channel):
                    if interact.user.voice and interact.user.voice.channel == ch:
                        await interact.response.send_message("You are already in this channel!", ephemeral=True)
                        return
                    try:
                        await interact.user.move_to(ch)
                        await interact.response.send_message(f"Moved you to {ch.name}!", ephemeral=True)
                    except Exception:
                        await interact.response.send_message(f"Could not move you to {ch.name}. Please join manually.", ephemeral=True)
                button.callback = join_callback

            view.add_item(button)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class MainMenu(discord.ui.View):
    def __init__(self, user_id, channel):
        super().__init__(timeout=60)
        self.user_id = user_id  # None means public menu
        self.channel = channel

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # If user_id is None, allow all users to interact
        if self.user_id is None:
            return True
        return interaction.user.id == self.user_id

    @discord.ui.button(label="🎤 Create Voice Channel", style=discord.ButtonStyle.green, emoji="🎤")
    async def create_channel(self, interaction, button):  # Fixed parameter order
        if self.user_id is not None and interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your menu!", ephemeral=True)
            return

        embed = discord.Embed(
            title="⏰ Channel Duration",
            description="How long should your voice channel last?",
            color=0x00ff00
        )
        view = DurationView(interaction.user.id, interaction.channel)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="📋 List Channels", style=discord.ButtonStyle.primary)
    async def list_channels(self, interaction, button):  # Fixed parameter order
        if self.user_id is not None and interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your menu!", ephemeral=True)
            return
        view = ListChannelsView(interaction.user.id)
        await view.send_channel_list(interaction)

class CategoryTextChannelSelectView(discord.ui.View):
    def __init__(self, user_id, guild):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild = guild
        self.selected_category = None
        self.selected_text_channel = None

        categories = [c for c in guild.categories]
        if not categories:
            options = [discord.SelectOption(label="No categories found", value="none", description="Create a category first")]
        else:
            options = [discord.SelectOption(label=c.name, value=str(c.id)) for c in categories]

        self.category_select = discord.ui.Select(placeholder="Select a category", options=options)
        self.category_select.callback = self.category_selected
        self.add_item(self.category_select)

    async def category_selected(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your menu!", ephemeral=True)
            return

        if self.category_select.values[0] == "none":
            await interaction.response.send_message("❌ No categories available. Please create one first.", ephemeral=True)
            return

        category_id = int(self.category_select.values[0])
        self.selected_category = self.guild.get_channel(category_id)

        text_channels = [ch for ch in self.selected_category.text_channels]
        if not text_channels:
            await interaction.response.send_message("❌ No text channels in this category. Please create one first.", ephemeral=True)
            return

        options = [discord.SelectOption(label=ch.name, value=str(ch.id)) for ch in text_channels]
        self.text_channel_select = discord.ui.Select(placeholder="Select a text channel", options=options)
        self.text_channel_select.callback = self.text_channel_selected

        self.clear_items()
        self.add_item(self.text_channel_select)

        await interaction.response.edit_message(content="Select a text channel for the menu:", view=self)

    async def text_channel_selected(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your menu!", ephemeral=True)
            return

        text_channel_id = int(self.text_channel_select.values[0])
        self.selected_text_channel = self.guild.get_channel(text_channel_id)

        await interaction.response.send_message("✅ Category and text channel selected! Proceeding...", ephemeral=True)
        self.stop()

class DurationView(discord.ui.View):
    def __init__(self, user_id, channel, category=None, menu_text_channel=None):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.channel = channel
        self.category = category
        self.menu_text_channel = menu_text_channel
        self.days = None

    @discord.ui.button(label="1 Day", style=discord.ButtonStyle.green)
    async def one_day(self, interaction, button):  # Fixed parameter order
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your menu!", ephemeral=True)
            return
        self.days = 1
        await self.show_access_menu(interaction)

    @discord.ui.button(label="1 Week", style=discord.ButtonStyle.blurple)
    async def one_week(self, interaction, button):  # Fixed parameter order
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your menu!", ephemeral=True)
            return
        self.days = 7
        await self.show_access_menu(interaction)

    @discord.ui.button(label="2 Weeks", style=discord.ButtonStyle.blurple)
    async def two_weeks(self, interaction, button):  # Fixed parameter order
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your menu!", ephemeral=True)
            return
        self.days = 14
        await self.show_access_menu(interaction)

    @discord.ui.button(label="Custom", style=discord.ButtonStyle.gray)
    async def custom_duration(self, interaction, button):  # Fixed parameter order
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your menu!", ephemeral=True)
            return

        await interaction.response.send_message("Please type the number of days (1-60 max):", ephemeral=True)

        def check(m):
            return m.author.id == self.user_id and m.channel == self.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=30)
            try:
                days = int(msg.content)
                if days < 1 or days > 60:
                    await self.channel.send("❌ Please enter a number between 1 and 60 days!")
                    return

                self.days = days
                embed = discord.Embed(
                    title="🔐 Channel Access Type",
                    description="Who can join your channel?",
                    color=0x00ff00
                )
                view = AccessTypeView(self.user_id, self.days, self.channel, self.category, self.menu_text_channel)
                await self.channel.send(embed=embed, view=view)
            except ValueError:
                await self.channel.send("❌ Please enter a valid number!")
        except asyncio.TimeoutError:
            await self.channel.send("⏰ Timed out! Please try again.")

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

    @discord.ui.button(label="🌐 Open (Anyone can join)", style=discord.ButtonStyle.green)
    async def open_access(self, interaction, button):  # Fixed parameter order
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your menu!", ephemeral=True)
            return
        await self.ask_channel_name(interaction, request_only=False)

    @discord.ui.button(label="🔒 Request Only", style=discord.ButtonStyle.red)
    async def request_access(self, interaction, button):  # Fixed parameter order
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your menu!", ephemeral=True)
            return
        await self.ask_channel_name(interaction, request_only=True)

    async def ask_channel_name(self, interaction, request_only):
        await interaction.response.send_message("Please type the name you want for your voice channel (1-100 characters):", ephemeral=True)

        def check(m):
            return m.author.id == self.user_id and m.channel == self.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            channel_name = msg.content.strip()
            if not (1 <= len(channel_name) <= 100):
                await self.channel.send("❌ Channel name must be between 1 and 100 characters!")
                return
            await self.create_channel(interaction, request_only, channel_name)
        except asyncio.TimeoutError:
            await self.channel.send("⏰ Timed out! Please try again.")

    async def create_channel(self, interaction, request_only, channel_name):
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=self.days)
        guild = interaction.guild
        user = interaction.user

        category = self.category or discord.utils.get(guild.categories, name="ℙ𝕣𝕚𝕧𝕒𝕥𝕖 𝕍𝕠𝕚𝕔𝕖 ℂ𝕣𝕖𝕒𝕥𝕠𝕣")

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

        channel = await guild.create_voice_channel(
            name=channel_name,
            overwrites=overwrites,
            category=category,
            reason="User-created custom voice channel"
        )

        menu_text_channel = self.menu_text_channel or discord.utils.get(guild.text_channels, name="vc-menu")
        if not menu_text_channel:
            await self.channel.send("❌ Could not find the menu text channel! Please create it first.")
            return

        async for msg in menu_text_channel.history(limit=100):
            if not msg.pinned:
                try:
                    await msg.delete()
                except:
                    pass

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

        await self.channel.send(f"✅ {user.mention}, your voice channel **{channel_name}** has been created! Check <#{menu_text_channel.id}> to manage it.")

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

# --- Commands ---

@bot.command(name="voice")
async def voice_command(ctx):
    view = CategoryTextChannelSelectView(ctx.author.id, ctx.guild)
    await ctx.send("Please select the category and text channel for your voice channel:", view=view)

    timeout = await view.wait()
    if timeout:
        await ctx.send("⏰ Selection timed out. Please try again.")
        return

    # Pass selected category and text channel to DurationView
    duration_view = DurationView(ctx.author.id, ctx.channel, category=view.selected_category, menu_text_channel=view.selected_text_channel)
    embed = discord.Embed(title="⏰ Channel Duration", description="How long should your voice channel last?", color=0x00ff00)
    await ctx.send(embed=embed, view=duration_view)

@bot.command(name="vcmanage")
async def vcmanage_command(ctx):
    voice_state = ctx.author.voice
    if not voice_state or not voice_state.channel:
        await ctx.send("❌ You are not connected to any voice channel.")
        return

    channel = voice_state.channel
    channel_info = temp_channels.get(channel.id)
    if not channel_info or channel_info["owner_id"] != ctx.author.id:
        await ctx.send("❌ You do not own this voice channel or it is not managed by the bot.")
        return

    view = ChannelActionsView(channel.id, ctx.author.id)
    embed = discord.Embed(
        title="Manage Your Voice Channel",
        description=f"Channel: {channel.name}",
        color=0x00ff00
    )
    await ctx.send(embed=embed, view=view)

@bot.command(name="vcsetup")
@commands.has_permissions(manage_channels=True)
async def vcsetup_command(ctx):
    def check_author(m):
        return m.author == ctx.author and m.channel == ctx.channel

    await ctx.send("Please type the name of the category you want to create or use:")

    try:
        category_msg = await bot.wait_for("message", check=check_author, timeout=60)
        category_name = category_msg.content.strip()

        guild = ctx.guild
        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            category = await guild.create_category(category_name)
            await ctx.send(f"Category **{category_name}** created.")
        else:
            await ctx.send(f"Using existing category **{category_name}**.")

        await ctx.send("Please type the name of the text channel to create under this category:")

        text_channel_msg = await bot.wait_for("message", check=check_author, timeout=60)
        text_channel_name = text_channel_msg.content.strip()

        existing_channel = discord.utils.get(guild.text_channels, name=text_channel_name)
        if existing_channel:
            await ctx.send(f"Text channel **{text_channel_name}** already exists.")
        else:
            await guild.create_text_channel(text_channel_name, category=category)
            await ctx.send(f"Text channel **{text_channel_name}** created under category **{category_name}**.")

    except asyncio.TimeoutError:
        await ctx.send("⏰ Setup timed out. Please try again.")

@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="🤖 Bot Commands",
        description="Here are the available commands:",
        color=0x0099ff
    )
    embed.add_field(name="!voice", value="Create a temporary voice channel", inline=False)
    embed.add_field(name="!vcmanage", value="Manage your own voice channel (kick/block users)", inline=False)
    embed.add_field(name="!vcsetup", value="Setup category and text channel for voice channels (requires Manage Channels permission)", inline=False)
    embed.add_field(name="!help", value="Show this help message", inline=False)
    await ctx.send(embed=embed)

bot.run(os.getenv("BOT_TOKEN"))
