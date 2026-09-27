import json
import random
from typing import List, Dict, Any, Optional
from whatsapp_parser import group_into_conversations

DEFAULT_HEBREW_SYSTEM_PROMPT = (
    "You are now responding and speaking exactly like {friend_name}. "
    "Use the same speaking style, vocabulary, slang, and language mixing (Hebrew/English) exactly as it appeared in the chat logs."
)

DEFAULT_ENGLISH_SYSTEM_PROMPT = (
    "You are now responding and speaking exactly like {friend_name}. "
    "Use the same speaking style, vocabulary, slang, and language mixing (Hebrew/English) exactly as it appeared in the chat logs."
)

def build_chat_dataset(
    messages: List[Dict[str, Any]],
    target_friend: Any,
    user_names: Optional[Any] = None,
    system_prompt: Optional[str] = None,
    context_turns: int = 5,
    val_split: float = 0.1,
    session_gap_minutes: int = 60,
    include_full_sessions: bool = True
) -> Dict[str, Any]:
    """
    Converts parsed WhatsApp & Discord messages into training samples by identifying discrete conversation sessions
    bounded by time gaps (e.g. 60 minutes of inactivity). Supports target_friend (AI) and user_names (Me/Others)
    role mapping so the model learns how specific friend(s) respond to specific conversation partner(s).
    """
    # 1. Parse friend (Assistant) aliases
    if isinstance(target_friend, str):
        target_aliases = [t.strip() for t in target_friend.split(",") if t.strip()]
    elif isinstance(target_friend, list):
        target_aliases = [str(t).strip() for t in target_friend if str(t).strip()]
    else:
        target_aliases = [str(target_friend).strip()]

    target_friend_lowers = set(t.lower() for t in target_aliases)
    main_friend = target_aliases[0] if target_aliases else "Friend"

    # 2. Parse user (Me / Sender) aliases
    user_names_lowers = None
    user_aliases = []
    if user_names:
        if isinstance(user_names, str):
            user_aliases = [u.strip() for u in user_names.split(",") if u.strip()]
        elif isinstance(user_names, list):
            user_aliases = [str(u).strip() for u in user_names if str(u).strip()]
        else:
            user_aliases = [str(user_names).strip()]
        if user_aliases:
            user_names_lowers = set(u.lower() for u in user_aliases)

    if not system_prompt:
        system_prompt = DEFAULT_HEBREW_SYSTEM_PROMPT.format(friend_name=main_friend)
    else:
        system_prompt = system_prompt.format(friend_name=main_friend)

    # 3. Group raw messages into discrete conversation sessions based on time gaps
    sessions = group_into_conversations(messages, max_gap_minutes=session_gap_minutes)

    dataset_samples = []
    seen_hashes = set()

    for session in sessions:
        if not session:
            continue

        # Filter session messages to only include active roles (Assistant or User)
        filtered_session = []
        for msg in session:
            s_lower = msg.get("sender", "").strip().lower()
            is_assistant = s_lower in target_friend_lowers
            is_user = (s_lower in user_names_lowers) if user_names_lowers else (not is_assistant)
            if is_assistant or is_user:
                filtered_session.append(msg)

        if not filtered_session:
            continue

        # A) Sliding Context Turn Samples WITHIN current session boundaries only
        for i in range(len(filtered_session)):
            msg = filtered_session[i]
            sender = msg["sender"].strip()
            s_lower = sender.lower()

            if s_lower in target_friend_lowers:
                target_response = msg["content"].strip()
                if not target_response:
                    continue

                # Preceding context within THIS session only
                start_idx = max(0, i - context_turns)
                context_msgs = filtered_session[start_idx:i]

                if not context_msgs:
                    continue

                formatted_messages = [{"role": "system", "content": system_prompt}]
                user_text_buffer = []

                for ctx_msg in context_msgs:
                    c_sender = ctx_msg["sender"].strip()
                    c_lower = c_sender.lower()
                    c_content = ctx_msg["content"].strip()
                    if not c_content:
                        continue

                    if c_lower in target_friend_lowers:
                        if user_text_buffer:
                            formatted_messages.append({"role": "user", "content": "\n".join(user_text_buffer)})
                            user_text_buffer = []
                        formatted_messages.append({"role": "assistant", "content": c_content})
                    else:
                        prefix = f"{c_sender}: " if (user_names_lowers and len(user_names_lowers) > 1) else ""
                        user_text_buffer.append(f"{prefix}{c_content}")

                if user_text_buffer:
                    formatted_messages.append({"role": "user", "content": "\n".join(user_text_buffer)})

                formatted_messages.append({"role": "assistant", "content": target_response})

                if len(formatted_messages) >= 3 and formatted_messages[-2]["role"] == "user":
                    sample_str = json.dumps(formatted_messages, ensure_ascii=False)
                    if sample_str not in seen_hashes:
                        seen_hashes.add(sample_str)
                        dataset_samples.append({"messages": formatted_messages})

        # B) Full-Session Dialogue Sequence Samples (Start to End of a session)
        if include_full_sessions and len(filtered_session) >= 2:
            full_session_msgs = [{"role": "system", "content": system_prompt}]
            user_buffer = []

            for s_msg in filtered_session:
                s_sender = s_msg["sender"].strip()
                s_lower = s_sender.lower()
                s_content = s_msg["content"].strip()

                if not s_content:
                    continue

                if s_lower in target_friend_lowers:
                    if user_buffer:
                        full_session_msgs.append({"role": "user", "content": "\n".join(user_buffer)})
                        user_buffer = []
                    full_session_msgs.append({"role": "assistant", "content": s_content})
                else:
                    prefix = f"{s_sender}: " if (user_names_lowers and len(user_names_lowers) > 1) else ""
                    user_buffer.append(f"{prefix}{s_content}")

            # Ensure valid dialogue format ending with assistant turn
            if full_session_msgs[-1]["role"] == "assistant" and len(full_session_msgs) >= 3:
                sample_str = json.dumps(full_session_msgs, ensure_ascii=False)
                if sample_str not in seen_hashes:
                    seen_hashes.add(sample_str)
                    dataset_samples.append({"messages": full_session_msgs})

    # Shuffle and split train / validation sets
    random.seed(42)
    random.shuffle(dataset_samples)

    split_idx = int(len(dataset_samples) * (1 - val_split))
    train_data = dataset_samples[:split_idx]
    val_data = dataset_samples[split_idx:]

    avg_len = round(sum(len(s) for s in sessions) / len(sessions), 1) if sessions else 0.0

    return {
        "train": train_data,
        "val": val_data,
        "total_samples": len(dataset_samples),
        "train_samples": len(train_data),
        "val_samples": len(val_data),
        "total_sessions": len(sessions),
        "avg_session_length": avg_len,
        "session_gap_minutes": session_gap_minutes,
        "target_friend": target_friend,
        "user_names": user_aliases
    }

def save_dataset_jsonl(dataset_dict: Dict[str, Any], train_path: str, val_path: str):
    """Saves generated dataset to JSONL files for Hugging Face / TRL SFTTrainer."""
    with open(train_path, "w", encoding="utf-8") as f:
        for item in dataset_dict["train"]:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    with open(val_path, "w", encoding="utf-8") as f:
        for item in dataset_dict["val"]:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

