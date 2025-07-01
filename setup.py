import discord
from discord.ext import commands
from data import load_settings, save_settings
from perms import check_category_permissions, check_text_channel_permissions, format_permission_error
import asyncio

async def setup_echonet(ctx, bot):
    """Set up EchoNet for a server."""
    settings = load_settings()
    guild_id = str(ctx.guild.id)

    # Ask for voice channels category name
    embed = discord.Embed(
        title="🔧 EchoNet Setup - Step 1/3",
        description="What would you like to name the category for voice channels?",
        color=0xffaa00
    )
    embed.add_field(name="Default", value="EchoNet Voice Channels", inline=False)
    embed.add_field(name="Instructions", value="Type your desired category name or 'default' to use the default name.", inline=False)

    await ctx.send(embed=embed)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for('message', check=check, timeout=60.0)
        voice_category_name = "EchoNet Voice Channels" if msg.content.lower() == "default" else msg.content.strip()
    except asyncio.TimeoutError:
        await ctx.send("❌ Setup timed out. Please try again.")
        return

    # Ask for menu category name
    embed = discord.Embed(
        title="🔧 EchoNet Setup - Step 2/3",
        description="What would you like to name the category for the menu text channel?",
        color=0xffaa00
    )
    embed.add_field(name="Default", value="EchoNet Controls", inline=False)
    embed.add_field(name="Instructions", value="Type your desired category name or 'default' to use the default name.", inline=False)

    await ctx.send(embed=embed)

    try:
        msg = await bot.wait_for('message', check=check, timeout=60.0)
        menu_category_name = "EchoNet Controls" if msg.content.lower() == "default" else msg.content.strip()
    except asyncio.TimeoutError:
        await ctx.send("❌ Setup timed out. Please try again.")
        return

    # Ask for menu text channel name
    embed = discord.Embed(
        title="🔧 EchoNet Setup - Step 3/3",
        description="What would you like to name the text channel for the menu?",
        color=0xffaa00
    )
    embed.add_field(name="Default", value="voice-controls", inline=False)
    embed.add_field(name="Instructions", value="Type your desired channel name or 'default' to use the default name.", inline=False)

    await ctx.send(embed=embed)

    try:
        msg = await bot.wait_for('message', check=check, timeout=60.0)
        text_channel_name = "voice-controls" if msg.content.lower() == "default" else msg.content.strip()
    except asyncio.TimeoutError:
        await ctx.send("❌ Setup timed out. Please try again.")
        return

    embed = discord.Embed(
        title="🔧 Setting up EchoNet...",
        description="Creating necessary channels and categories.",
        color=0xffaa00
    )
    setup_msg = await ctx.send(embed=embed)

    try:
        # Create or find voice channels category
        voice_category = None
        for cat in ctx.guild.categories:
            if cat.name.lower() == voice_category_name.lower():
                voice_category = cat
                break

        if not voice_category:
            try:
                voice_category = await ctx.guild.create_category_channel(
                    voice_category_name,
                    reason="EchoNet setup - Voice channel category"
                )
            except Exception as e:
                await ctx.send(f"❌ Error creating voice category: {str(e)}")
                return

        # Create or find menu category
        menu_category = None
        for cat in ctx.guild.categories:
            if cat.name.lower() == menu_category_name.lower():
                menu_category = cat
                break

        if not menu_category:
            try:
                menu_category = await ctx.guild.create_category_channel(
                    menu_category_name,
                    reason="EchoNet setup - Menu category"
                )
            except Exception as e:
                await ctx.send(f"❌ Error creating menu category: {str(e)}")
                return

        # Create text channel for menus in the menu category
        text_channel = None
        for channel in ctx.guild.text_channels:
            if channel.name.lower() == text_channel_name.lower() and channel.category == menu_category:
                text_channel = channel
                break

        if not text_channel:
            try:
                text_channel = await menu_category.create_text_channel(
                    text_channel_name,
                    reason="EchoNet setup - Menu text channel"
                )
            except Exception as e:
                await ctx.send(f"❌ Error creating text channel: {str(e)}")
                return

        # Check permissions
        missing_cat = check_category_permissions(menu_category)
        missing_txt = check_text_channel_permissions(text_channel)

        if missing_cat or missing_txt:
            error_msg = "❌ Missing required permissions:\n"
            if missing_cat:
                error_msg += format_permission_error(missing_cat, f"Category {menu_category.name}") + "\n"
            if missing_txt:
                error_msg += format_permission_error(missing_txt, f"Text Channel {text_channel.name}") + "\n"
            error_msg += "\nPlease grant these permissions and run setup again."
            await ctx.send(error_msg)
            return

        # Save settings
        if guild_id not in settings:
            settings[guild_id] = {}

        settings[guild_id]["voice_category_id"] = voice_category.id
        settings[guild_id]["menu_category_id"] = menu_category.id
        settings[guild_id]["text_channel_id"] = text_channel.id
        save_settings(settings)

        embed = discord.Embed(
            title="✅ EchoNet Setup Complete!",
            description="Your server is now ready to use EchoNet.",
            color=0x00ff00
        )
        embed.add_field(name="Category", value=menu_category.name, inline=True)
        embed.add_field(name="Text Channel", value=text_channel.mention, inline=True)
        embed.add_field(name="Next Step", value="Run `!voice` to set up the main menu", inline=False)

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ An unexpected error occurred: {str(e)}")

async def diagnose_permissions(ctx):
    """Diagnose permission issues for EchoNet."""
    settings = load_settings()
    guild_id = str(ctx.guild.id)

    embed = discord.Embed(
        title="🔍 EchoNet Permission Diagnosis",
        color=0x0099ff
    )

    if guild_id not in settings:
        embed.add_field(
            name="❌ Setup Status", 
            value="EchoNet is not set up for this server. Run `!echonetsetup` first.", 
            inline=False
        )
        await ctx.send(embed=embed)
        return

    voice_category_id = settings[guild_id].get("voice_category_id", settings[guild_id].get("category_id"))
    menu_category_id = settings[guild_id].get("menu_category_id")
    text_channel_id = settings[guild_id].get("text_channel_id")

    voice_category = ctx.guild.get_channel(voice_category_id) if voice_category_id else None
    menu_category = ctx.guild.get_channel(menu_category_id) if menu_category_id else None
    text_channel = ctx.guild.get_channel(text_channel_id) if text_channel_id else None

    if not voice_category:
        embed.add_field(
            name="❌ Voice Category", 
            value="Saved voice category no longer exists. Re-run `!echonetsetup`.", 
            inline=False
        )
    else:
        missing_cat = check_category_permissions(voice_category)
        if missing_cat:
            embed.add_field(
                name=f"❌ Voice Category: {voice_category.name}", 
                value=f"Missing: {', '.join(missing_cat)}", 
                inline=False
            )
        else:
            embed.add_field(
                name=f"✅ Voice Category: {voice_category.name}", 
                value="All permissions OK", 
                inline=False
            )

    if not menu_category:
        embed.add_field(
            name="❌ Menu Category", 
            value="Saved menu category no longer exists. Re-run `!echonetsetup`.", 
            inline=False
        )
    else:
        missing_menu_cat = check_category_permissions(menu_category)
        if missing_menu_cat:
            embed.add_field(
                name=f"❌ Menu Category: {menu_category.name}", 
                value=f"Missing: {', '.join(missing_menu_cat)}", 
                inline=False
            )
        else:
            embed.add_field(
                name=f"✅ Menu Category: {menu_category.name}", 
                value="All permissions OK", 
                inline=False
            )

    if not text_channel:
        embed.add_field(
            name="❌ Text Channel", 
            value="Saved text channel no longer exists. Re-run `!echonetsetup`.", 
            inline=False
        )
    else:
        missing_txt = check_text_channel_permissions(text_channel)
        if missing_txt:
            embed.add_field(
                name=f"❌ Text Channel: {text_channel.name}", 
                value=f"Missing: {', '.join(missing_txt)}", 
                inline=False
            )
        else:
            embed.add_field(
                name=f"✅ Text Channel: {text_channel.name}", 
                value="All permissions OK", 
                inline=False
            )

    embed.add_field(
        name="Required Permissions",
        value="**Category**: Manage Channels, View Channel\n**Text Channel**: Send Messages, Embed Links, Read Message History, Manage Messages",
        inline=False
    )

    await ctx.send(embed=embed)
