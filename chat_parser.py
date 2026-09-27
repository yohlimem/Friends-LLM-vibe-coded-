import os
import json
from typing import Dict, Any
from whatsapp_parser import parse_whatsapp_file
from discord_parser import parse_discord_file


def parse_chat_file(file_path: str) -> Dict[str, Any]:
    """
    Auto-detects chat export format (WhatsApp .txt, Discord .json, Discord .txt)
    and returns parsed messages with metadata & statistics.
    """
    file_ext = os.path.splitext(file_path)[1].lower()

    # 1. Direct JSON file handling (DiscordChatExporter JSON or GDPR JSON)
    if file_ext == ".json":
        return parse_discord_file(file_path)

    # 2. Inspect head content for JSON or Discord header markers
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            head = f.read(2048).strip()

        if head.startswith("{") or head.startswith("["):
            try:
                return parse_discord_file(file_path)
            except Exception:
                pass

        if "Guild:" in head or "Channel:" in head or "DiscordChatExporter" in head:
            try:
                res = parse_discord_file(file_path)
                if res["stats"]["total_messages"] > 0:
                    return res
            except Exception:
                pass

    # 3. Try WhatsApp parsing
    try:
        wa_res = parse_whatsapp_file(file_path)
        if "chat_source" not in wa_res["stats"]:
            wa_res["stats"]["chat_source"] = "WhatsApp"

        if wa_res["stats"]["total_messages"] > 0:
            return wa_res
    except Exception:
        pass

    # 4. Fallback to Discord text parser
    try:
        discord_res = parse_discord_file(file_path)
        if discord_res["stats"]["total_messages"] > 0:
            return discord_res
    except Exception:
        pass

    # Fallback to default whatsapp_parser result
    fallback = parse_whatsapp_file(file_path)
    if "chat_source" not in fallback["stats"]:
        fallback["stats"]["chat_source"] = "WhatsApp"
    return fallback
