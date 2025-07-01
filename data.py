import json
import os
import datetime

SETTINGS_FILE = "echonet_settings.json"
CHANNELS_FILE = "channels.json"

def load_settings():
    """Load bot settings from JSON file."""
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_settings(settings):
    """Save bot settings to JSON file."""
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)

def load_temp_channels():
    """Load temporary channel data from JSON file."""
    temp_channels = {}
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, "r") as f:
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
        except Exception as e:
            print(f"Error loading channel data: {e}")
            temp_channels = {}
    return temp_channels

def save_temp_channels(temp_channels):
    """Save temporary channel data to JSON file."""
    data = {}
    for channel_id, info in temp_channels.items():
        data[str(channel_id)] = {
            "owner_id": info["owner_id"],
            "expires_at": info["expires_at"].isoformat(),
            "request_only": info["request_only"],
            "pending_requests": info.get("pending_requests", []),
            "menu_message_id": info.get("menu_message_id"),
            "menu_channel_id": info.get("menu_channel_id"),
            "blocked_users": info.get("blocked_users", []),
            "user_limit": info.get("user_limit")
        }

    with open(CHANNELS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def save_temp_channels(temp_channels):
    """Save temporary channel data to JSON file."""
    data = {}
    for channel_id, info in temp_channels.items():
        data[str(channel_id)] = {
            "owner_id": info["owner_id"],
            "expires_at": info["expires_at"].isoformat(),
            "request_only": info["request_only"],
            "pending_requests": info.get("pending_requests", []),
            "menu_message_id": info.get("menu_message_id"),
            "menu_channel_id": info.get("menu_channel_id"),
            "blocked_users": info.get("blocked_users", []),
            "user_limit": info.get("user_limit")
        }
    with open(CHANNELS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def add_temp_channel(channel_id, owner_id, expires_at, request_only, menu_message_id=None, menu_channel_id=None):
    """Add a new temporary channel to the data."""
    return {
        "owner_id": owner_id,
        "expires_at": expires_at,
        "request_only": request_only,
        "pending_requests": [],
        "menu_message_id": menu_message_id,
        "menu_channel_id": menu_channel_id,
        "blocked_users": []
    }