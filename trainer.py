import os
import sys
import json
import time
import torch
import logging
from typing import Dict, Any, Callable, Optional

# Enforce UTF-8 stdio on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

STATUS_FILE = "training_status.json"

def update_status(status_dict: Dict[str, Any]):
    """Atomic write of training progress for real-time web UI streaming."""
    try:
        tmp_file = STATUS_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(status_dict, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, STATUS_FILE)
    except Exception as e:
        logger.error(f"Failed to write status file: {e}")

class WebProgressCallback:
    """Callback for Hugging Face Trainer to emit live metrics to Web UI."""
    def __init__(self, total_epochs: int, output_dir: str):
        self.total_epochs = total_epochs
        self.output_dir = output_dir
        self.start_time = time.time()
        self.logs_history = []

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None:
            return

        epoch = logs.get("epoch", state.epoch if state.epoch else 0.0)
        loss = logs.get("loss", None)
        learning_rate = logs.get("learning_rate", None)
        step = state.global_step
        max_steps = state.max_steps

        gpu_mem_used_gb = 0.0
        gpu_mem_total_gb = 16.0
        if torch.cuda.is_available():
            gpu_mem_used_gb = round(torch.cuda.memory_allocated() / (1024 ** 3), 2)
            gpu_mem_total_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 2)

        elapsed = time.time() - self.start_time
        progress_pct = round((step / max_steps) * 100, 1) if max_steps > 0 else 0

        metric_entry = {
            "step": step,
            "max_steps": max_steps,
            "epoch": round(epoch, 2),
            "total_epochs": self.total_epochs,
            "loss": round(loss, 4) if loss is not None else None,
            "learning_rate": learning_rate,
            "gpu_mem_used_gb": gpu_mem_used_gb,
            "gpu_mem_total_gb": gpu_mem_total_gb,
            "elapsed_seconds": round(elapsed, 1),
            "progress_pct": progress_pct
        }

        if loss is not None:
            self.logs_history.append(metric_entry)

        status = {
            "state": "running",
            "progress_pct": progress_pct,
            "current_step": step,
            "max_steps": max_steps,
            "current_epoch": round(epoch, 2),
            "total_epochs": self.total_epochs,
            "latest_loss": round(loss, 4) if loss is not None else (self.logs_history[-1]["loss"] if self.logs_history else None),
            "gpu_mem_used_gb": gpu_mem_used_gb,
            "gpu_mem_total_gb": gpu_mem_total_gb,
            "logs_history": self.logs_history[-50:], # Last 50 data points for Chart.js
            "output_dir": self.output_dir,
            "message": f"Step {step}/{max_steps} - Epoch {round(epoch,2)} - Loss: {round(loss,4) if loss else 'N/A'}"
        }
        update_status(status)

    def on_step_end(self, args, state, control, **kwargs):
        step = state.global_step
        max_steps = state.max_steps
        epoch = state.epoch if state.epoch else 0.0

        gpu_mem_used_gb = 0.0
        gpu_mem_total_gb = 16.0
        if torch.cuda.is_available():
            gpu_mem_used_gb = round(torch.cuda.memory_allocated() / (1024 ** 3), 2)
            gpu_mem_total_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 2)

        elapsed = time.time() - self.start_time
        progress_pct = round((step / max_steps) * 100, 1) if max_steps > 0 else 0
        latest_loss = self.logs_history[-1]["loss"] if self.logs_history else None

    def on_train_begin(self, args, state, control, **kwargs):
        step = state.global_step
        max_steps = state.max_steps
        gpu_mem_used_gb = round(torch.cuda.memory_allocated() / (1024 ** 3), 2) if torch.cuda.is_available() else 0.0
        status = {
            "state": "running",
            "progress_pct": 1,
            "current_step": step,
            "max_steps": max_steps,
            "current_epoch": 0.0,
            "total_epochs": self.total_epochs,
            "latest_loss": None,
            "gpu_mem_used_gb": gpu_mem_used_gb,
            "gpu_mem_total_gb": 16.0,
            "logs_history": [],
            "output_dir": self.output_dir,
            "message": f"Training loop active! Target: {max_steps} steps ({self.total_epochs} epochs)..."
        }
        update_status(status)

    def on_step_begin(self, args, state, control, **kwargs):
        step = state.global_step + 1
        max_steps = state.max_steps
        epoch = state.epoch if state.epoch else 0.0
        progress_pct = round(((step - 1) / max_steps) * 100, 1) if max_steps > 0 else 0
        latest_loss = self.logs_history[-1]["loss"] if self.logs_history else None
        gpu_mem_used_gb = round(torch.cuda.memory_allocated() / (1024 ** 3), 2) if torch.cuda.is_available() else 0.0

        if step == 1 and latest_loss is None:
            step_msg = f"Step 1/{max_steps} (Epoch {round(epoch,2)}) - Warming up CUDA kernels & computing loss (takes ~25-30s)..."
        else:
            step_msg = f"Executing Step {step}/{max_steps} (Epoch {round(epoch,2)}) - Loss: {round(latest_loss, 4) if latest_loss is not None else 'Computing...'}"

        status = {
            "state": "running",
            "progress_pct": progress_pct,
            "current_step": step - 1,
            "max_steps": max_steps,
            "current_epoch": round(epoch, 2),
            "total_epochs": self.total_epochs,
            "latest_loss": latest_loss,
            "gpu_mem_used_gb": gpu_mem_used_gb,
            "gpu_mem_total_gb": 16.0,
            "logs_history": self.logs_history[-50:],
            "output_dir": self.output_dir,
            "message": step_msg
        }
        update_status(status)

def train_persona_model(
    train_jsonl_path: str,
    val_jsonl_path: str,
    base_model_name: str = "Qwen/Qwen2.5-7B-Instruct",
    output_dir: str = "./trained_persona",
    epochs: int = 3,
    batch_size: int = 2,
    gradient_accumulation_steps: int = 4,
    learning_rate: float = 2e-4,
    lora_r: int = 16,
    lora_alpha: int = 32,
    max_seq_length: int = 1024,
    resume_adapter_path: Optional[str] = None
):
    """
    Fine-tunes a persona LLM using QLoRA 4-bit quantization on NVIDIA RTX 4080 Super (16GB VRAM).
    Supports initial training from base model as well as continued fine-tuning from an existing LoRA adapter.
    """
    try:
        update_status({
            "state": "initializing",
            "progress_pct": 0,
            "message": "Step 1/4: Loading dataset into memory...",
            "logs_history": []
        })

        from datasets import load_dataset
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainerCallback
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, PeftModel
        from trl import SFTTrainer, SFTConfig

        logger.info(f"Starting QLoRA fine-tuning for {base_model_name}...")

        # 1. Load Dataset
        dataset = load_dataset("json", data_files={"train": train_jsonl_path, "validation": val_jsonl_path})
        logger.info(f"Loaded dataset: {len(dataset['train'])} train, {len(dataset['validation'])} val samples.")

        # 2. Configure 4-bit Quantization (NF4) for 16GB VRAM optimization
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16 if (torch.cuda.is_available() and torch.cuda.is_bf16_supported()) else torch.float16,
            bnb_4bit_use_double_quant=True
        ) if torch.cuda.is_available() else None

        # 3. Load Base Model & Tokenizer
        step_msg = f"Step 2/4: Loading 4-bit base model '{base_model_name}' into GPU VRAM..."
        if resume_adapter_path and os.path.exists(resume_adapter_path):
            step_msg = f"Step 2/4: Loading base model '{base_model_name}' + existing LoRA weights from '{resume_adapter_path}'..."

        update_status({
            "state": "initializing",
            "progress_pct": 0,
            "message": step_msg,
            "logs_history": []
        })

        logger.info(f"Downloading/Loading base model {base_model_name}...")
        tokenizer = AutoTokenizer.from_pretrained(base_model_name, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        if torch.cuda.is_available():
            model = AutoModelForCausalLM.from_pretrained(
                base_model_name,
                quantization_config=bnb_config,
                device_map="auto",
                trust_remote_code=True
            )
            model = prepare_model_for_kbit_training(model)
        else:
            model = AutoModelForCausalLM.from_pretrained(
                base_model_name,
                torch_dtype=torch.float32,
                device_map="cpu",
                trust_remote_code=True
            )

        # Handle continued fine-tuning from pre-existing LoRA adapter
        is_continued_training = False
        if resume_adapter_path and os.path.exists(resume_adapter_path):
            logger.info(f"Loading existing LoRA adapter from {resume_adapter_path} for continued fine-tuning...")
            model = PeftModel.from_pretrained(model, resume_adapter_path, is_trainable=True)
            for name, param in model.named_parameters():
                if "lora_" in name:
                    param.requires_grad = True
            is_continued_training = True
            peft_config = None
        else:
            peft_config = LoraConfig(
                r=lora_r,
                lora_alpha=lora_alpha,
                target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
                lora_dropout=0.05,
                bias="none",
                task_type="CAUSAL_LM"
            )

        # 4. Pre-format conversation messages into text strings
        update_status({
            "state": "initializing",
            "progress_pct": 0,
            "message": "Step 3/4: Formatting chat dataset into chat template strings...",
            "logs_history": []
        })

        def format_chat_item(example):
            return {"text": tokenizer.apply_chat_template(example["messages"], tokenize=False)}

        dataset = dataset.map(format_chat_item, remove_columns=["messages"])

        # 6. Hugging Face / TRL SFT Trainer configuration
        web_callback = WebProgressCallback(total_epochs=epochs, output_dir=output_dir)

        class HFTrainerProgressBridge(TrainerCallback):
            def on_train_begin(self, args, state, control, **kwargs):
                web_callback.on_train_begin(args, state, control, **kwargs)

            def on_step_begin(self, args, state, control, **kwargs):
                web_callback.on_step_begin(args, state, control, **kwargs)

            def on_log(self, args, state, control, logs=None, **kwargs):
                web_callback.on_log(args, state, control, logs=logs, **kwargs)

            def on_step_end(self, args, state, control, **kwargs):
                web_callback.on_step_end(args, state, control, **kwargs)

        training_args = SFTConfig(
            output_dir=output_dir,
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=gradient_accumulation_steps,
            learning_rate=learning_rate,
            logging_steps=1,
            save_strategy="epoch",
            eval_strategy="epoch",
            fp16=not (torch.cuda.is_available() and torch.cuda.is_bf16_supported()),
            bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
            dataset_text_field="text",
            max_length=max_seq_length,
            packing=False,
            report_to="none"
        )

        trainer = SFTTrainer(
            model=model,
            train_dataset=dataset["train"],
            eval_dataset=dataset["validation"],
            peft_config=peft_config,
            processing_class=tokenizer,
            args=training_args,
            callbacks=[HFTrainerProgressBridge()]
        )

        update_status({
            "state": "running",
            "progress_pct": 1,
            "message": "Step 4/4: Launching training execution loop...",
            "logs_history": []
        })

        # 6. Execute Fine-Tuning
        trainer.train()

        # 7. Save Final LoRA Adapter
        trainer.model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)

        # Register in model_manager
        preset_name = os.path.basename(output_dir).replace("_", " ").title()
        preset_id = os.path.basename(output_dir)
        try:
            from model_manager import register_preset
            register_preset(
                preset_id=preset_id,
                name=preset_name,
                base_model=base_model_name,
                adapter_path=output_dir
            )
        except Exception as me:
            logger.warning(f"Could not auto-register preset: {me}")

        logger.info(f"Training completed! LoRA adapter saved to {output_dir}")
        update_status({
            "state": "completed",
            "progress_pct": 100,
            "message": f"Training completed successfully! Adapter saved at: {output_dir}",
            "output_dir": output_dir
        })
    except Exception as e:
        import traceback
        err_msg = f"Training Error: {str(e)}"
        logger.error(traceback.format_exc())
        update_status({
            "state": "error",
            "progress_pct": 0,
            "message": err_msg
        })

if __name__ == "__main__":
    if len(sys.argv) > 2:
        train_path = sys.argv[1]
        val_path = sys.argv[2]
        base_model = sys.argv[3] if len(sys.argv) > 3 else "Qwen/Qwen2.5-7B-Instruct"
        out_dir = sys.argv[4] if len(sys.argv) > 4 else "./trained_persona/my_model"
        epochs = int(sys.argv[5]) if len(sys.argv) > 5 else 3
        batch_size = int(sys.argv[6]) if len(sys.argv) > 6 else 2
        grad_accum = int(sys.argv[7]) if len(sys.argv) > 7 else 4
        lr = float(sys.argv[8]) if len(sys.argv) > 8 else 2e-4
        lora_r = int(sys.argv[9]) if len(sys.argv) > 9 else 16
        lora_alpha = int(sys.argv[10]) if len(sys.argv) > 10 else 32
        resume_adapter_raw = sys.argv[11] if len(sys.argv) > 11 else None
        resume_adapter = resume_adapter_raw if resume_adapter_raw and resume_adapter_raw.lower() not in ["none", "", "null"] else None

        train_persona_model(
            train_jsonl_path=train_path,
            val_jsonl_path=val_path,
            base_model_name=base_model,
            output_dir=out_dir,
            epochs=epochs,
            batch_size=batch_size,
            gradient_accumulation_steps=grad_accum,
            learning_rate=lr,
            lora_r=lora_r,
            lora_alpha=lora_alpha,
            resume_adapter_path=resume_adapter
        )
    else:
        print("Usage: python trainer.py <train.jsonl> <val.jsonl> [base_model] [output_dir] [epochs] [batch_size] [grad_accum] [lr] [lora_r] [lora_alpha] [resume_adapter_path]")
