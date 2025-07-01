
import discord
from discord.ext import commands
from data import load_settings, save_settings
from perms import check_category_permissions, check_text_channel_permissions, format_permission_error

async def setup_echonet(ctx, bot):
    """Set up EchoNet for a guild."""
    guild = ctx.guild
    settings = load_settings()
    guild_id = str(guild.id)
    
    # Create or find category
    category = None
    for cat in guild.categories:
        if cat.name.lower() == "echonet voice channels":
            category = cat
            break
    
    if not category:
        try:
            category = await guild.create_category("EchoNet Voice Channels")
            await ctx.send(f"✅ Created category: **{category.name}**")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to create categories. Please create a category named 'EchoNet Voice Channels' and give me 'Manage Channels' permission in it.")
            return
        except Exception as e:
            await ctx.send(f"❌ Error creating category: {str(e)}")
            return
    
    # Create or find text channel
    text_channel = None
    for channel in guild.text_channels:
        if channel.name.lower() == "voice-control":
            text_channel = channel
            break
    
    if not text_channel:
        try:
            text_channel = await guild.create_text_channel("voice-control", category=category)
            await ctx.send(f"✅ Created text channel: **{text_channel.name}**")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to create text channels. Please create a text channel named 'voice-control' in the EchoNet category.")
            return
        except Exception as e:
            await ctx.send(f"❌ Error creating text channel: {str(e)}")
            return
    
    # Check permissions
    missing_cat = check_category_permissions(category)
    missing_txt = check_text_channel_permissions(text_channel)
    
    if missing_cat or missing_txt:
        error_msg = "❌ Missing required permissions:\n"
        if missing_cat:
            error_msg += format_permission_error(missing_cat, f"Category {category.name}") + "\n"
        if missing_txt:
            error_msg += format_permission_error(missing_txt, f"Text Channel {text_channel.name}") + "\n"
        error_msg += "\nPlease grant these permissions and run setup again."
        await ctx.send(error_msg)
        return
    
    # Save settings
    if guild_id not in settings:
        settings[guild_id] = {}
    
    settings[guild_id]["category_id"] = category.id
    settings[guild_id]["text_channel_id"] = text_channel.id
    save_settings(settings)
    
    embed = discord.Embed(
        title="✅ EchoNet Setup Complete!",
        description="Your server is now ready to use EchoNet.",
        color=0x00ff00
    )
    embed.add_field(name="Category", value=category.name, inline=True)
    embed.add_field(name="Text Channel", value=text_channel.mention, inline=True)
    embed.add_field(name="Next Step", value="Run `!voice` to set up the main menu", inline=False)
    
    await ctx.send(embed=embed)

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
    
    category_id = settings[guild_id].get("category_id")
    text_channel_id = settings[guild_id].get("text_channel_id")
    
    category = ctx.guild.get_channel(category_id) if category_id else None
    text_channel = ctx.guild.get_channel(text_channel_id) if text_channel_id else None
    
    if not category:
        embed.add_field(
            name="❌ Category", 
            value="Saved category no longer exists. Re-run `!echonetsetup`.", 
            inline=False
        )
    else:
        missing_cat = check_category_permissions(category)
        if missing_cat:
            embed.add_field(
                name=f"❌ Category: {category.name}", 
                value=f"Missing: {', '.join(missing_cat)}", 
                inline=False
            )
        else:
            embed.add_field(
                name=f"✅ Category: {category.name}", 
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
