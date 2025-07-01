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

    async def on_submit(self, interaction: discord.Interaction):
        # Show the dropdown view after getting the channel name
        view = CreateChannelView(self.channel_name.value)
        embed = discord.Embed(
            title="🎤 Create Voice Channel",
            description=f"**Channel Name:** {self.channel_name.value}\n\nPlease select the duration and access type:",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class CreateChannelView(discord.ui.View):
    def __init__(self, channel_name):
        super().__init__(timeout=120)
        self.channel_name = channel_name
        self.duration_days = None  # No default, user must select
        self.request_only = None  # No default, user must select
        self.setup_buttons()

    def setup_buttons(self):
        # Duration buttons - Row 1
        duration_buttons = [
            (1, "1 Day", "⏰"),
            (3, "3 Days", "📅"),
            (7, "1 Week", "📆"),
            (14, "2 Weeks", "🗓️"),
            (30, "1 Month", "📊"),
            (60, "2 Months", "📈")
        ]
        
        for days, label, emoji in duration_buttons:
            button = discord.ui.Button(
                label=label,
                emoji=emoji,
                style=discord.ButtonStyle.secondary,
                custom_id=f"duration_{days}"
            )
            button.callback = self.create_duration_callback(days)
            self.add_item(button)

        # Access type buttons - Row 2
        open_button = discord.ui.Button(
            label="Open",
            emoji="🌐",
            style=discord.ButtonStyle.secondary,
            custom_id="access_open",
            row=1
        )
        open_button.callback = self.create_access_callback(False)
        self.add_item(open_button)

        request_button = discord.ui.Button(
            label="Request Only",
            emoji="🔒",
            style=discord.ButtonStyle.secondary,
            custom_id="access_request",
            row=1
        )
        request_button.callback = self.create_access_callback(True)
        self.add_item(request_button)

    def create_duration_callback(self, days):
        async def duration_callback(interaction: discord.Interaction):
            self.duration_days = days
            # Update button styles
            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.custom_id and item.custom_id.startswith("duration_"):
                    item.style = discord.ButtonStyle.primary if item.custom_id == f"duration_{days}" else discord.ButtonStyle.secondary
            await interaction.response.defer()
            await self.update_embed(interaction)
        return duration_callback

    def create_access_callback(self, request_only):
        async def access_callback(interaction: discord.Interaction):
            self.request_only = request_only
            # Update button styles
            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.custom_id and item.custom_id.startswith("access_"):
                    if (item.custom_id == "access_request" and request_only) or (item.custom_id == "access_open" and not request_only):
                        item.style = discord.ButtonStyle.primary
                    else:
                        item.style = discord.ButtonStyle.secondary
            await interaction.response.defer()
            await self.update_embed(interaction)
        return access_callback

    async def update_embed(self, interaction: discord.Interaction):
        duration_text = f"{self.duration_days} day(s)" if self.duration_days is not None else "Not selected"
        access_text = "🔒 Request Only" if self.request_only is True else ("🌐 Open" if self.request_only is False else "Not selected")
        
        embed = discord.Embed(
            title="🎤 Create Voice Channel",
            description=f"**Channel Name:** {self.channel_name}\n**Duration:** {duration_text}\n**Access Type:** {access_text}",
            color=0x00ff00
        )
        
        # Show instructions if selections are incomplete
        if self.duration_days is None or self.request_only is None:
            embed.add_field(
                name="Instructions",
                value="Please select both duration and access type to continue.",
                inline=False
            )
        
        # Enable create button if both selections are made
        if self.duration_days is not None and self.request_only is not None:
            # Remove old create button if it exists
            for item in self.children:
                if isinstance(item, discord.ui.Button) and item.custom_id == "create_channel_final":
                    self.remove_item(item)
                    break
            
            create_button = discord.ui.Button(
                label="Create Channel",
                style=discord.ButtonStyle.green,
                emoji="✅",
                custom_id="create_channel_final",
                row=2
            )
            create_button.callback = self.create_channel
            self.add_item(create_button)
        
        await interaction.edit_original_response(embed=embed, view=self)

    async def create_channel(self, interaction: discord.Interaction):
        settings = load_settings()
        guild_id = str(interaction.guild.id)
        category_id = settings[guild_id]["category_id"]
        category = interaction.guild.get_channel(category_id)

        try:
            # Create the voice channel
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                interaction.user: discord.PermissionOverwrite(manage_channels=True, connect=True, view_channel=True)
            }

            bot_member = interaction.guild.me
            overwrites[bot_member] = discord.PermissionOverwrite(manage_channels=True, view_channel=True, connect=True)

            if self.request_only:
                overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(connect=False, view_channel=True)
            else:
                overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(connect=True, view_channel=True)

            channel = await category.create_voice_channel(
                name=self.channel_name,
                overwrites=overwrites,
                reason=f"Temporary channel created by {interaction.user}"
            )

            # Calculate expiration
            expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=self.duration_days)

            # Save channel data
            temp_channels = load_temp_channels()
            temp_channels[channel.id] = {
                "owner_id": interaction.user.id,
                "expires_at": expires_at,
                "request_only": self.request_only,
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
            embed.add_field(name="Duration", value=f"{self.duration_days} days", inline=True)
            embed.add_field(name="Access", value="Request Only" if self.request_only else "Open", inline=True)
            embed.add_field(name="Expires", value=f"<t:{int(expires_at.timestamp())}:R>", inline=True)

            view = ChannelManagementView(channel.id)
            await interaction.response.edit_message(embed=embed, view=view)

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

    @discord.ui.button(label="Transfer Ownership", style=discord.ButtonStyle.blurple, emoji="👑", row=0)
    async def transfer_ownership(self, interaction: discord.Interaction, button: discord.ui.Button):
        from data import load_temp_channels
        temp_channels = load_temp_channels()
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        if temp_channels[self.channel_id]["owner_id"] != interaction.user.id:
            await interaction.response.send_message("❌ Only the channel owner can transfer ownership.", ephemeral=True)
            return

        modal = TransferOwnershipModal(self.channel_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Invite User", style=discord.ButtonStyle.green, emoji="📨", row=0)
    async def invite_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        from data import load_temp_channels
        temp_channels = load_temp_channels()
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        if temp_channels[self.channel_id]["owner_id"] != interaction.user.id:
            await interaction.response.send_message("❌ Only the channel owner can invite users.", ephemeral=True)
            return

        modal = InviteUserModal(self.channel_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Kick User", style=discord.ButtonStyle.red, emoji="👢", row=0)
    async def kick_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        from data import load_temp_channels
        temp_channels = load_temp_channels()
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        if temp_channels[self.channel_id]["owner_id"] != interaction.user.id:
            await interaction.response.send_message("❌ Only the channel owner can kick users.", ephemeral=True)
            return

        view = KickUserView(self.channel_id, interaction.user.id)
        await interaction.response.send_message("Select a user to kick:", view=view, ephemeral=True)

    @discord.ui.button(label="Channel Stats", style=discord.ButtonStyle.secondary, emoji="📊", row=0)
    async def channel_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        from data import load_temp_channels
        temp_channels = load_temp_channels()
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        info = temp_channels[self.channel_id]
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        owner = interaction.guild.get_member(info["owner_id"])
        created_time = info["expires_at"] - datetime.timedelta(days=30)  # Estimate based on max duration
        
        embed = discord.Embed(
            title=f"📊 Channel Statistics: {channel.name}",
            color=0x3498db
        )
        embed.add_field(name="Owner", value=owner.mention if owner else "Unknown", inline=True)
        embed.add_field(name="Current Members", value=str(len(channel.members)), inline=True)
        embed.add_field(name="Access Type", value="🔒 Request Only" if info.get("request_only") else "🌐 Open", inline=True)
        embed.add_field(name="Expires", value=f"<t:{int(info['expires_at'].timestamp())}:R>", inline=True)
        embed.add_field(name="Pending Requests", value=str(len(info.get("pending_requests", []))), inline=True)
        embed.add_field(name="Blocked Users", value=str(len(info.get("blocked_users", []))), inline=True)
        embed.add_field(name="User Limit", value=str(info.get("user_limit", "No limit")), inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Extend Duration", style=discord.ButtonStyle.primary, emoji="⏰", row=1)
    async def extend_duration(self, interaction: discord.Interaction, button: discord.ui.Button):
        from data import load_temp_channels
        temp_channels = load_temp_channels()
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        if temp_channels[self.channel_id]["owner_id"] != interaction.user.id:
            await interaction.response.send_message("❌ Only the channel owner can extend duration.", ephemeral=True)
            return

        view = ExtendDurationView(self.channel_id, interaction.user.id)
        await interaction.response.send_message("Choose how much to extend the channel duration:", view=view, ephemeral=True)

    @discord.ui.button(label="Change Access Type", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def change_access_type(self, interaction: discord.Interaction, button: discord.ui.Button):
        from data import load_temp_channels, save_temp_channels
        temp_channels = load_temp_channels()
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        if temp_channels[self.channel_id]["owner_id"] != interaction.user.id:
            await interaction.response.send_message("❌ Only the channel owner can change access type.", ephemeral=True)
            return

        info = temp_channels[self.channel_id]
        current_type = info.get("request_only", False)
        new_type = not current_type
        info["request_only"] = new_type
        save_temp_channels(temp_channels)

        # Update channel permissions
        channel = interaction.guild.get_channel(self.channel_id)
        if channel:
            overwrites = channel.overwrites
            if new_type:  # Changing to request only
                overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(connect=False, view_channel=True)
            else:  # Changing to open
                overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(connect=True, view_channel=True)
            
            try:
                await channel.edit(overwrites=overwrites, reason="Access type changed by owner")
                access_text = "🔒 Request Only" if new_type else "🌐 Open"
                await interaction.response.send_message(f"✅ Channel access type changed to **{access_text}**!", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ I don't have permission to edit the channel.", ephemeral=True)

    @discord.ui.button(label="Set User Limit", style=discord.ButtonStyle.secondary, emoji="👥", row=1)
    async def set_user_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        from data import load_temp_channels
        temp_channels = load_temp_channels()
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        if temp_channels[self.channel_id]["owner_id"] != interaction.user.id:
            await interaction.response.send_message("❌ Only the channel owner can set user limit.", ephemeral=True)
            return

        modal = SetUserLimitModal(self.channel_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="View Pending Requests", style=discord.ButtonStyle.primary, emoji="📋", row=1)
    async def view_pending_requests(self, interaction: discord.Interaction, button: discord.ui.Button):
        from data import load_temp_channels
        temp_channels = load_temp_channels()
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        if temp_channels[self.channel_id]["owner_id"] != interaction.user.id:
            await interaction.response.send_message("❌ Only the channel owner can view pending requests.", ephemeral=True)
            return

        info = temp_channels[self.channel_id]
        pending = info.get("pending_requests", [])
        
        if not pending:
            await interaction.response.send_message("❌ No pending requests for this channel.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📋 Pending Join Requests",
            color=0x3498db
        )
        
        for user_id in pending:
            user = interaction.guild.get_member(user_id)
            if user:
                embed.add_field(
                    name=user.display_name,
                    value=user.mention,
                    inline=True
                )

        view = ManagePendingRequestsView(self.channel_id, interaction.user.id, pending)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Block User", style=discord.ButtonStyle.secondary, emoji="🚫", row=2)
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

    @discord.ui.button(label="Edit Channel", style=discord.ButtonStyle.primary, emoji="✏️", row=2)
    async def edit_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = EditChannelView(self.channel_id, interaction.user.id)
        await interaction.response.send_message("Edit your channel settings below:", view=view, ephemeral=True)

    @discord.ui.button(label="Unblock Users", style=discord.ButtonStyle.success, emoji="✅", row=2)
    async def unblock_users(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = UnblockedUsersView(self.channel_id, interaction.user.id)
        await interaction.response.send_message("Manage your blocked users below:", view=view, ephemeral=True)

    @discord.ui.button(label="Delete Channel", style=discord.ButtonStyle.red, emoji="🗑️", row=2)
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

class JoinRequestView(discord.ui.View):
    def __init__(self, channel_id, requester_id, guild_id):
        super().__init__(timeout=300)  # 5 minute timeout
        self.channel_id = channel_id
        self.requester_id = requester_id
        self.guild_id = guild_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, emoji="✅")
    async def approve_request(self, interaction: discord.Interaction, button: discord.ui.Button):
        from data import load_temp_channels, save_temp_channels
        temp_channels = load_temp_channels()
        
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel no longer exists!", ephemeral=True)
            return
            
        info = temp_channels[self.channel_id]
        if self.requester_id in info.get("pending_requests", []):
            info["pending_requests"].remove(self.requester_id)
            save_temp_channels(temp_channels)
            
            # Grant access to the channel
            guild = interaction.client.get_guild(self.guild_id)
            if guild:
                channel = guild.get_channel(self.channel_id)
                requester = guild.get_member(self.requester_id)
                if channel and requester:
                    try:
                        overwrites = channel.overwrites
                        overwrites[requester] = discord.PermissionOverwrite(connect=True, view_channel=True)
                        await channel.edit(overwrites=overwrites, reason="Join request approved")
                        
                        # Notify requester
                        try:
                            await requester.send(f"✅ Your request to join **{channel.name}** in **{guild.name}** has been approved! You can now join the channel.")
                        except:
                            pass
                            
                        await interaction.response.send_message(f"✅ Approved {requester.display_name}'s request to join {channel.name}!", ephemeral=True)
                    except discord.Forbidden:
                        await interaction.response.send_message("❌ I don't have permission to edit the channel.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Channel or user not found!", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Server not found!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Request not found or already processed!", ephemeral=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, emoji="❌")
    async def deny_request(self, interaction: discord.Interaction, button: discord.ui.Button):
        from data import load_temp_channels, save_temp_channels
        temp_channels = load_temp_channels()
        
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel no longer exists!", ephemeral=True)
            return
            
        info = temp_channels[self.channel_id]
        if self.requester_id in info.get("pending_requests", []):
            info["pending_requests"].remove(self.requester_id)
            save_temp_channels(temp_channels)
            
            # Notify requester
            guild = interaction.client.get_guild(self.guild_id)
            if guild:
                channel = guild.get_channel(self.channel_id)
                requester = guild.get_member(self.requester_id)
                if channel and requester:
                    try:
                        await requester.send(f"❌ Your request to join **{channel.name}** in **{guild.name}** has been denied.")
                    except:
                        pass
                    await interaction.response.send_message(f"❌ Denied {requester.display_name}'s request to join {channel.name}.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Channel or user not found!", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Server not found!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Request not found or already processed!", ephemeral=True)

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
        super().__init__(timeout=120)
        self.user_id = user_id
        self.guild = guild

    async def send_channel_list(self, interaction: discord.Interaction):
        from data import load_temp_channels
        temp_channels = load_temp_channels()

        guild = interaction.guild

        if not temp_channels:
            await interaction.response.send_message("❌ There are no active voice channels.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📋 Active Voice Channels",
            color=0x00ff00
        )

        request_only_channels = []
        
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
            
            # Add member count
            member_count = len(channel.members) if hasattr(channel, 'members') else 0
            
            embed.add_field(
                name=f"🎤 {channel.name}",
                value=f"**Owner:** {owner_name}\n**Access:** {access}\n**Members:** {member_count}\n**Expires:** {expires_str}",
                inline=False
            )
            
            # Check if user can request to join this channel
            if (info.get("request_only") and 
                info["owner_id"] != self.user_id and 
                self.user_id not in info.get("pending_requests", []) and
                self.user_id not in info.get("blocked_users", [])):
                request_only_channels.append((cid, channel.name, info["owner_id"]))

        # Add request join buttons for request-only channels
        for cid, channel_name, owner_id in request_only_channels:
            self.add_item(RequestJoinButton(cid, channel_name, owner_id, self.user_id))

        if request_only_channels:
            embed.add_field(
                name="💡 Tip",
                value="Use the buttons below to request access to private channels!",
                inline=False
            )

        await interaction.response.send_message(embed=embed, view=self, ephemeral=True)

class RequestJoinButton(discord.ui.Button):
    def __init__(self, channel_id, channel_name, owner_id, requester_id):
        # Truncate channel name if too long for button label
        display_name = channel_name[:20] + "..." if len(channel_name) > 20 else channel_name
        super().__init__(
            label=f"🔐 Join {display_name}",
            style=discord.ButtonStyle.secondary,
            emoji="📨",
            custom_id=f"reqjoin_{channel_id}"
        )
        self.channel_id = channel_id
        self.channel_name = channel_name
        self.owner_id = owner_id
        self.requester_id = requester_id

    async def callback(self, interaction: discord.Interaction):
        from data import load_temp_channels, save_temp_channels
        temp_channels = load_temp_channels()

        info = temp_channels.get(self.channel_id)
        if not info:
            await interaction.response.send_message("❌ Channel not found or no longer exists!", ephemeral=True)
            return

        # Check if user is blocked
        if self.requester_id in info.get("blocked_users", []):
            await interaction.response.send_message("❌ You have been blocked from this channel.", ephemeral=True)
            return

        if "pending_requests" not in info:
            info["pending_requests"] = []
        if self.requester_id in info["pending_requests"]:
            await interaction.response.send_message("❌ You have already requested to join this channel. Please wait for the owner's response.", ephemeral=True)
            return

        info["pending_requests"].append(self.requester_id)
        save_temp_channels(temp_channels)

        await interaction.response.send_message(f"✅ Your request to join **{self.channel_name}** has been sent to the channel owner!", ephemeral=True)

        # Send DM to channel owner
        owner = interaction.guild.get_member(self.owner_id)
        channel = interaction.guild.get_channel(self.channel_id)
        requester = interaction.user
        if owner and channel:
            try:
                embed = discord.Embed(
                    title="🔔 Voice Channel Join Request",
                    description=f"**{requester.display_name}** ({requester.mention}) has requested to join your channel **{channel.name}** in **{interaction.guild.name}**.",
                    color=0x3498db
                )
                embed.set_thumbnail(url=requester.display_avatar.url)
                embed.add_field(name="Channel", value=channel.name, inline=True)
                embed.add_field(name="Server", value=interaction.guild.name, inline=True)
                embed.add_field(name="Requested by", value=f"{requester.display_name}\n{requester.mention}", inline=False)
                
                view = JoinRequestView(self.channel_id, requester.id, interaction.guild.id)
                await owner.send(embed=embed, view=view)
            except discord.Forbidden:
                # If can't DM owner, try to find them in the channel and ping them
                try:
                    settings = load_settings()
                    guild_id = str(interaction.guild.id)
                    if guild_id in settings:
                        text_channel_id = settings[guild_id]["text_channel_id"]
                        text_channel = interaction.guild.get_channel(text_channel_id)
                        if text_channel:
                            await text_channel.send(f"🔔 {owner.mention}, **{requester.display_name}** has requested to join your channel **{channel.name}**. Please check your DMs or use the manage channel menu.")
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


class TransferOwnershipModal(discord.ui.Modal, title="Transfer Ownership"):
    def __init__(self, channel_id):
        super().__init__()
        self.channel_id = channel_id

    user_id = discord.ui.TextInput(label="New Owner (User ID or @mention)", placeholder="Enter user ID or mention them...")

    async def on_submit(self, interaction: discord.Interaction):
        from data import load_temp_channels, save_temp_channels
        temp_channels = load_temp_channels()
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        # Parse user ID
        user_input = self.user_id.value.strip()
        if user_input.startswith('<@') and user_input.endswith('>'):
            new_owner_id = int(user_input[2:-1].replace('!', ''))
        else:
            try:
                new_owner_id = int(user_input)
            except ValueError:
                await interaction.response.send_message("❌ Invalid user ID or mention.", ephemeral=True)
                return

        new_owner = interaction.guild.get_member(new_owner_id)
        if not new_owner:
            await interaction.response.send_message("❌ User not found in this server.", ephemeral=True)
            return

        if new_owner_id == temp_channels[self.channel_id]["owner_id"]:
            await interaction.response.send_message("❌ This user is already the owner.", ephemeral=True)
            return

        # Transfer ownership
        temp_channels[self.channel_id]["owner_id"] = new_owner_id
        save_temp_channels(temp_channels)

        # Update channel permissions
        channel = interaction.guild.get_channel(self.channel_id)
        if channel:
            try:
                overwrites = channel.overwrites
                # Remove old owner's manage permissions
                old_owner = interaction.user
                if old_owner in overwrites:
                    overwrites[old_owner] = discord.PermissionOverwrite(connect=True, view_channel=True)
                
                # Give new owner manage permissions
                overwrites[new_owner] = discord.PermissionOverwrite(manage_channels=True, connect=True, view_channel=True)
                await channel.edit(overwrites=overwrites, reason="Ownership transferred")
                
                # Notify new owner
                try:
                    await new_owner.send(f"🎉 You are now the owner of the voice channel **{channel.name}** in **{interaction.guild.name}**!")
                except:
                    pass
                
                await interaction.response.send_message(f"✅ Ownership of the channel has been transferred to {new_owner.display_name}!", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ I don't have permission to edit the channel.", ephemeral=True)

class InviteUserModal(discord.ui.Modal, title="Invite User"):
    def __init__(self, channel_id):
        super().__init__()
        self.channel_id = channel_id

    user_id = discord.ui.TextInput(label="User to Invite (User ID or @mention)", placeholder="Enter user ID or mention them...")

    async def on_submit(self, interaction: discord.Interaction):
        from data import load_temp_channels, save_temp_channels
        temp_channels = load_temp_channels()
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        # Parse user ID
        user_input = self.user_id.value.strip()
        if user_input.startswith('<@') and user_input.endswith('>'):
            invite_user_id = int(user_input[2:-1].replace('!', ''))
        else:
            try:
                invite_user_id = int(user_input)
            except ValueError:
                await interaction.response.send_message("❌ Invalid user ID or mention.", ephemeral=True)
                return

        invite_user = interaction.guild.get_member(invite_user_id)
        if not invite_user:
            await interaction.response.send_message("❌ User not found in this server.", ephemeral=True)
            return

        info = temp_channels[self.channel_id]
        if invite_user_id in info.get("blocked_users", []):
            await interaction.response.send_message("❌ This user is blocked from the channel.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        # Grant access to the channel
        try:
            overwrites = channel.overwrites
            overwrites[invite_user] = discord.PermissionOverwrite(connect=True, view_channel=True)
            await channel.edit(overwrites=overwrites, reason="User invited by owner")
            
            # Remove from pending requests if they're there
            if invite_user_id in info.get("pending_requests", []):
                info["pending_requests"].remove(invite_user_id)
                save_temp_channels(temp_channels)
            
            # Notify invited user
            try:
                await invite_user.send(f"🎉 You've been invited to join the voice channel **{channel.name}** in **{interaction.guild.name}**! You can now join the channel.")
            except:
                pass
            
            await interaction.response.send_message(f"✅ Successfully invited {invite_user.display_name} to the channel!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to edit the channel.", ephemeral=True)

class KickUserView(discord.ui.View):
    def __init__(self, channel_id, owner_id):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @discord.ui.button(label="Select User to Kick", style=discord.ButtonStyle.red, emoji="👢")
    async def select_user_to_kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Channel not found!", ephemeral=True)
            return

        # Get users currently in the channel (excluding owner and bot)
        kickable_users = [member for member in channel.members 
                         if member.id != self.owner_id and not member.bot]

        if not kickable_users:
            await interaction.response.send_message("❌ No users to kick from this channel.", ephemeral=True)
            return

        options = [discord.SelectOption(label=member.display_name, value=str(member.id)) 
                  for member in kickable_users[:25]]  # Discord limit
        
        select = discord.ui.Select(placeholder="Select a user to kick...", options=options)

        async def select_callback(select_interaction: discord.Interaction):
            user_id = int(select_interaction.data['values'][0])
            user = interaction.guild.get_member(user_id)
            if user and user.voice and user.voice.channel == channel:
                try:
                    await user.move_to(None, reason="Kicked by channel owner")
                    await select_interaction.response.send_message(f"✅ Kicked {user.display_name} from the channel.", ephemeral=True)
                except discord.Forbidden:
                    await select_interaction.response.send_message("❌ I don't have permission to move users.", ephemeral=True)
            else:
                await select_interaction.response.send_message("❌ User is not in the channel.", ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View(timeout=60)
        view.add_item(select)
        await interaction.response.send_message("Select a user to kick:", view=view, ephemeral=True)

class ExtendDurationView(discord.ui.View):
    def __init__(self, channel_id, owner_id):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @discord.ui.button(label="1 Hour", style=discord.ButtonStyle.secondary, emoji="⏰")
    async def extend_1_hour(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.extend_channel(interaction, hours=1)

    @discord.ui.button(label="6 Hours", style=discord.ButtonStyle.secondary, emoji="⏰")
    async def extend_6_hours(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.extend_channel(interaction, hours=6)

    @discord.ui.button(label="1 Day", style=discord.ButtonStyle.secondary, emoji="📅")
    async def extend_1_day(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.extend_channel(interaction, days=1)

    @discord.ui.button(label="1 Week", style=discord.ButtonStyle.secondary, emoji="📆")
    async def extend_1_week(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.extend_channel(interaction, days=7)

    async def extend_channel(self, interaction: discord.Interaction, days=0, hours=0):
        from data import load_temp_channels, save_temp_channels
        temp_channels = load_temp_channels()
        
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found!", ephemeral=True)
            return

        info = temp_channels[self.channel_id]
        current_expires = info["expires_at"]
        new_expires = current_expires + datetime.timedelta(days=days, hours=hours)
        
        # Check if new expiration is within 60 days from now
        max_expires = datetime.datetime.utcnow() + datetime.timedelta(days=60)
        if new_expires > max_expires:
            await interaction.response.send_message("❌ Cannot extend beyond 60 days from now.", ephemeral=True)
            return

        info["expires_at"] = new_expires
        save_temp_channels(temp_channels)
        
        duration_text = f"{days} day(s)" if days > 0 else f"{hours} hour(s)"
        await interaction.response.send_message(f"✅ Channel duration extended by {duration_text}. New expiration: <t:{int(new_expires.timestamp())}:R>", ephemeral=True)

class SetUserLimitModal(discord.ui.Modal, title="Set User Limit"):
    def __init__(self, channel_id):
        super().__init__()
        self.channel_id = channel_id

    user_limit = discord.ui.TextInput(label="User Limit (0 for no limit)", placeholder="Enter number of users (0-99)...")

    async def on_submit(self, interaction: discord.Interaction):
        from data import load_temp_channels, save_temp_channels
        temp_channels = load_temp_channels()
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        try:
            limit = int(self.user_limit.value)
            if limit < 0 or limit > 99:
                await interaction.response.send_message("❌ User limit must be between 0 and 99 (0 = no limit).", ephemeral=True)
                return

            channel = interaction.guild.get_channel(self.channel_id)
            if not channel:
                await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
                return

            try:
                await channel.edit(user_limit=limit if limit > 0 else None, reason="User limit changed by owner")
                temp_channels[self.channel_id]["user_limit"] = limit if limit > 0 else None
                save_temp_channels(temp_channels)
                
                limit_text = f"{limit} users" if limit > 0 else "No limit"
                await interaction.response.send_message(f"✅ User limit set to: **{limit_text}**", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ I don't have permission to edit the channel.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)

class ManagePendingRequestsView(discord.ui.View):
    def __init__(self, channel_id, owner_id, pending_requests):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        self.owner_id = owner_id
        self.pending_requests = pending_requests

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @discord.ui.button(label="Approve Request", style=discord.ButtonStyle.green, emoji="✅")
    async def approve_request(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pending_requests:
            await interaction.response.send_message("❌ No pending requests.", ephemeral=True)
            return

        options = []
        for user_id in self.pending_requests:
            user = interaction.guild.get_member(user_id)
            if user:
                options.append(discord.SelectOption(label=user.display_name, value=str(user_id)))

        if not options:
            await interaction.response.send_message("❌ No valid pending requests found.", ephemeral=True)
            return

        select = discord.ui.Select(placeholder="Select user to approve...", options=options)

        async def approve_callback(select_interaction: discord.Interaction):
            user_id = int(select_interaction.data['values'][0])
            await self.process_request(select_interaction, user_id, approve=True)

        select.callback = approve_callback
        view = discord.ui.View(timeout=60)
        view.add_item(select)
        await interaction.response.send_message("Select a user to approve:", view=view, ephemeral=True)

    @discord.ui.button(label="Deny Request", style=discord.ButtonStyle.red, emoji="❌")
    async def deny_request(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pending_requests:
            await interaction.response.send_message("❌ No pending requests.", ephemeral=True)
            return

        options = []
        for user_id in self.pending_requests:
            user = interaction.guild.get_member(user_id)
            if user:
                options.append(discord.SelectOption(label=user.display_name, value=str(user_id)))

        if not options:
            await interaction.response.send_message("❌ No valid pending requests found.", ephemeral=True)
            return

        select = discord.ui.Select(placeholder="Select user to deny...", options=options)

        async def deny_callback(select_interaction: discord.Interaction):
            user_id = int(select_interaction.data['values'][0])
            await self.process_request(select_interaction, user_id, approve=False)

        select.callback = deny_callback
        view = discord.ui.View(timeout=60)
        view.add_item(select)
        await interaction.response.send_message("Select a user to deny:", view=view, ephemeral=True)

    async def process_request(self, interaction: discord.Interaction, user_id: int, approve: bool):
        from data import load_temp_channels, save_temp_channels
        temp_channels = load_temp_channels()
        
        if self.channel_id not in temp_channels:
            await interaction.response.send_message("❌ Channel not found!", ephemeral=True)
            return
            
        info = temp_channels[self.channel_id]
        if user_id not in info.get("pending_requests", []):
            await interaction.response.send_message("❌ Request not found!", ephemeral=True)
            return

        info["pending_requests"].remove(user_id)
        save_temp_channels(temp_channels)
        
        user = interaction.guild.get_member(user_id)
        channel = interaction.guild.get_channel(self.channel_id)
        
        if approve:
            # Grant access
            if channel and user:
                try:
                    overwrites = channel.overwrites
                    overwrites[user] = discord.PermissionOverwrite(connect=True, view_channel=True)
                    await channel.edit(overwrites=overwrites, reason="Join request approved")
                    
                    # Notify user
                    try:
                        await user.send(f"✅ Your request to join **{channel.name}** in **{interaction.guild.name}** has been approved!")
                    except:
                        pass
                    
                    await interaction.response.send_message(f"✅ Approved {user.display_name}'s request!", ephemeral=True)
                except discord.Forbidden:
                    await interaction.response.send_message("❌ I don't have permission to edit the channel.", ephemeral=True)
        else:
            # Deny request
            if user and channel:
                try:
                    await user.send(f"❌ Your request to join **{channel.name}** in **{interaction.guild.name}** has been denied.")
                except:
                    pass
                await interaction.response.send_message(f"❌ Denied {user.display_name}'s request.", ephemeral=True)
