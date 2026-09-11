"""Gayatri AI — Local LLM provider using llama-cpp-python."""

from __future__ import annotations

import logging
import threading
import time

from core.config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_K,
    DEFAULT_TOP_P,
    LOCAL_MODEL_CONTEXT,
    LOCAL_MODEL_DIR,
    LOCAL_MODEL_FILE,
    LOCAL_MODEL_GPU_LAYERS,
)

logger = logging.getLogger("gayatri.providers.local")

# Gemma 2 chat template tokens
_TURN_START = "<start_of_turn>"
_TURN_END = "<end_of_turn>"
_MODEL_TOKEN = "model"
_USER_TOKEN = "user"
_SYSTEM_TOKEN = "system"


class LocalModelError(Exception):
    """Raised when the local model fails to load or generate."""


def format_gemma_prompt(messages: list[dict]) -> str:
    """Format a list of chat messages into Gemma 2's chat template.

    Args:
        messages: List of {"role": "system|user|assistant", "content": str}

    Returns:
        Formatted prompt string ready for the model.
    """
    parts = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            parts.append(f"{_TURN_START}{_SYSTEM_TOKEN}\n{content}{_TURN_END}\n")
        elif role == "user":
            parts.append(f"{_TURN_START}{_USER_TOKEN}\n{content}{_TURN_END}\n")
        elif role == "assistant":
            parts.append(f"{_TURN_START}{_MODEL_TOKEN}\n{content}{_TURN_END}\n")
    # Always end with model turn so generation follows
    parts.append(f"{_TURN_START}{_MODEL_TOKEN}\n")
    return "".join(parts)


class LocalProvider:
    """Loads and runs a GGUF model via llama-cpp-python.

    Lazy-loads the model on first use. Singleton — load once, reuse.
    Thread-safe model loading and inference synchronization.
    """

    _model = None
    _model_lock = threading.Lock()
    _infer_lock = threading.Lock()
    MODEL_PATH = LOCAL_MODEL_DIR / LOCAL_MODEL_FILE

    @classmethod
    def _load_model(cls, **override_params):
        """Load the GGUF model. Called once.

        Auto-detects hardware if not explicitly overridden.
        Thread-safe singleton loading.
        """
        if cls._model is not None and not override_params:
            return cls._model

        with cls._model_lock:
            if cls._model is not None and not override_params:
                return cls._model

            try:
                from llama_cpp import Llama
            except ImportError:
                raise LocalModelError(
                    "llama-cpp-python not installed. Run: pip install llama-cpp-python"
                )

            model_path = cls.MODEL_PATH
            if not model_path.exists():
                raise LocalModelError(
                    f"Model not found at {model_path}. "
                    "Download the fine-tuned GGUF model first."
                )

            actual_size = model_path.stat().st_size
            if actual_size < 1024 * 1024:
                raise LocalModelError(
                    f"Model file at {model_path} is only {actual_size} bytes — "
                    "the download failed (likely a placeholder). Delete the file and "
                    "re-download via the app's Download button."
                )

            logger.info(f"Loading model: {model_path.name} ({model_path.stat().st_size / 1024 / 1024:.1f} MB)")
            start = time.time()

            # Use override params if provided, otherwise auto-detect
            if override_params:
                n_gpu_layers = override_params.get("n_gpu_layers", LOCAL_MODEL_GPU_LAYERS)
                n_ctx = override_params.get("n_ctx", LOCAL_MODEL_CONTEXT)
                n_threads = override_params.get("n_threads", 4)
            else:
                # Auto-detect hardware
                try:
                    from core.hardware import detect_hardware, recommend_llama_params
                    profile = detect_hardware()
                    model_size_mb = int(model_path.stat().st_size / (1024 * 1024))
                    params = recommend_llama_params(profile, model_size_mb)
                    n_gpu_layers = params.n_gpu_layers
                    n_ctx = params.n_ctx
                    n_threads = params.n_threads
                    logger.info(
                        f"Auto-detected: GPU={profile.gpu_name} "
                        f"(layers={n_gpu_layers}, ctx={n_ctx}, threads={n_threads})"
                    )
                except Exception as exc:
                    logger.warning(f"Hardware detection failed, using defaults: {exc}")
                    n_gpu_layers = LOCAL_MODEL_GPU_LAYERS
                    n_ctx = LOCAL_MODEL_CONTEXT
                    n_threads = 4

            try:
                cls._model = Llama(
                    model_path=str(model_path),
                    n_ctx=n_ctx,
                    n_gpu_layers=n_gpu_layers,
                    verbose=False,
                    n_threads=n_threads,
                )
            except Exception as exc:
                raise LocalModelError(f"Failed to load GGUF model: {exc}") from exc

            elapsed = time.time() - start
            logger.info(f"Model loaded in {elapsed:.1f}s (layers={n_gpu_layers}, ctx={n_ctx})")
            return cls._model

    @classmethod
    def health(cls) -> dict:
        """Return structured health status of the local model without forcing heavy model load."""
        model_path = cls.MODEL_PATH
        if not model_path.exists():
            return {
                "available": False,
                "reason_code": "missing_file",
                "message": "Model file not found. Please download it.",
                "path": str(model_path)
            }

        actual_size = model_path.stat().st_size
        if actual_size < 1024 * 1024:
            return {
                "available": False,
                "reason_code": "invalid_file",
                "message": f"Model file is only {actual_size} bytes, likely a failed download.",
                "path": str(model_path)
            }

        try:
            import llama_cpp  # verify dependency without loading model
        except ImportError:
            return {
                "available": False,
                "reason_code": "missing_dependency",
                "message": "llama-cpp-python not installed. Run: pip install llama-cpp-python",
                "path": str(model_path)
            }

        if cls._model is not None:
            return {
                "available": True,
                "reason_code": "ok",
                "message": "Model is loaded and ready.",
                "path": str(model_path)
            }

        return {
            "available": True,
            "reason_code": "ok",
            "message": "Model file ready to load.",
            "path": str(model_path)
        }

    @classmethod
    def is_available(cls) -> bool:
        """Check if the model file exists and is ready to load."""
        return cls.health()["available"]

    @classmethod
    def stream(cls, prompt: str, **kwargs):
        """Stream tokens from the model. Yields strings."""
        model = cls._load_model()
        max_tokens = kwargs.get("max_tokens", DEFAULT_MAX_TOKENS)
        temperature = kwargs.get("temperature", DEFAULT_TEMPERATURE)
        top_p = kwargs.get("top_p", DEFAULT_TOP_P)
        top_k = kwargs.get("top_k", DEFAULT_TOP_K)
        stop = kwargs.get("stop")
        if not stop:
            stop = ["<end_of_turn>"]

        logger.info(f"Generating: max_tokens={max_tokens}, temp={temperature}")

        try:
            with cls._infer_lock:
                stream = model.create_completion(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    stop=stop,
                    stream=True,
                )
                for chunk in stream:
                    text = chunk["choices"][0].get("text", "")
                    if text:
                        yield text
        except Exception as exc:
            logger.error(f"Generation failed: {exc}")
            raise LocalModelError(f"Generation failed: {exc}") from exc

    @classmethod
    def chat(cls, messages: list[dict], **kwargs) -> str:
        """Generate a response from a list of chat messages.

        Automatically formats using the Gemma 2 chat template.

        Args:
            messages: List of {"role": "system|user|assistant", "content": str}
            **kwargs: Generation parameters (max_tokens, temperature, etc.)

        Returns:
            Full response string.
        """
        prompt = format_gemma_prompt(messages)
        return cls.generate(prompt, **kwargs)

    @classmethod
    def chat_stream(cls, messages: list[dict], **kwargs):
        """Stream a response from a list of chat messages.

        Automatically formats using the Gemma 2 chat template.

        Args:
            messages: List of {"role": "system|user|assistant", "content": str}
            **kwargs: Generation parameters (max_tokens, temperature, etc.)

        Yields:
            Token strings.
        """
        prompt = format_gemma_prompt(messages)
        yield from cls.stream(prompt, **kwargs)

    @classmethod
    def generate(cls, prompt: str, **kwargs) -> str:
        """Non-streaming generation. Returns the full response."""
        tokens = list(cls.stream(prompt, **kwargs))
        return "".join(tokens)

    @classmethod
    def reset(cls):
        """Unload the model (for testing or reload)."""
        with cls._model_lock:
            cls._model = None
