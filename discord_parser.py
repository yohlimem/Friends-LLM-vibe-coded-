import re
import json
import os
from datetime import datetime
from collections import Counter
from typing import List, Dict, Any, Tuple, Optional
from whatsapp_parser import (
    clean_unicode_controls,
    strip_urls,
    contains_hebrew,
    contains_english,
    is_system_message,
    group_into_conversations
)

# Discord Non-chat message types to ignore (system/event notices)
DISCORD_SYSTEM_TYPES = {
    "RecipientAdd", "RecipientRemove", "Call", "ChannelNameChange",
    "ChannelIconChange", "ChannelPinnedMessage", "GuildMemberJoin",
    "UserPremiumGuildSubscription", "UserPremiumGuildSubscriptionTier1",
    "UserPremiumGuildSubscriptionTier2", "UserPremiumGuildSubscriptionTier3",
    "ChannelFollowAdd", "GuildDiscoveryDisqualified", "GuildDiscoveryRequalified",
    "GuildDiscoveryGracePeriodInitialWarning", "GuildDiscoveryGracePeriodFinalWarning",
    "ThreadCreated", "ThreadStarterMessage", "GuildInviteReminder"
}

# Timestamp patterns for Discord TXT export (e.g. DiscordChatExporter .txt format)
DISCORD_TXT_PATTERNS = [
    # [01-Jan-24 12:00 PM] Sender#0000 or [01-Jan-24 12:00 PM] Sender:
    re.compile(r"^\[(\d{1,2}-[\w]{3}-\d{2,4}\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)\]\s*([^:\n]+?)(?:#\d{4})?:\s*(.*)$", re.IGNORECASE),
    re.compile(r"^\[(\d{1,2}-[\w]{3}-\d{2,4}\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)\]\s*([^:\n]+?)(?:#\d{4})?\s*$", re.IGNORECASE),

    # [2024-01-15 14:30:00] Sender: Content or [15/01/2024 14:30] Sender: Content
    re.compile(r"^\[(\d{2,4}[\/\.-]\d{1,2}[\/\.-]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)\]\s*([^:\n]+?):\s*(.*)$", re.IGNORECASE),
    re.compile(r"^\[(\d{2,4}[\/\.-]\d{1,2}[\/\.-]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)\]\s*([^:\n]+?)\s*$", re.IGNORECASE),

    # Sender [01/15/2024 12:00 PM]: Content
    re.compile(r"^([^\[:\n]+?)\s*\[(\d{1,2}[\/\.-]\d{1,2}[\/\.-]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)\]:\s*(.*)$", re.IGNORECASE),
    re.compile(r"^([^\[:\n]+?)\s*\[(\d{1,2}[\/\.-]\d{1,2}[\/\.-]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)\]\s*$", re.IGNORECASE),
]


def parse_iso_timestamp(ts_str: str) -> Tuple[str, str]:
    """Extracts formatted date (DD/MM/YYYY) and time (HH:MM:SS) from ISO or standard timestamp strings."""
    if not ts_str:
        return "", ""
    ts_str = str(ts_str).strip()

    # Try ISO parsing
    try:
        clean_ts = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_ts)
        return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M:%S")
    except Exception:
        pass

    # Try common strptime formats
    formats = [
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
        "%d-%b-%y %I:%M %p", "%d-%b-%Y %I:%M %p",
        "%d-%b-%y %H:%M:%S", "%d-%b-%Y %H:%M:%S"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(ts_str.split(".")[0], fmt)
            return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M:%S")
        except Exception:
            continue

    # Fallback string split
    parts = ts_str.split("T") if "T" in ts_str else ts_str.split(" ")
    if len(parts) >= 2:
        date_part = parts[0]
        time_part = parts[1].split("+")[0].split("-")[0].split(".")[0]
        return date_part, time_part

    return ts_str, ""


def extract_author_name(author_data: Any) -> Tuple[str, bool]:
    """
    Extracts display name and isBot flag from Discord author field.
    Supports DiscordChatExporter author objects, raw strings, or GDPR data.
    """
    if isinstance(author_data, str):
        clean_name = re.sub(r'#\d{4}$', '', author_data).strip()
        return clean_name or "DiscordUser", False

    if isinstance(author_data, dict):
        is_bot = bool(author_data.get("isBot") or author_data.get("bot") or False)
        nickname = author_data.get("nickname") or author_data.get("globalName") or author_data.get("global_name")
        name = nickname or author_data.get("name") or author_data.get("username") or "DiscordUser"
        clean_name = re.sub(r'#\d{4}$', '', str(name)).strip()
        return clean_name or "DiscordUser", is_bot

    return "DiscordUser", False


def parse_discord_json_data(data: Any) -> Dict[str, Any]:
    """Parses loaded JSON data from DiscordChatExporter or official Discord export."""
    messages_raw = []
    if isinstance(data, dict):
        if "messages" in data and isinstance(data["messages"], list):
            messages_raw = data["messages"]
        elif "messages" in data and isinstance(data["messages"], dict):
            messages_raw = list(data["messages"].values())
    elif isinstance(data, list):
        messages_raw = data

    cleaned_messages = []
    sender_counts = Counter()
    hebrew_count = 0
    english_count = 0
    media_count = 0
    urls_removed_count = 0

    for item in messages_raw:
        if not isinstance(item, dict):
            continue

        msg_type = item.get("type", "Default")
        if msg_type in DISCORD_SYSTEM_TYPES and msg_type not in ["Default", "Reply"]:
            continue

        author_data = item.get("author") or item.get("user") or item.get("Author") or "DiscordUser"
        sender, is_bot = extract_author_name(author_data)

        if is_bot:
            continue

        raw_content = clean_unicode_controls(item.get("content") or item.get("Contents") or item.get("message") or "")
        attachments = item.get("attachments") or item.get("Attachments") or []

        if not raw_content and attachments:
            media_count += len(attachments)
            continue

        if not raw_content:
            continue

        if is_system_message(raw_content) or is_system_message(sender):
            continue

        # Strip URLs
        content_no_urls = strip_urls(raw_content)
        if content_no_urls != raw_content:
            urls_removed_count += 1

        if not content_no_urls:
            media_count += 1
            continue

        ts_raw = item.get("timestamp") or item.get("Timestamp") or item.get("createdAt") or ""
        date_str, time_str = parse_iso_timestamp(ts_raw)

        has_heb = contains_hebrew(content_no_urls)
        has_eng = contains_english(content_no_urls)
        if has_heb:
            hebrew_count += 1
        if has_eng:
            english_count += 1

        sender_counts[sender] += 1

        cleaned_messages.append({
            "date": date_str,
            "time": time_str,
            "sender": sender,
            "content": content_no_urls,
            "has_hebrew": has_heb,
            "has_english": has_eng
        })

    top_senders = [s for s, c in sender_counts.most_common(10)]

    stats = {
        "total_messages": len(cleaned_messages),
        "total_raw_lines": len(messages_raw),
        "sender_counts": dict(sender_counts),
        "top_senders": top_senders,
        "hebrew_messages": hebrew_count,
        "english_messages": english_count,
        "media_omitted_count": media_count,
        "urls_removed_count": urls_removed_count,
        "chat_source": "Discord (JSON)"
    }

    return {
        "stats": stats,
        "messages": cleaned_messages
    }


def parse_discord_txt_file(file_path: str) -> Dict[str, Any]:
    """Parses a raw Discord text export file (.txt) from DiscordChatExporter."""
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    messages: List[Dict[str, Any]] = []
    current_msg = None

    for raw_line in lines:
        line = clean_unicode_controls(raw_line)
        if not line or line.startswith("===") or line.startswith("Guild:") or line.startswith("Channel:"):
            continue

        matched = False
        for pattern in DISCORD_TXT_PATTERNS:
            m = pattern.match(line)
            if m:
                groups = m.groups()
                if len(groups) == 3:
                    ts_str, sender, content = groups
                elif len(groups) == 2:
                    ts_str, sender = groups
                    content = ""
                else:
                    continue

                date_str, time_str = parse_iso_timestamp(ts_str)
                sender = re.sub(r'#\d{4}$', '', sender.strip()).strip()

                if current_msg:
                    messages.append(current_msg)

                current_msg = {
                    "date": date_str,
                    "time": time_str,
                    "sender": sender,
                    "content": content.strip()
                }
                matched = True
                break

        if not matched:
            if current_msg is not None:
                if current_msg["content"]:
                    current_msg["content"] += "\n" + line
                else:
                    current_msg["content"] = line

    if current_msg:
        messages.append(current_msg)

    cleaned_messages = []
    sender_counts = Counter()
    hebrew_count = 0
    english_count = 0
    media_count = 0
    urls_removed_count = 0

    for msg in messages:
        raw_content = msg["content"]
        sender = msg["sender"]

        if is_system_message(raw_content) or is_system_message(sender):
            continue

        content_no_urls = strip_urls(raw_content)
        if content_no_urls != raw_content:
            urls_removed_count += 1

        if not content_no_urls:
            media_count += 1
            continue

        has_heb = contains_hebrew(content_no_urls)
        has_eng = contains_english(content_no_urls)
        if has_heb:
            hebrew_count += 1
        if has_eng:
            english_count += 1

        sender_counts[sender] += 1

        cleaned_messages.append({
            "date": msg["date"],
            "time": msg["time"],
            "sender": sender,
            "content": content_no_urls,
            "has_hebrew": has_heb,
            "has_english": has_eng
        })

    top_senders = [s for s, c in sender_counts.most_common(10)]

    stats = {
        "total_messages": len(cleaned_messages),
        "total_raw_lines": len(lines),
        "sender_counts": dict(sender_counts),
        "top_senders": top_senders,
        "hebrew_messages": hebrew_count,
        "english_messages": english_count,
        "media_omitted_count": media_count,
        "urls_removed_count": urls_removed_count,
        "chat_source": "Discord (TXT)"
    }

    return {
        "stats": stats,
        "messages": cleaned_messages
    }


def parse_discord_file(file_path: str) -> Dict[str, Any]:
    """Detects whether file is JSON or TXT and parses accordingly."""
    if file_path.endswith(".json"):
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            data = json.load(f)
        return parse_discord_json_data(data)

    # Check if file content starts with JSON brackets
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        head = f.read(1024).strip()

    if head.startswith("{") or head.startswith("["):
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            data = json.load(f)
        return parse_discord_json_data(data)

    return parse_discord_txt_file(file_path)
