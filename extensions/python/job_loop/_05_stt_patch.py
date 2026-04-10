"""
STT Providers Plugin - Startup patch for helpers.whisper.transcribe.
Runs on each job_loop tick but only patches once.
Patches:
  1. helpers.whisper.transcribe -> our multi-provider dispatcher
  2. YATCA _download_attachments -> auto-transcribe voice files (if YATCA is installed)
"""

from helpers.extension import Extension
from helpers.print_style import PrintStyle

PLUGIN_NAME = "stt_providers"
_WHISPER_PATCH_ATTR = "_stt_providers_patched"
_YATCA_PATCH_ATTR = "_stt_providers_yatca_patched"


class SttProvidersPatch(Extension):

    async def execute(self, **kwargs) -> None:
        import helpers.whisper as whisper_module

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
