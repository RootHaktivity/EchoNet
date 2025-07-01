import discord
from discord.ext import commands
import asyncio
import datetime
from data import load_settings, save_settings, load_temp_channels, save_temp_channels
from perms import check_category_permissions, check_voice_channel_permissions, format_permission_error

MAIN_MENU_TAG = "🎤 **MAIN MENU**"

class MainMenu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create Voice Channel", style=discord.ButtonStyle.green, emoji="🎤", custom_id="mainmenu_create")
    async def create_voice_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = load_settings()
        guild_id = str(interaction.guild.id)

        if guild_id not in settings:
            await interaction.response.send_message("❌ Setup not complete. Please ask an admin to run `!echonetsetup` first.", ephemeral=True)
            return

        category_id = settings[guild_id]["category_id"]
        category = interaction.guild.get_channel(category_id)

        if not category:
            await interaction.response.send_message("❌ The saved category no longer exists. Please ask an admin to run `!echonetsetup` again.", ephemeral=True)
            return

        missing_perms = check_category_permissions(category)
        if missing_perms:
            perm_error = format_permission_error(missing_perms, f"Category {category.name}")
            await interaction.response.send_message(f"❌ Cannot create channel due to missing permissions:\n{perm_error}\n\nPlease contact an admin.", ephemeral=True)
            return

        modal = CreateChannelModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🛠️ Manage My Channel", style=discord.ButtonStyle.blurple, custom_id="mainmenu_manage")
    async def manage_channel(self, interaction, button):
        from data import load_temp_channels
        temp_channels = load_temp_channels()

        owned = [cid for cid, info in temp_channels.items() if info["owner_id"] == interaction.user.id]
        if not owned:
            await interaction.response.send_message("❌ You don't own any active voice channels.", ephemeral=True)
            return

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
            view = ChannelManagementView(cid)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
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

    @discord.ui.button(label="📋 List Channels", style=discord.ButtonStyle.primary, custom_id="mainmenu_list")
    async def list_channels(self, interaction, button):
        view = ListChannelsView(interaction.user.id, interaction.guild)
        await view.send_channel_list(interaction)

class CreateChannelModal(discord.ui.Modal, title="Create Voice Channel"):
    def __init__(self):
        super().__init__()

    channel_name = discord.ui.TextInput(label="Channel Name", placeholder="Enter your channel name...", max_length=50)
    duration_days = discord.ui.TextInput(label="Duration (days)", placeholder="1-60 days", default="1", max_length=2)
    access_type = discord.ui.TextInput(label="Access Type", placeholder="Type 'open' or 'request'", default="open", max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        settings = load_settings()
        guild_id = str(interaction.guild.id)
        category_id = settings[guild_id]["category_id"]
        category = interaction.guild.get_channel(category_id)

        # Validate duration
        try:
            days = int(self.duration_days.value)
            if not 1 <= days <= 60:
                await interaction.response.send_message("❌ Duration must be between 1 and 60 days.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Duration must be a valid number.", ephemeral=True)
            return

        # Validate access type
        access_type = self.access_type.value.lower().strip()
        if access_type not in ["open", "request"]:
            await interaction.response.send_message("❌ Access type must be 'open' or 'request'.", ephemeral=True)
            return

        request_only = access_type == "request"

        try:
            # Create the voice channel
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                interaction.user: discord.PermissionOverwrite(manage_channels=True, connect=True, view_channel=True)
            }

            bot_member = interaction.guild.me
            overwrites[bot_member] = discord.PermissionOverwrite(manage_channels=True, view_channel=True, connect=True)

            if request_only:
                overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(connect=False, view_channel=True)
            else:
                overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(connect=True, view_channel=True)

            channel = await category.create_voice_channel(
                name=self.channel_name.value,
                overwrites=overwrites,
                reason=f"Temporary channel created by {interaction.user}"
            )

            # Calculate expiration
            expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=days)

            # Save channel data
            temp_channels = load_temp_channels()
            temp_channels[channel.id] = {
                "owner_id": interaction.user.id,
                "expires_at": expires_at,
                "request_only": request_only,
                "pending_requests": [],
                "menu_message_id": None,
                "menu_channel_id": None,
                "blocked_users": []
            }
            save_temp_channels(temp_channels)

            # Create management embed
            embed = discord.Embed(
                title="✅ Voice Channel Created!",
                description=f"Your channel **{channel.name}** has been created.",
                color=0x00ff00
            )
            embed.add_field(name="Duration", value=f"{days} days", inline=True)
            embed.add_field(name="Access", value="Request Only" if request_only else "Open", inline=True)
            embed.add_field(name="Expires", value=f"<t:{int(expires_at.timestamp())}:R>", inline=True)

            view = ChannelManagementView(channel.id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

            # Schedule cleanup - modified to work with ephemeral=True
            await asyncio.sleep(5)  # Give the user time to see the message
            original_response = await interaction.original_response()
            try:
                await original_response.delete()
            except:
                pass

        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to create voice channels.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error creating channel: {str(e)}", ephemeral=True)

class SelectChannelView(discord.ui.View):
    def __init__(self, user_id, channel_options):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.channel_options = channel_options

        options = []
        for name, cid in channel_options[:25]:
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
        view = ChannelManagementView(cid)
        await interaction.response.edit_message(embed=embed, view=view)

class ChannelManagementView(discord.ui.View):
    def __init__(self, channel_id):
        super().__init__(timeout=300)
        self.channel_id = channel_id

    @discord.ui.button(label="Delete Channel", style=discord.ButtonStyle.red, emoji="🗑️")
    async def delete_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        from data import load_temp_channels, save_temp_channels
        temp_channels = load_temp_channels()
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        if temp_channels[self.channel_id]["owner_id"] != interaction.user.id:
            await interaction.response.send_message("❌ Only the channel owner can delete it.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(self.channel_id)
        if channel:
            try:
                await channel.delete(reason=f"Deleted by owner {interaction.user}")
                del temp_channels[self.channel_id]
                save_temp_channels(temp_channels)
                await interaction.response.send_message("✅ Channel deleted successfully.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ I don't have permission to delete the channel.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)

    @discord.ui.button(label="Block User", style=discord.ButtonStyle.secondary, emoji="🚫")
    async def block_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        from data import load_temp_channels
        temp_channels = load_temp_channels()
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        if temp_channels[self.channel_id]["owner_id"] != interaction.user.id:
            await interaction.response.send_message("❌ Only the channel owner can block users.", ephemeral=True)
            return

        modal = BlockUserModal(self.channel_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Channel", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = EditChannelView(self.channel_id, interaction.user.id)
        await interaction.response.send_message("Edit your channel settings below:", view=view, ephemeral=True)

    @discord.ui.button(label="Unblock Users", style=discord.ButtonStyle.success, emoji="✅")
    async def unblock_users(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = UnblockedUsersView(self.channel_id, interaction.user.id)
        await interaction.response.send_message("Manage your blocked users below:", view=view, ephemeral=True)

class EditChannelView(discord.ui.View):
    def __init__(self, channel_id, user_id):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="Rename Channel", style=discord.ButtonStyle.primary, emoji="✏️")
    async def rename_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Please type the new name for your channel (1-100 characters):", ephemeral=True)

        def check(m):
            return m.author.id == self.user_id and m.guild and m.guild.id == interaction.guild.id

        try:
            msg = await interaction.client.wait_for("message", check=check, timeout=60)
            new_name = msg.content.strip()
            if not (1 <= len(new_name) <= 100):
                await interaction.followup.send("❌ Channel name must be between 1 and 100 characters!", ephemeral=True)
                return

            channel = interaction.guild.get_channel(self.channel_id)
            if not channel:
                await interaction.followup.send("❌ Channel not found!", ephemeral=True)
                return

            await channel.edit(name=new_name, reason="Renamed by owner via EchoNet")
            await interaction.followup.send(f"✅ Channel renamed to **{new_name}**!", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timed out! Please try again.", ephemeral=True)

    @discord.ui.button(label="Change Duration", style=discord.ButtonStyle.secondary, emoji="⏰")
    async def change_duration(self, interaction: discord.Interaction, button: discord.ui.Button):
        from data import load_temp_channels, save_temp_channels
        temp_channels = load_temp_channels()

        await interaction.response.send_message("Please type the new duration in days (1-60):", ephemeral=True)

        def check(m):
            return m.author.id == self.user_id and m.guild and m.guild.id == interaction.guild.id

        try:
            msg = await interaction.client.wait_for("message", check=check, timeout=60)
            try:
                days = int(msg.content)
                if days < 1 or days > 60:
                    await interaction.followup.send("❌ Please enter a number between 1 and 60!", ephemeral=True)
                    return

                if self.channel_id not in temp_channels:
                    await interaction.followup.send("❌ Channel not found in data!", ephemeral=True)
                    return

                expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=days)
                temp_channels[self.channel_id]["expires_at"] = expires_at
                save_temp_channels(temp_channels)
                await interaction.followup.send(f"✅ Channel duration updated to {days} day(s) from now.", ephemeral=True)
            except ValueError:
                await interaction.followup.send("❌ Please enter a valid number!", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timed out! Please try again.", ephemeral=True)

class UnblockedUsersView(discord.ui.View):
    def __init__(self, channel_id, user_id):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="Unblock a User", style=discord.ButtonStyle.success, emoji="✅")
    async def unblock_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        from data import load_temp_channels, save_temp_channels
        temp_channels = load_temp_channels()

        if self.channel_id not in temp_channels or not temp_channels[self.channel_id]["blocked_users"]:
            await interaction.response.send_message("❌ No blocked users for this channel.", ephemeral=True)
            return

        blocked_ids = temp_channels[self.channel_id]["blocked_users"]
        guild = interaction.guild
        blocked_members = [guild.get_member(uid) for uid in blocked_ids if guild.get_member(uid)]

        if not blocked_members:
            await interaction.response.send_message("❌ No blocked users found in this server.", ephemeral=True)
            return

        options = [discord.SelectOption(label=member.display_name, value=str(member.id)) for member in blocked_members]
        select = discord.ui.Select(placeholder="Select a user to unblock...", options=options)

        async def select_callback(select_interaction: discord.Interaction):
            user_id = int(select_interaction.data['values'][0])
            temp_channels[self.channel_id]["blocked_users"].remove(user_id)
            save_temp_channels(temp_channels)

            channel = guild.get_channel(self.channel_id)
            user = guild.get_member(user_id)
            if channel and user:
                overwrites = channel.overwrites
                if user in overwrites:
                    del overwrites[user]
                    await channel.edit(overwrites=overwrites, reason="User unblocked by owner via EchoNet")

            await select_interaction.response.send_message(f"✅ {user.mention} has been unblocked.", ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View(timeout=60)
        view.add_item(select)
        await interaction.response.send_message("Select a user to unblock:", view=view, ephemeral=True)

class BlockUserModal(discord.ui.Modal, title="Block User"):
    def __init__(self, channel_id):
        super().__init__()
        self.channel_id = channel_id

    user_id = discord.ui.TextInput(label="User ID or @mention", placeholder="Enter user ID or mention them...")

    async def on_submit(self, interaction: discord.Interaction):
        from data import load_temp_channels, save_temp_channels
        temp_channels = load_temp_channels()
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        # Parse user ID
        user_input = self.user_id.value.strip()
        if user_input.startswith('<@') and user_input.endswith('>'):
            user_id = int(user_input[2:-1].replace('!', ''))
        else:
            try:
                user_id = int(user_input)
            except ValueError:
                await interaction.response.send_message("❌ Invalid user ID or mention.", ephemeral=True)
                return

        user = interaction.guild.get_member(user_id)
        if not user:
            await interaction.response.send_message("❌ User not found in this server.", ephemeral=True)
            return

        if user_id in temp_channels[self.channel_id]["blocked_users"]:
            await interaction.response.send_message("❌ User is already blocked.", ephemeral=True)
            return

        temp_channels[self.channel_id]["blocked_users"].append(user_id)
        save_temp_channels(temp_channels)

        # Remove user from channel if they're in it
        channel = interaction.guild.get_channel(self.channel_id)
        if channel and user.voice and user.voice.channel == channel:
            try:
                await user.move_to(None, reason="User blocked by channel owner")
            except discord.Forbidden:
                pass

        await interaction.response.send_message(f"✅ Blocked {user.display_name} from the channel.", ephemeral=True)

class ApproveDenyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, emoji="✅", custom_id="approve_request")
    async def approve_request(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Implementation for approving requests
        await interaction.response.send_message("Request approved!", ephemeral=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, emoji="❌", custom_id="deny_request")
    async def deny_request(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Implementation for denying requests
        await interaction.response.send_message("Request denied!", ephemeral=True)

class ListChannelsView(discord.ui.View):
    def __init__(self, user_id, guild):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.guild = guild

        from data import load_temp_channels
        temp_channels = load_temp_channels()

        for cid, info in temp_channels.items():
            if (
                info.get("request_only")
                and info["owner_id"] != self.user_id
                and self.user_id not in info.get("pending_requests", [])
            ):
                channel = guild.get_channel(cid)
                if channel:
                    self.add_item(RequestJoinButton(cid, channel.name, info["owner_id"], self.user_id))

    async def send_channel_list(self, interaction: discord.Interaction):
        from data import load_temp_channels
        temp_channels = load_temp_channels()

        guild = interaction.guild

        if not temp_channels:
            await interaction.response.send_message("❌ There are no active voice channels.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Active Voice Channels",
            color=0x00ff00
        )

        for cid, info in temp_channels.items():
            channel = guild.get_channel(cid)
            if not channel:
                continue
            expires = info["expires_at"]
            if isinstance(expires, datetime.datetime):
                expires_str = expires.strftime("%Y-%m-%d %H:%M UTC")
            else:
                expires_str = str(expires)
            access = "🔒 Request Only" if info.get("request_only") else "🌐 Open"
            owner = guild.get_member(info["owner_id"])
            owner_name = owner.mention if owner else f"User ID {info['owner_id']}"
            embed.add_field(
                name=f"{channel.name} (ID: {cid})",
                value=f"Owner: {owner_name}\nAccess: {access}\nExpires: {expires_str}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, view=self, ephemeral=True)

class RequestJoinButton(discord.ui.Button):
    def __init__(self, channel_id, channel_name, owner_id, requester_id):
        super().__init__(
            label=f"Request to Join: {channel_name}",
            style=discord.ButtonStyle.primary,
            custom_id=f"reqjoin_{channel_id}"
        )
        self.channel_id = channel_id
        self.owner_id = owner_id
        self.requester_id = requester_id

    async def callback(self, interaction: discord.Interaction):
        from data import load_temp_channels, save_temp_channels
        temp_channels = load_temp_channels()

        info = temp_channels.get(self.channel_id)
        if not info:
            await interaction.response.send_message("❌ Channel not found!", ephemeral=True)
            return

        if "pending_requests" not in info:
            info["pending_requests"] = []
        if self.requester_id in info["pending_requests"]:
            await interaction.response.send_message("❌ You have already requested to join this channel.", ephemeral=True)
            return

        info["pending_requests"].append(self.requester_id)
        save_temp_channels(temp_channels)

        await interaction.response.send_message("✅ Your request to join has been sent to the channel owner.", ephemeral=True)

        owner = interaction.guild.get_member(self.owner_id)
        channel = interaction.guild.get_channel(self.channel_id)
        requester = interaction.user
        if owner and channel:
            try:
                embed = discord.Embed(
                    title="Voice Channel Join Request",
                    description=f"{requester.mention} has requested to join your channel **{channel.name}** in **{interaction.guild.name}**.",
                    color=0x00ff00
                )
                view = ApproveDenyView()
                await owner.send(embed=embed, view=view)
            except:
                pass

async def purge_menu_text_channel(menu_text_channel):
    """Remove all messages from the menu text channel except pinned ones."""
    try:
        async for message in menu_text_channel.history(limit=100):
            if not message.pinned:
                try:
                    await message.delete()
                except:
                    pass
    except Exception as e:
        print(f"Error purging menu channel: {e}")

async def ensure_main_menu(menu_text_channel):
    """Ensure the main menu exists in the text channel."""
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
    """Delete management menu after delay and restore main menu."""
    await asyncio.sleep(delay)
    try:
        await management_msg.delete()
    except:
        pass
    await purge_menu_text_channel(menu_text_channel)
    await ensure_main_menu(menu_text_channel)