import discord
from discord.ext import commands
import asyncio
import datetime
from data import load_settings, save_temp_channels, add_temp_channel
from perms import (
    check_bot_permissions, 
    format_permission_error, 
    check_category_permissions, 
    check_text_channel_permissions,
    check_voice_channel_permissions,
    check_move_permissions
)

MAIN_MENU_TAG = "[EchoNet Main Menu]"

# --- Helper Functions ---

async def purge_menu_text_channel(menu_text_channel):
    missing_perms = check_bot_permissions(menu_text_channel, ["read_message_history", "manage_messages"])
    if missing_perms:
        return
    async for msg in menu_text_channel.history(limit=100):
        if not (msg.author == menu_text_channel.guild.me and msg.content.startswith(MAIN_MENU_TAG)):
            try:
                await msg.delete()
            except:
                pass

async def ensure_main_menu(menu_text_channel):
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
    await purge_menu_text_channel(menu_text_channel)
    await ensure_main_menu(menu_text_channel)

# --- UI Classes ---

class ApproveDenyView(discord.ui.View):
    def __init__(self, cid=None, requester_id=None, guild_id=None):
        super().__init__(timeout=None)
        self.cid = cid
        self.requester_id = requester_id
        self.guild_id = guild_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, custom_id="approve_request")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        from main import bot, temp_channels, save_data

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

        missing_perms = check_voice_channel_permissions(channel)
        if missing_perms:
            perm_error = format_permission_error(missing_perms, f"Channel {channel.name}")
            await interaction.response.send_message(f"❌ Cannot approve request due to missing permissions:\n{perm_error}")
            return

        try:
            overwrites = channel.overwrites
            overwrites[requester] = discord.PermissionOverwrite(connect=True, view_channel=True)
            await channel.edit(overwrites=overwrites, reason="Approved join request")

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
        from main import bot, temp_channels, save_data

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

class MainMenu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

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

        missing_cat_perms = check_category_permissions(category)
        missing_txt_perms = check_text_channel_permissions(text_channel)

        if missing_cat_perms or missing_txt_perms:
            error_msg = "❌ Missing required permissions:\n"
            if missing_cat_perms:
                error_msg += format_permission_error(missing_cat_perms, f"Category {category.name}") + "\n"
            if missing_txt_perms:
                error_msg += format_permission_error(missing_txt_perms, f"Text Channel {text_channel.name}") + "\n"
            error_msg += "\nPlease ask an admin to grant these permissions."
            await interaction.response.send_message(error_msg, ephemeral=True)
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
        from main import temp_channels

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
            view = ChannelActionsView(cid, interaction.user.id)
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

    @discord.ui.button(label="📋 List Channels", style=discord.ButtonStyle.primary, emoji="📋", custom_id="mainmenu_list")
    async def list_channels(self, interaction, button):
        view = ListChannelsView(interaction.user.id)
        await view.send_channel_list(interaction)

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
            msg = await interaction.client.wait_for("message", check=check, timeout=30)
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
            msg = await interaction.client.wait_for("message", check=check, timeout=60)
            channel_name = msg.content.strip()
            if not (1 <= len(channel_name) <= 100):
                await interaction.followup.send("❌ Channel name must be between 1 and 100 characters!", ephemeral=True)
                return
            await self.create_channel(interaction, request_only, channel_name)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timed out! Please try again.", ephemeral=True)

    async def create_channel(self, interaction, request_only, channel_name):
        from main import bot, temp_channels, save_data
        from data import load_settings

        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=self.days)
        guild = interaction.guild
        user = interaction.user

        settings = load_settings()
        guild_id = str(guild.id)
        if guild_id not in settings or "category_id" not in settings[guild_id]:
            await interaction.followup.send("❌ No category set. Please ask an admin to run `!echonetsetup`.", ephemeral=True)
            return

        category_id = settings[guild_id]["category_id"]
        category = guild.get_channel(category_id)
        if not category:
            await interaction.followup.send("❌ The voice channel category no longer exists. Please ask an admin to run `!echonetsetup` again.", ephemeral=True)
            return

        missing_perms = check_category_permissions(category)
        if missing_perms:
            perm_error = format_permission_error(missing_perms, f"Category {category.name}")
            await interaction.followup.send(f"❌ Cannot create channel due to missing permissions:\n{perm_error}\n\nPlease ask an admin to grant these permissions.", ephemeral=True)
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

        temp_channels[channel.id] = add_temp_channel(
            channel.id, user.id, expires_at, request_only, menu_message.id, menu_text_channel.id
        )
        save_data()

        interaction.client.loop.create_task(delete_management_menu_and_restore_main(menu_text_channel, menu_message))

# ... (rest of your code for ChannelActionsView, EditChannelView, BlockedUsersView, ListChannelsView remains unchanged)