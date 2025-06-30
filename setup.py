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

    # Check permissions before saving settings
    missing_cat = check_category_permissions(category)
    missing_txt = check_text_channel_permissions(text_channel)

    if missing_cat or missing_txt:
        msg = "⚠️ **Missing Required Permissions:**\n"
        if missing_cat:
            msg += format_permission_error(missing_cat, f"Category {category.name}") + "\n"
        if missing_txt:
            msg += format_permission_error(missing_txt, f"Text Channel {text_channel.name}") + "\n"
        msg += "\n**Please grant these permissions and run `!echonetsetup` again.**\n\n"
        msg += "**Required Permissions:**\n"
        msg += f"• **{category.name}**: Manage Channels, View Channel\n"
        msg += f"• **{text_channel.name}**: Send Messages, Embed Links, Read Message History, Manage Messages"
        await ctx.send(msg)
        return

    # Save settings
    settings = load_settings()
    settings[str(guild.id)] = {
        "category_id": category.id,
        "text_channel_id": text_channel.id
    }
    save_settings(settings)
    await ctx.send(f"✅ Setup complete! New voice channels will be created in **{category.name}**, and the menu will be posted in **{text_channel.name}**.\n\n🔧 All required permissions are properly configured!")

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
