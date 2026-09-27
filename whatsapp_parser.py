import re
import json
import os
from datetime import datetime
from collections import Counter
from typing import List, Dict, Any, Tuple, Optional

# Common WhatsApp System Message patterns in English and Hebrew
SYSTEM_PATTERNS = [
    r"Messages and calls are end-to-end encrypted",
    r"הודעות ושיחות מוצפנות מקצה לקצה",
    r"created group",
    r"יצר/ה את הקבוצה",
    r"added",
    r"הוסיף/ה את",
    r"left",
    r"עזב/ה",
    r"changed the subject",
    r"שינה/תה את נושא הקבוצה",
    r"changed this group's icon",
    r"שינה/תה את סמל הקבוצה",
    r"deleted this message",
    r"הודעה זו נמחקה",
    r"You deleted this message",
    r"מחקת את ההודעה הזו",
    r"This message was deleted",
    r"Waiting for this message",
    r"מחכה להודעה זו",
]

# Media omitted tags in WhatsApp exports (English & Hebrew)
MEDIA_PATTERNS = [
    r"<Media omitted>",
    r"<מדיה הושמטה>",
    r"<sticker omitted>",
    r"<סטיקר הושמט>",
    r"<gif omitted>",
    r"<GIF הושמט>",
    r"<image omitted>",
    r"<תמונה הושמטה>",
    r"<video omitted>",
    r"<סרטון הושמט>",
    r"<audio omitted>",
    r"<הודעה קולית הושמטה>",
    r"<document omitted>",
    r"<מסמך הושמט>",
    r"<Contact card omitted>",
    r"<כרטיס איש קשר הושמט>",
    r"<location omitted>",
    r"<מיקום הושמט>",
    r"<Attached: .*?>",
    r"\(file attached\)",
    r"קובץ מצורף",
]

# Regex patterns for social media (YouTube Shorts, Reels, TikTok) and general URLs
URL_PATTERNS = [
    r"(?:https?://)?(?:www\.)?(?:youtube\.com/shorts/|youtube\.com/watch\?v=|youtu\.be/|youtube\.com/)[^\s]+",
    r"(?:https?://)?(?:www\.)?(?:instagram\.com/reel/|instagram\.com/reels/|instagram\.com/p/|instagram\.com/stories/|instagram\.com/|instagr\.am/)[^\s]+",
    r"(?:https?://)?(?:www\.)?(?:tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)/[^\s]+",
    r"(?:https?://)?(?:open\.)?spotify\.com/[^\s]+",
    r"https?://[^\s]+",
    r"www\.[^\s]+",
]

# WhatsApp timestamp regexes for various formats
TIMESTAMP_PATTERNS = [
    re.compile(r"^\[(\d{1,2}[\/\.]\d{1,2}[\/\.]\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)\]\s*([^:]+):\s*(.*)$", re.IGNORECASE),
    re.compile(r"^(\d{1,2}[\/\.]\d{1,2}[\/\.]\d{2,4}),?\s+(\d{1,2}:\d{2}(?:\s*[AP]M)?)\s*[\-\–]\s*([^:]+):\s*(.*)$", re.IGNORECASE),
    re.compile(r"^(\d{4}[\/\.-]\d{1,2}[\/\.-]\d{1,2}),?\s+(\d{1,2}:\d{2}(?:\s*[AP]M)?)\s*[\-\–]\s*([^:]+):\s*(.*)$", re.IGNORECASE),
]

def clean_unicode_controls(text: str) -> str:
    """Removes invisible Unicode direction marks (LTR/RTL override codes inserted by WhatsApp)."""
    if not text:
        return ""
    return re.sub(r'[\u200e\u200f\u202a-\u202e\ufeff]', '', text).strip()

def strip_urls(text: str) -> str:
    """Strips YouTube, Instagram, TikTok, and general URLs from message text."""
    if not text:
        return ""
    cleaned = text
    for pattern in URL_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    # Collapse multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def is_system_message(text: str) -> bool:
    """Checks if a line is a system notice (e.g. encrypted notice, member added)."""
    for pattern in SYSTEM_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def contains_hebrew(text: str) -> bool:
    """Returns True if the text contains Hebrew characters."""
    return bool(re.search(r'[\u0590-\u05FF]', text))

def contains_english(text: str) -> bool:
    """Returns True if the text contains English Latin characters."""
    return bool(re.search(r'[a-zA-Z]', text))

def parse_whatsapp_file(file_path: str) -> Dict[str, Any]:
    """
    Parses a raw WhatsApp export file (.txt) handling multiline messages, Hebrew/English,
    system lines, media omissions, and URL stripping (YouTube, IG, TikTok).
    """
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    messages: List[Dict[str, Any]] = []
    current_msg = None

    for raw_line in lines:
        line = clean_unicode_controls(raw_line)
        if not line:
            continue

        matched = False
        for pattern in TIMESTAMP_PATTERNS:
            m = pattern.match(line)
            if m:
                date_str, time_str, sender, content = m.groups()
                sender = sender.strip()
                content = content.strip()

                if current_msg:
                    messages.append(current_msg)

                current_msg = {
                    "date": date_str,
                    "time": time_str,
                    "sender": sender,
                    "content": content,
                }
                matched = True
                break

        if not matched:
            if current_msg is not None:
                current_msg["content"] += "\n" + line

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

        is_media = False
        for media_pat in MEDIA_PATTERNS:
            if re.search(media_pat, raw_content, re.IGNORECASE):
                is_media = True
                media_count += 1
                break

        if is_media:
            continue

        # Strip URLs (YouTube, Instagram, TikTok, Spotify, general URLs)
        content_no_urls = strip_urls(raw_content)
        if content_no_urls != raw_content:
            urls_removed_count += 1

        # Skip if message was ONLY a link and is now empty
        if not content_no_urls:
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
    }

    return {
        "stats": stats,
        "messages": cleaned_messages
    }


def parse_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    """Parses WhatsApp date and time string formats into a Python datetime object."""
    if not date_str or not time_str:
        return None

    date_clean = re.sub(r'[\[\]]', '', date_str.strip())
    time_clean = re.sub(r'[\[\]]', '', time_str.strip().upper())

    date_formats = [
        "%d/%m/%Y", "%d/%m/%y", "%d.%m.%Y", "%d.%m.%y",
        "%m/%d/%Y", "%m/%d/%y",
        "%Y-%m-%d", "%Y/%m/%d"
    ]
    time_formats = [
        "%H:%M:%S", "%H:%M",
        "%I:%M:%S %p", "%I:%M %p", "%I:%M:%S%p", "%I:%M%p"
    ]

    for df in date_formats:
        for tf in time_formats:
            try:
                dt_str = f"{date_clean} {time_clean}"
                return datetime.strptime(dt_str, f"{df} {tf}")
            except ValueError:
                continue
    return None


def group_into_conversations(messages: List[Dict[str, Any]], max_gap_minutes: int = 60) -> List[List[Dict[str, Any]]]:
    """
    Groups WhatsApp messages into discrete, realistic conversation sessions based on time gaps.
    A new session is triggered whenever the pause between consecutive messages exceeds max_gap_minutes.
    """
    if not messages:
        return []

    conversations = []
    current_session = []
    last_dt = None

    for msg in messages:
        msg_dt = parse_datetime(msg.get("date", ""), msg.get("time", ""))
        msg_copy = dict(msg)
        if msg_dt:
            msg_copy["datetime_obj"] = msg_dt.isoformat()

        if not current_session:
            current_session.append(msg_copy)
            if msg_dt:
                last_dt = msg_dt
            continue

        is_new_session = False
        if msg_dt and last_dt:
            gap_seconds = (msg_dt - last_dt).total_seconds()
            if gap_seconds >= (max_gap_minutes * 60) or gap_seconds < 0:
                is_new_session = True

        if is_new_session:
            if current_session:
                conversations.append(current_session)
            current_session = [msg_copy]
        else:
            current_session.append(msg_copy)

        if msg_dt:
            last_dt = msg_dt

    if current_session:
        conversations.append(current_session)

    return conversations


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        res = parse_whatsapp_file(sys.argv[1])
        print(f"Parsed {res['stats']['total_messages']} valid messages.")
        print(f"URLs stripped: {res['stats']['urls_removed_count']}")
        print("Senders:", res['stats']['sender_counts'])
        convs = group_into_conversations(res["messages"], max_gap_minutes=60)
        print(f"Grouped into {len(convs)} discrete conversation sessions.")

