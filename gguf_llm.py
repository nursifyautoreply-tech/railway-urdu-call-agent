"""Local entry point for the deployable GGUF LiveKit adapter."""
import importlib.util
from pathlib import Path

_implementation = Path(__file__).parent / "railway-gguf" / "voice-agent" / "gguf_llm.py"
_spec = importlib.util.spec_from_file_location("railway_gguf_llm", _implementation)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Unable to load GGUF adapter from {_implementation}")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

GGUFLLM = _module.GGUFLLM

__all__ = ["GGUFLLM"]
