import os
import sys
import re
import json
import torch
import logging
import threading
from typing import Generator, List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Patterns for stripping YouTube Shorts, Instagram Reels, TikTok and general web links
URL_PATTERNS = [
    r"(?:https?://)?(?:www\.)?(?:youtube\.com/shorts/|youtube\.com/watch\?v=|youtu\.be/|youtube\.com/)[^\s]+",
    r"(?:https?://)?(?:www\.)?(?:instagram\.com/reel/|instagram\.com/reels/|instagram\.com/p/|instagram\.com/stories/|instagram\.com/|instagr\.am/)[^\s]+",
    r"(?:https?://)?(?:www\.)?(?:tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)/[^\s]+",
    r"(?:https?://)?(?:open\.)?spotify\.com/[^\s]+",
    r"https?://[^\s]+",
    r"www\.[^\s]+",
]

def clean_generated_text(text: str) -> str:
    """Strips YouTube, IG, TikTok, and web URLs from model output."""
    if not text:
        return ""
    cleaned = text
    for pattern in URL_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned

class PersonaInferenceEngine:
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.loaded_base_name = None
        self.loaded_adapter_path = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._lock = threading.Lock()

    def is_loaded(self) -> bool:
        return getattr(self, "model", None) is not None and getattr(self, "tokenizer", None) is not None

    def load_model_and_adapter(self, base_model_name: str, adapter_path: Optional[str] = None):
        """Loads base model and optional PEFT LoRA adapter into VRAM thread-safely."""
        with self._lock:
            try:
                from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TextIteratorStreamer
                from peft import PeftModel
            except ImportError as e:
                logger.error(f"Missing dependency for inference: {e}")
                raise RuntimeError(f"Dependencies not installed: {e}")

            logger.info(f"Loading base model {base_model_name} on device {self.device}...")

            self.model = None
            self.tokenizer = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16 if (torch.cuda.is_available() and torch.cuda.is_bf16_supported()) else torch.float16,
                bnb_4bit_use_double_quant=True
            ) if torch.cuda.is_available() else None

            tokenizer = AutoTokenizer.from_pretrained(base_model_name, trust_remote_code=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            if torch.cuda.is_available():
                base_model = AutoModelForCausalLM.from_pretrained(
                    base_model_name,
                    quantization_config=bnb_config,
                    device_map="auto",
                    trust_remote_code=True
                )
            else:
                base_model = AutoModelForCausalLM.from_pretrained(
                    base_model_name,
                    torch_dtype=torch.float32,
                    device_map="cpu",
                    trust_remote_code=True
                )

            adapter_config_file = os.path.join(adapter_path, "adapter_config.json") if adapter_path else None
            if adapter_path and os.path.exists(adapter_path) and os.path.exists(adapter_config_file):
                try:
                    logger.info(f"Applying fine-tuned LoRA adapter from {adapter_path}...")
                    loaded_model = PeftModel.from_pretrained(base_model, adapter_path)
                    self.loaded_adapter_path = adapter_path
                except Exception as ae:
                    logger.warning(f"Could not load LoRA adapter from {adapter_path}: {ae}. Using base model.")
                    loaded_model = base_model
                    self.loaded_adapter_path = None
            else:
                loaded_model = base_model
                self.loaded_adapter_path = None

            loaded_model.eval()
            self.tokenizer = tokenizer
            self.model = loaded_model
            self.loaded_base_name = base_model_name
            logger.info("Persona Model loaded successfully!")

    def unload_model(self):
        """Frees GPU VRAM when launching fine-tuning."""
        with self._lock:
            self.model = None
            self.tokenizer = None
            self.loaded_base_name = None
            self.loaded_adapter_path = None
            import gc
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("Inference model unloaded from GPU memory.")

    def generate_response_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_new_tokens: int = 512
    ) -> Generator[str, None, None]:
        """
        Streams generated tokens for a multi-turn chat conversation with URL filtering.
        """
        if not self.is_loaded():
            yield "[Error: Model not loaded. Please load a model or adapter in the control panel.]"
            return

        from transformers import TextIteratorStreamer
        from threading import Thread

        # Apply chat template
        try:
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
        except Exception:
            prompt = ""
            for m in messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                prompt += f"<|im_start|>{role}\n{content}<|im_end|>\n"
            prompt += "<|im_start|>assistant\n"

        inputs = self.tokenizer([prompt], return_tensors="pt").to(self.device)
        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)

        generation_kwargs = dict(
            inputs,
            streamer=streamer,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            do_sample=temperature > 0.0,
            pad_token_id=self.tokenizer.pad_token_id
        )

        thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()

        accumulated_text = ""
        for new_text in streamer:
            accumulated_text += new_text
            cleaned = clean_generated_text(new_text)
            if cleaned:
                yield cleaned

# Global singleton instance
engine = PersonaInferenceEngine()
