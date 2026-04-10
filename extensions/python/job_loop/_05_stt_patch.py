"""
STT Providers Plugin - Startup patch for helpers.whisper.transcribe.
Runs on each job_loop tick but only patches once (or re-patches if transcribe.py changed on disk).
Patches:
  1. helpers.whisper.transcribe -> our multi-provider dispatcher
  2. YATCA _download_attachments -> auto-transcribe voice files (if YATCA is installed)
"""

import os
import sys
from helpers.extension import Extension
from helpers.print_style import PrintStyle

PLUGIN_NAME = "stt_providers"
_WHISPER_PATCH_ATTR = "_stt_providers_patched"
_WHISPER_MTIME_ATTR = "_stt_providers_transcribe_mtime"
_YATCA_PATCH_ATTR = "_stt_providers_yatca_patched"

_TRANSCRIBE_MODULE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "..", "helpers", "transcribe.py"
)
# Resolve to actual path in plugin
_TRANSCRIBE_PLUGIN_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "helpers", "transcribe.py")
)


def _get_transcribe_mtime() -> float:
    """Get mtime of transcribe.py to detect file changes."""
    try:
        return os.path.getmtime(_TRANSCRIBE_PLUGIN_PATH)
    except OSError:
        return 0.0


class SttProvidersPatch(Extension):

    async def execute(self, **kwargs) -> None:
        import helpers.whisper as whisper_module

        # --- Check if transcribe.py changed on disk -> invalidate and re-patch ---
        current_mtime = _get_transcribe_mtime()
        last_mtime = getattr(whisper_module, _WHISPER_MTIME_ATTR, 0.0)

        if getattr(whisper_module, _WHISPER_PATCH_ATTR, False) and current_mtime != last_mtime:
            PrintStyle.standard(f"[stt_providers] transcribe.py changed on disk, re-patching...")
            # Invalidate module cache
            sys.modules.pop('usr.plugins.stt_providers.helpers.transcribe', None)
            # Reset patch flag to force re-patch below
            setattr(whisper_module, _WHISPER_PATCH_ATTR, False)

        # --- Patch 1: whisper.transcribe for web UI mic input ---
        # Always patch regardless of current provider setting.
        # Provider is read dynamically inside patched_transcribe so runtime
        # switching works without restart.
        if not getattr(whisper_module, _WHISPER_PATCH_ATTR, False):
            _original_transcribe = whisper_module.transcribe

            async def patched_transcribe(model_name: str, audio_bytes_b64: str):
                try:
                    from usr.plugins.stt_providers.helpers.transcribe import transcribe_with_provider
                    return await transcribe_with_provider(model_name, audio_bytes_b64)
                except Exception as e:
                    PrintStyle.error(f"[stt_providers] patched_transcribe error: {e}, falling back to original")
                    return await _original_transcribe(model_name, audio_bytes_b64)

            whisper_module.transcribe = patched_transcribe
            setattr(whisper_module, _WHISPER_PATCH_ATTR, True)
            setattr(whisper_module, _WHISPER_MTIME_ATTR, current_mtime)
            PrintStyle.standard(f"[stt_providers] whisper.transcribe patched successfully")

        # --- Patch 2: YATCA voice integration (optional, idempotent) ---
        if not getattr(whisper_module, _YATCA_PATCH_ATTR, False):
            try:
                from usr.plugins.stt_providers.helpers.yatca_voice import patch_yatca_handle_message
                patched = patch_yatca_handle_message()
                if patched:
                    setattr(whisper_module, _YATCA_PATCH_ATTR, True)
                    PrintStyle.standard(f"[stt_providers] YATCA voice integration patched")
            except Exception as e:
                PrintStyle.error(f"[stt_providers] YATCA voice patch error: {e}")
