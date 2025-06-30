import discord

def check_bot_permissions(channel, perms_needed):
    """Check if bot has required permissions in a channel. Returns list of missing permissions."""
    if not channel:
        return perms_needed  # If channel doesn't exist, all perms are "missing"

    perms = channel.permissions_for(channel.guild.me)
    missing = []

    for perm in perms_needed:
        if not getattr(perms, perm, False):
            missing.append(perm.replace('_', ' ').title())

    return missing

def format_permission_error(missing_perms, location_name):
    """Format a nice error message for missing permissions."""
    if not missing_perms:
        return ""

    perm_list = ", ".join(missing_perms)
    return f"**{location_name}**: Missing {perm_list}"

def check_category_permissions(category):
    """Check if bot has required permissions in a category for creating channels."""
    return check_bot_permissions(category, ["manage_channels", "view_channel"])

def check_text_channel_permissions(text_channel):
    """Check if bot has required permissions in a text channel for menu operations."""
    return check_bot_permissions(text_channel, ["send_messages", "embed_links", "read_message_history", "manage_messages"])

def check_voice_channel_permissions(voice_channel):
    """Check if bot has required permissions in a voice channel for management."""
    return check_bot_permissions(voice_channel, ["manage_channels", "view_channel"])

def check_move_permissions(voice_channel):
    """Check if bot can move members to a voice channel."""
    return check_bot_permissions(voice_channel, ["move_members"])
