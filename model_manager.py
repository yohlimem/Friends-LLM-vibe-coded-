import os
import re
import json
import shutil
import zipfile
import time
from typing import List, Dict, Any, Optional

MODELS_DIR = "./trained_persona"
REGISTRY_FILE = os.path.join(MODELS_DIR, "models_registry.json")

def ensure_models_dir():
    os.makedirs(MODELS_DIR, exist_ok=True)
    if not os.path.exists(REGISTRY_FILE):
        save_registry({})

def load_registry() -> Dict[str, Any]:
    ensure_models_dir()
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_registry(registry: Dict[str, Any]):
    os.makedirs(MODELS_DIR, exist_ok=True)
    tmp_file = REGISTRY_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, REGISTRY_FILE)

def sanitize_preset_id(name: str) -> str:
    clean = re.sub(r'[^\w\s-]', '', name).strip().lower()
    clean = re.sub(r'[-\s]+', '_', clean)
    return clean or f"preset_{int(time.time())}"

def scan_and_sync_presets() -> List[Dict[str, Any]]:
    ensure_models_dir()
    registry = load_registry()
    updated = False

    # Clean up stale registry entries (e.g. root ./trained_persona or deleted folders)
    stale_ids = []
    for pid, pdata in registry.items():
        apath = pdata.get("adapter_path", "")
        if apath in [MODELS_DIR, "./trained_persona", "trained_persona"] or not os.path.exists(apath):
            stale_ids.append(pid)
    for pid in stale_ids:
        del registry[pid]
        updated = True

    for entry in os.listdir(MODELS_DIR):
        if entry.startswith("checkpoint-") or entry == "models_registry.json" or entry.endswith(".tmp") or entry.endswith(".zip"):
            continue
        folder_path = os.path.join(MODELS_DIR, entry)
        if os.path.isdir(folder_path):
            config_path = os.path.join(folder_path, "adapter_config.json")
            meta_path = os.path.join(folder_path, "adapter_config_meta.json")
            
            if os.path.exists(config_path):
                preset_id = entry
                existing_entry = registry.get(preset_id, {})
                display_name = existing_entry.get("name", entry.replace("_", " ").title())
                base_model = existing_entry.get("base_model", "Qwen/Qwen2.5-7B-Instruct")
                created_at = existing_entry.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S"))
                system_prompt = existing_entry.get("system_prompt", "")

                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as mf:
                            meta = json.load(mf)
                            display_name = meta.get("name", display_name)
                            base_model = meta.get("base_model", base_model)
                            created_at = meta.get("created_at", created_at)
                            if not system_prompt and meta.get("system_prompt"):
                                system_prompt = meta.get("system_prompt")
                    except Exception:
                        pass

                if preset_id not in registry or registry[preset_id].get("system_prompt") != system_prompt or registry[preset_id].get("name") != display_name:
                    registry[preset_id] = {
                        "id": preset_id,
                        "name": display_name,
                        "base_model": base_model,
                        "adapter_path": folder_path.replace("\\", "/"),
                        "created_at": created_at,
                        "system_prompt": system_prompt
                    }
                    updated = True

    if updated:
        save_registry(registry)

    return list(registry.values())

def register_preset(
    preset_id: str,
    name: str,
    base_model: str,
    adapter_path: str,
    system_prompt: str = ""
) -> Dict[str, Any]:
    registry = load_registry()
    entry = {
        "id": preset_id,
        "name": name,
        "base_model": base_model,
        "adapter_path": adapter_path.replace("\\", "/"),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "system_prompt": system_prompt
    }
    registry[preset_id] = entry
    save_registry(registry)

    meta_path = os.path.join(adapter_path, "adapter_config_meta.json")
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return entry

def update_preset_prompt(preset_id: str, system_prompt: str) -> bool:
    registry = load_registry()
    if preset_id in registry:
        registry[preset_id]["system_prompt"] = system_prompt
        save_registry(registry)
        
        meta_path = os.path.join(registry[preset_id]["adapter_path"], "adapter_config_meta.json")
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(registry[preset_id], f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return True
    return False

def rename_preset(preset_id: str, new_name: str) -> Optional[Dict[str, Any]]:
    registry = load_registry()
    if preset_id in registry:
        registry[preset_id]["name"] = new_name
        save_registry(registry)
        
        meta_path = os.path.join(registry[preset_id]["adapter_path"], "adapter_config_meta.json")
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(registry[preset_id], f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return registry[preset_id]
    return None

def delete_preset(preset_id: str) -> bool:
    registry = load_registry()
    if preset_id in registry:
        adapter_path = registry[preset_id].get("adapter_path")
        del registry[preset_id]
        save_registry(registry)

        if adapter_path and os.path.exists(adapter_path):
            try:
                shutil.rmtree(adapter_path)
            except Exception:
                pass
        return True
    return False

def zip_preset(preset_id: str, output_zip_path: str) -> bool:
    registry = load_registry()
    if preset_id not in registry:
        return False

    adapter_path = registry[preset_id]["adapter_path"]
    if not os.path.exists(adapter_path):
        return False

    with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(adapter_path):
            # Exclude checkpoint subfolders and temp files
            dirs[:] = [d for d in dirs if not d.startswith("checkpoint-")]
            for file in files:
                if file.endswith(".tmp") or file == "models_registry.json" or file.endswith(".zip"):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, adapter_path)
                zipf.write(full_path, rel_path)
    return True

def extract_and_import_preset(zip_file_path: str, custom_name: str, system_prompt: str = "") -> Dict[str, Any]:
    preset_id = sanitize_preset_id(custom_name)
    target_dir = os.path.join(MODELS_DIR, preset_id)
    os.makedirs(target_dir, exist_ok=True)

    with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
        zip_ref.extractall(target_dir)

    meta_path = os.path.join(target_dir, "adapter_config_meta.json")
    base_model = "Qwen/Qwen2.5-7B-Instruct"
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as mf:
                meta = json.load(mf)
                base_model = meta.get("base_model", base_model)
                if not system_prompt:
                    system_prompt = meta.get("system_prompt", "")
        except Exception:
            pass

    return register_preset(
        preset_id=preset_id,
        name=custom_name,
        base_model=base_model,
        adapter_path=target_dir,
        system_prompt=system_prompt
    )
