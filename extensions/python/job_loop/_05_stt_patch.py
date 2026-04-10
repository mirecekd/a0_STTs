"""
STT Providers Plugin - Startup patch for helpers.whisper.transcribe.
Runs on each job_loop tick and always re-patches.
- Uses whisper._transcribe (private, never patched) as safe fallback.
- sys.modules.pop ensures fresh transcribe.py on every call.
Patches:
  1. helpers.whisper.transcribe -> our multi-provider dispatcher
  2. YATCA _download_attachments -> auto-transcribe voice files (if YATCA is installed)
"""

import sys
from helpers.extension import Extension
from helpers.print_style import PrintStyle

_YATCA_PATCH_ATTR = "_stt_providers_yatca_patched"


class SttProvidersPatch(Extension):

    async def execute(self, **kwargs) -> None:
        import helpers.whisper as whisper_module

        # --- Patch 1: whisper.transcribe ---
        # Always re-patch on every job_loop tick.
        # Use whisper._transcribe (private, never patched) as safe fallback.
        _original = whisper_module._transcribe  # private func, always the real Whisper

        async def patched_transcribe(model_name: str, audio_bytes_b64: str):
            # Pop module cache every call -> always loads latest transcribe.py from disk
            sys.modules.pop('usr.plugins.stt_providers.helpers.transcribe', None)
            try:
                from usr.plugins.stt_providers.helpers.transcribe import transcribe_with_provider
                return await transcribe_with_provider(model_name, audio_bytes_b64)
            except Exception as e:
                PrintStyle.error(f"[stt_providers] error: {e}, falling back to local Whisper")
                return await _original(model_name, audio_bytes_b64)

        whisper_module.transcribe = patched_transcribe
        PrintStyle.debug(f"[stt_providers] whisper.transcribe patched (fallback: _transcribe)")

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
