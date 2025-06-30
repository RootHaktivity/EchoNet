import discord
from discord.ext import commands
import asyncio
from data import load_settings, save_settings
from perms import check_category_permissions, check_text_channel_permissions, format_permission_error

async def setup_echonet(ctx, bot):
    """Handle the EchoNet setup process."""
    def check_author(m):
        return m.author == ctx.author and m.channel == ctx.channel

    guild = ctx.guild

    # Step 1: Ask for voice channel category name
    await ctx.send("Please type the name for the category where new voice channels will be created:")

    try:
        cat_msg = await bot.wait_for("message", check=check_author, timeout=60)
        voice_category_name = cat_msg.content.strip()
        if not (1 <= len(voice_category_name) <= 100):
            await ctx.send("❌ Category name must be between 1 and 100 characters.")
            return
    except asyncio.TimeoutError:
        await ctx.send("❌ Timed out. Please try again.")
        return

    # Step 2: Ask for menu text channel name
    await ctx.send("Please type the name for the menu text channel (will be created under 'EchoNet Menu' category):")

    try:
        txt_msg = await bot.wait_for("message", check=check_author, timeout=60)
        text_channel_name = txt_msg.content.strip()
        if not (1 <= len(text_channel_name) <= 100):
            await ctx.send("❌ Text channel name must be between 1 and 100 characters.")
            return
    except asyncio.TimeoutError:
        await ctx.send("❌ Timed out. Please try again.")
        return

    try:
        # Step 3: Create voice channel category
        await ctx.send(f"Creating voice channel category: **{voice_category_name}**...")
        voice_category = await guild.create_category(voice_category_name)
        
        # Step 4: Create EchoNet Menu category
        await ctx.send("Creating **EchoNet Menu** category...")
        menu_category = await guild.create_category("EchoNet Menu")
        
        # Step 5: Create text channel under EchoNet Menu category
        await ctx.send(f"Creating text channel: **{text_channel_name}** under **EchoNet Menu**...")
        text_channel = await guild.create_text_channel(text_channel_name, category=menu_category)
        
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to create categories or channels. Please ensure I have 'Manage Channels' permission.")
        return
    except Exception as e:
        await ctx.send(f"❌ Error creating channels: {str(e)}")
        return

    # Step 6: Check permissions before saving settings
    missing_cat = check_category_permissions(voice_category)
    missing_txt = check_text_channel_permissions(text_channel)

    if missing_cat or missing_txt:
        msg = "⚠️ **Missing Required Permissions:**\n"
        if missing_cat:
            msg += format_permission_error(missing_cat, f"Category {voice_category.name}") + "\n"
        if missing_txt:
            msg += format_permission_error(missing_txt, f"Text Channel {text_channel.name}") + "\n"
        msg += "\n**Please grant these permissions and run `!echonetsetup` again.**\n\n"
        msg += "**Required Permissions:**\n"
        msg += f"• **{voice_category.name}**: Manage Channels, View Channel\n"
        msg += f"• **{text_channel.name}**: Send Messages, Embed Links, Read Message History, Manage Messages"
        await ctx.send(msg)
        return

    # Step 7: Save settings
    settings = load_settings()
    settings[str(guild.id)] = {
        "category_id": voice_category.id,
        "text_channel_id": text_channel.id
    }
    save_settings(settings)
    
    await ctx.send(
        f"✅ **Setup Complete!**\n\n"
        f"📁 **Voice Channel Category**: {voice_category.name}\n"
        f"📋 **Menu Text Channel**: {text_channel.name} (under EchoNet Menu)\n\n"
        f"🔧 All required permissions are properly configured!"
    )

async def diagnose_permissions(ctx):
    """Diagnose permission issues for EchoNet."""
    settings = load_settings()
    guild_id = str(ctx.guild.id)
    if guild_id not in settings:
        await ctx.send("❌ Setup not complete. Please run `!echonetsetup` first.")
        return

    category = ctx.guild.get_channel(settings[guild_id]["category_id"])
    text_channel = ctx.guild.get_channel(settings[guild_id]["text_channel_id"])

    if not category or not text_channel:
        await ctx.send("❌ Configured category or text channel no longer exists. Please run `!echonetsetup` again.")
        return

    missing_cat = check_category_permissions(category)
    missing_txt = check_text_channel_permissions(text_channel)

    embed = discord.Embed(title="🔧 EchoNet Permission Diagnosis", color=0x00ff00)

    if not missing_cat and not missing_txt:
        embed.description = "✅ All permissions are configured correctly!"
        embed.add_field(name=f"Category: {category.name}", value="✅ All permissions OK", inline=False)
        embed.add_field(name=f"Text Channel: {text_channel.name}", value="✅ All permissions OK", inline=False)
    else:
        embed.description = "⚠️ Some permissions are missing:"
        embed.color = 0xff9900

        if missing_cat:
            embed.add_field(
                name=f"❌ Category: {category.name}", 
                value=f"Missing: {', '.join(missing_cat)}", 
                inline=False
            )
        else:
            embed.add_field(name=f"✅ Category: {category.name}", value="All permissions OK", inline=False)

        if missing_txt:
            embed.add_field(
                name=f"❌ Text Channel: {text_channel.name}", 
                value=f"Missing: {', '.join(missing_txt)}", 
                inline=False
            )
        else:
            embed.add_field(name=f"✅ Text Channel: {text_channel.name}", value="All permissions OK", inline=False)

    embed.add_field(
        name="Required Permissions",
        value=f"**Category**: Manage Channels, View Channel\n**Text Channel**: Send Messages, Embed Links, Read Message History, Manage Messages",
        inline=False
    )

    await ctx.send(embed=embed)