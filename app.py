import os
import sys
import json
import time
import shutil
import asyncio
import subprocess
import psutil
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from whatsapp_parser import group_into_conversations
from chat_parser import parse_chat_file
from dataset_builder import build_chat_dataset, save_dataset_jsonl, DEFAULT_HEBREW_SYSTEM_PROMPT
from inference_engine import engine
from model_manager import (
    scan_and_sync_presets,
    register_preset,
    delete_preset,
    zip_preset,
    extract_and_import_preset,
    sanitize_preset_id,
    MODELS_DIR
)

app = FastAPI(title="WhatsApp Persona AI Fine-Tuner", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "./uploads"
DATASET_DIR = "./datasets"
TRAIN_OUTPUT_DIR = "./trained_persona"
STATUS_FILE = "training_status.json"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATASET_DIR, exist_ok=True)
os.makedirs(TRAIN_OUTPUT_DIR, exist_ok=True)

current_chat_data: Dict[str, Any] = {}
current_dataset_meta: Dict[str, Any] = {}
active_training_proc: Optional[subprocess.Popen] = None

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>UI loading error: static/index.html not found.</h1>")


@app.get("/api/system-status")
async def get_system_status():
    gpu_available = False
    gpu_name = "N/A"
    vram_used_gb = 0.0
    vram_total_gb = 0.0

    try:
        import torch
        gpu_available = torch.cuda.is_available()
        if gpu_available:
            gpu_name = torch.cuda.get_device_name(0)
            vram_used_gb = round(torch.cuda.memory_allocated(0) / (1024 ** 3), 2)
            vram_total_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 2)
    except Exception:
        pass

    ram = psutil.virtual_memory()

    training_info = {"state": "idle", "progress_pct": 0}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                training_info = json.load(f)
        except Exception:
            pass

    return {
        "gpu_available": gpu_available,
        "gpu_name": gpu_name,
        "vram_used_gb": vram_used_gb,
        "vram_total_gb": vram_total_gb,
        "ram_used_gb": round(ram.used / (1024 ** 3), 2),
        "ram_total_gb": round(ram.total / (1024 ** 3), 2),
        "training_info": training_info,
        "model_loaded": engine.is_loaded(),
        "loaded_base_model": engine.loaded_base_name,
        "loaded_adapter": engine.loaded_adapter_path
    }


@app.post("/api/upload-chat")
async def upload_chat(
    files: Optional[List[UploadFile]] = File(None),
    file: Optional[UploadFile] = File(None)
):
    global current_chat_data

    upload_list = []
    if files:
        upload_list.extend(files)
    if file and file not in upload_list:
        upload_list.append(file)

    if not upload_list:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    from collections import Counter
    all_messages = []
    combined_sender_counts = Counter()
    total_raw_lines = 0
    hebrew_count = 0
    english_count = 0
    media_count = 0
    urls_removed_count = 0
    chat_sources = []
    parsed_filenames = []

    for upload_file in upload_list:
        if not upload_file.filename:
            continue

        file_path = os.path.join(UPLOAD_DIR, upload_file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)

        parsed_res = parse_chat_file(file_path)
        stats = parsed_res.get("stats", {})

        all_messages.extend(parsed_res.get("messages", []))
        total_raw_lines += stats.get("total_raw_lines", 0)
        hebrew_count += stats.get("hebrew_messages", 0)
        english_count += stats.get("english_messages", 0)
        media_count += stats.get("media_omitted_count", 0)
        urls_removed_count += stats.get("urls_removed_count", 0)

        for sender, count in stats.get("sender_counts", {}).items():
            combined_sender_counts[sender] += count

        src = stats.get("chat_source", "Chat")
        if src not in chat_sources:
            chat_sources.append(src)
        parsed_filenames.append(upload_file.filename)

    top_senders = [s for s, c in combined_sender_counts.most_common(20)]

    merged_stats = {
        "total_messages": len(all_messages),
        "total_raw_lines": total_raw_lines,
        "sender_counts": dict(combined_sender_counts),
        "top_senders": top_senders,
        "hebrew_messages": hebrew_count,
        "english_messages": english_count,
        "media_omitted_count": media_count,
        "urls_removed_count": urls_removed_count,
        "chat_source": " & ".join(chat_sources) if chat_sources else "WhatsApp & Discord",
        "chat_sources_list": chat_sources,
        "files_count": len(parsed_filenames),
        "filenames": parsed_filenames
    }

    current_chat_data = {
        "stats": merged_stats,
        "messages": all_messages
    }

    cache_path = os.path.join(UPLOAD_DIR, "latest_parsed.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(current_chat_data, f, ensure_ascii=False)

    return {
        "status": "success",
        "filenames": parsed_filenames,
        "stats": merged_stats,
        "sample_messages": all_messages[:20]
    }


class DatasetBuildRequest(BaseModel):
    target_friend: Any
    system_prompt: Optional[str] = None
    context_turns: int = 5
    val_split: float = 0.1
    session_gap_minutes: int = 60
    include_full_sessions: bool = True


@app.post("/api/build-dataset")
async def create_dataset(req: DatasetBuildRequest):
    global current_chat_data, current_dataset_meta

    if not current_chat_data or "messages" not in current_chat_data:
        cache_path = os.path.join(UPLOAD_DIR, "latest_parsed.json")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                current_chat_data = json.load(f)
        else:
            raise HTTPException(status_code=400, detail="No WhatsApp chat uploaded yet.")

    dataset_dict = build_chat_dataset(
        messages=current_chat_data["messages"],
        target_friend=req.target_friend,
        system_prompt=req.system_prompt,
        context_turns=req.context_turns,
        val_split=req.val_split,
        session_gap_minutes=req.session_gap_minutes,
        include_full_sessions=req.include_full_sessions
    )

    train_path = os.path.join(DATASET_DIR, "train.jsonl")
    val_path = os.path.join(DATASET_DIR, "val.jsonl")
    save_dataset_jsonl(dataset_dict, train_path, val_path)

    current_dataset_meta = {
        "train_path": train_path,
        "val_path": val_path,
        "stats": dataset_dict,
        "sample_train_item": dataset_dict["train"][0] if dataset_dict["train"] else None
    }

    return {
        "status": "success",
        "total_samples": dataset_dict["total_samples"],
        "train_samples": dataset_dict["train_samples"],
        "val_samples": dataset_dict["val_samples"],
        "total_sessions": dataset_dict["total_sessions"],
        "avg_session_length": dataset_dict["avg_session_length"],
        "session_gap_minutes": dataset_dict["session_gap_minutes"],
        "sample_preview": dataset_dict["train"][:3] if dataset_dict["train"] else []
    }


class TrainStartRequest(BaseModel):
    base_model_name: str = "Qwen/Qwen2.5-7B-Instruct"
    persona_name: Optional[str] = None
    system_prompt: Optional[str] = None
    epochs: int = 3
    batch_size: int = 2
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    lora_r: int = 16
    lora_alpha: int = 32
    max_seq_length: int = 1024
    train_mode: str = "new"  # "new" or "continue"
    resume_preset_id: Optional[str] = None


@app.post("/api/start-training")
async def start_training(req: TrainStartRequest):
    global active_training_proc

    train_path = os.path.join(DATASET_DIR, "train.jsonl")
    val_path = os.path.join(DATASET_DIR, "val.jsonl")

    if not os.path.exists(train_path):
        raise HTTPException(status_code=400, detail="Dataset train.jsonl not found. Please build dataset first.")

    resume_adapter_path = None
    if req.train_mode == "continue" and req.resume_preset_id:
        presets = scan_and_sync_presets()
        target = next((p for p in presets if p["id"] == req.resume_preset_id), None)
        if target and os.path.exists(target["adapter_path"]):
            resume_adapter_path = target["adapter_path"]
            if target.get("base_model"):
                req.base_model_name = target["base_model"]

    name = req.persona_name.strip() if req.persona_name else "My Friend AI"
    preset_id = sanitize_preset_id(name)
    output_dir = os.path.join(TRAIN_OUTPUT_DIR, preset_id).replace("\\", "/")

    # Unload inference model from GPU VRAM to ensure trainer gets 100% VRAM
    try:
        engine.unload_model()
    except Exception:
        pass

    start_msg = f"Initializing QLoRA fine-tuning for '{name}' using {req.base_model_name}..."
    if resume_adapter_path:
        start_msg = f"Initializing continued QLoRA fine-tuning for '{name}' from existing model '{req.resume_preset_id}'..."

    initial_status = {
        "state": "starting",
        "progress_pct": 0,
        "message": start_msg,
        "logs_history": []
    }
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(initial_status, f, ensure_ascii=False)

    python_exe = sys.executable
    if os.path.exists(r"C:\Users\yahli\anaconda3\envs\whatsapp_ai\python.exe"):
        python_exe = r"C:\Users\yahli\anaconda3\envs\whatsapp_ai\python.exe"

    cmd = [
        python_exe,
        "trainer.py",
        train_path,
        val_path,
        req.base_model_name,
        output_dir,
        str(req.epochs),
        str(req.batch_size),
        str(req.gradient_accumulation_steps),
        str(req.learning_rate),
        str(req.lora_r),
        str(req.lora_alpha),
        resume_adapter_path or "None"
    ]

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    try:
        active_training_proc = subprocess.Popen(cmd, cwd=os.getcwd(), env=env)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to launch trainer subprocess: {e}")

    # Register initial metadata in registry with system prompt
    register_preset(
        preset_id=preset_id,
        name=name,
        base_model=req.base_model_name,
        adapter_path=output_dir,
        system_prompt=req.system_prompt or ""
    )

    return {
        "status": "training_started",
        "preset_id": preset_id,
        "persona_name": name,
        "base_model": req.base_model_name,
        "train_mode": req.train_mode,
        "resumed_from": req.resume_preset_id if resume_adapter_path else None,
        "pid": active_training_proc.pid
    }


@app.post("/api/stop-training")
async def stop_training():
    global active_training_proc
    if active_training_proc and active_training_proc.poll() is None:
        active_training_proc.terminate()
        active_training_proc = None

    status = {
        "state": "stopped",
        "progress_pct": 0,
        "message": "Training was manually stopped by user."
    }
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False)

    return {"status": "stopped"}


@app.get("/api/training-logs-stream")
async def stream_training_logs():
    async def log_generator():
        while True:
            if os.path.exists(STATUS_FILE):
                try:
                    with open(STATUS_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                    if data.get("state") in ["completed", "error", "stopped"]:
                        break
                except Exception:
                    pass
            await asyncio.sleep(1.0)

    return StreamingResponse(log_generator(), media_type="text/event-stream")


# --- MODEL PRESETS & EXPORT / IMPORT ENDPOINTS ---

@app.get("/api/presets")
async def list_presets():
    """Scans disk and lists all registered model presets."""
    presets = scan_and_sync_presets()
    return {"presets": presets}


class UpdatePromptRequest(BaseModel):
    preset_id: str
    system_prompt: str

@app.post("/api/update-preset-prompt")
async def update_prompt_endpoint(req: UpdatePromptRequest):
    """Updates the custom system prompt for a specific model preset."""
    from model_manager import update_preset_prompt
    success = update_preset_prompt(req.preset_id, req.system_prompt)
    if not success:
        raise HTTPException(status_code=404, detail=f"Preset '{req.preset_id}' not found.")
    return {"status": "success", "preset_id": req.preset_id, "system_prompt": req.system_prompt}


class RenamePresetRequest(BaseModel):
    preset_id: str
    new_name: str

@app.post("/api/rename-preset")
async def rename_preset_endpoint(req: RenamePresetRequest):
    """Renames an existing model preset."""
    from model_manager import rename_preset
    updated = rename_preset(req.preset_id, req.new_name)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Preset '{req.preset_id}' not found.")
    return {"status": "success", "preset": updated}


class LoadModelRequest(BaseModel):
    base_model_name: str = "Qwen/Qwen2.5-7B-Instruct"
    adapter_path: Optional[str] = "./trained_persona/final_adapter"
    preset_id: Optional[str] = None


@app.post("/api/load-model")
async def load_model_endpoint(req: LoadModelRequest):
    """Loads base model + fine-tuned LoRA preset into VRAM."""
    adapter_to_use = None
    if req.adapter_path and os.path.exists(req.adapter_path):
        adapter_to_use = req.adapter_path
    elif req.preset_id:
        presets = scan_and_sync_presets()
        for p in presets:
            if p["id"] == req.preset_id and os.path.exists(p["adapter_path"]):
                adapter_to_use = p["adapter_path"]
                req.base_model_name = p.get("base_model", req.base_model_name)
                break

    try:
        engine.load_model_and_adapter(req.base_model_name, adapter_to_use)
        return {
            "status": "success",
            "message": f"Successfully loaded {req.base_model_name}" + (f" with adapter {adapter_to_use}" if adapter_to_use else " (base model)")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load model: {e}")


@app.get("/api/export-model/{preset_id}")
async def export_model_endpoint(preset_id: str):
    """Packages fine-tuned model preset into a zip download."""
    presets = scan_and_sync_presets()
    target_preset = next((p for p in presets if p["id"] == preset_id), None)

    if not target_preset:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found.")

    zip_filename = f"{preset_id}_lora_weights.zip"
    zip_path = os.path.join(UPLOAD_DIR, zip_filename)

    success = zip_preset(preset_id, zip_path)
    if not success or not os.path.exists(zip_path):
        raise HTTPException(status_code=500, detail="Failed to package model files into zip archive.")

    return FileResponse(
        path=zip_path,
        filename=zip_filename,
        media_type="application/zip"
    )


@app.post("/api/import-model")
async def import_model_endpoint(
    preset_name: str = Form(...),
    file: UploadFile = File(...)
):
    """Imports a .zip model file, extracts weights, and registers it as a preset."""
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Import file must be a .zip archive containing model weights.")

    temp_zip_path = os.path.join(UPLOAD_DIR, f"temp_import_{int(time.time())}.zip")
    with open(temp_zip_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        preset_info = extract_and_import_preset(temp_zip_path, preset_name)
        if os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)

        return {
            "status": "success",
            "message": f"Successfully imported preset '{preset_name}'!",
            "preset": preset_info
        }
    except Exception as e:
        if os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)
        raise HTTPException(status_code=500, detail=f"Failed to import model zip: {e}")


@app.delete("/api/delete-preset/{preset_id}")
async def delete_preset_endpoint(preset_id: str):
    """Deletes a preset and its weights directory."""
    success = delete_preset(preset_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found.")
    return {"status": "deleted", "preset_id": preset_id}


class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    top_p: float = 0.9

@app.post("/api/chat-stream")
async def chat_stream_endpoint(req: ChatRequest):
    full_messages = []
    if req.system_prompt:
        full_messages.append({"role": "system", "content": req.system_prompt})
    
    for m in req.messages:
        full_messages.append({"role": m.role, "content": m.content})

    async def token_generator():
        if not engine.is_loaded():
            demo_reply = "אהלן! אני המודל המאומן של החבר שלך. כרגע לא טענת מודל לזכרון ה-GPU, אז זה מענה סימולציה מהיר. ברגע שתאמן ותטען את המודל, אענה בול כמוהו!"
            for char in demo_reply:
                yield f"data: {json.dumps({'token': char})}\n\n"
                await asyncio.sleep(0.02)
            return

        for token in engine.generate_response_stream(
            full_messages,
            temperature=req.temperature,
            top_p=req.top_p
        ):
            yield f"data: {json.dumps({'token': token})}\n\n"
            await asyncio.sleep(0.01)

    return StreamingResponse(token_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
