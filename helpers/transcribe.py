"""
STT Providers Plugin - Multi-provider speech-to-text transcription.
Supports: Deepgram, OpenAI Whisper API, local Whisper (fallback).
"""

import base64
import tempfile
import os

from helpers import plugins
from helpers.print_style import PrintStyle

PLUGIN_NAME = "stt_providers"


def get_config() -> dict:
    """Load plugin config with defaults."""
    cfg = plugins.get_plugin_config(PLUGIN_NAME) or {}
    return cfg


def detect_audio_content_type(audio_bytes: bytes) -> tuple[str, str]:
    """Detect real audio format from magic bytes. Returns (content_type, extension)."""
    if audio_bytes[:4] == b'RIFF':
        return 'audio/wav', 'wav'
    elif audio_bytes[:4] == b'OggS':
        return 'audio/ogg', 'ogg'
    elif len(audio_bytes) >= 4 and audio_bytes[:4] == b'\x1a\x45\xdf\xa3':
        return 'audio/webm', 'webm'
    elif audio_bytes[:3] == b'ID3' or (len(audio_bytes) >= 2 and audio_bytes[:2] in (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2')):
        return 'audio/mpeg', 'mp3'
    elif audio_bytes[:4] == b'fLaC':
        return 'audio/flac', 'flac'
    elif len(audio_bytes) >= 8 and audio_bytes[4:8] in (b'ftyp', b'mdat', b'moov'):
        return 'audio/mp4', 'm4a'
    else:
        # Default to webm - most browsers record in webm/opus
        return 'audio/webm', 'webm'


async def transcribe_deepgram(audio_bytes: bytes, cfg: dict) -> dict:
    """Transcribe audio using Deepgram REST API."""
    import httpx

    dg_cfg = cfg.get("deepgram", {})
    api_key = dg_cfg.get("api_key", "")
    model = dg_cfg.get("model", "nova-2")
    language = dg_cfg.get("language", "")

    if not api_key:
        raise ValueError("Deepgram API key is not configured.")

    params = {"model": model, "punctuate": "true", "smart_format": "true"}
    if language:
        params["language"] = language

    # Detect REAL content type from magic bytes (browser sends webm, not wav!)
    content_type, ext = detect_audio_content_type(audio_bytes)
    PrintStyle.debug(f"[stt_providers] Deepgram audio: {content_type}, {len(audio_bytes)} bytes")

    url = "https://api.deepgram.com/v1/listen"
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": content_type,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, params=params, headers=headers, content=audio_bytes)
        response.raise_for_status()
        data = response.json()

    # Extract transcript from Deepgram response
    try:
        transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"]
    except (KeyError, IndexError):
        transcript = ""
        PrintStyle.error(f"[stt_providers] Deepgram unexpected response: {data}")

    PrintStyle.debug(f"[stt_providers] Deepgram transcript: '{transcript[:80]}'")
    return {"text": transcript}


async def transcribe_openai(audio_bytes: bytes, cfg: dict) -> dict:
    """Transcribe audio using OpenAI Whisper API."""
    import httpx

    oa_cfg = cfg.get("openai", {})
    api_key = oa_cfg.get("api_key", "")
    model = oa_cfg.get("model", "whisper-1")
    language = oa_cfg.get("language", "")

    if not api_key:
        raise ValueError("OpenAI API key is not configured.")

    content_type, ext = detect_audio_content_type(audio_bytes)

    url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}

    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            with open(tmp_path, "rb") as audio_file:
                files = {"file": (f"audio.{ext}", audio_file, content_type)}
                data = {"model": model}
                if language:
                    data["language"] = language
                response = await client.post(url, headers=headers, files=files, data=data)
                response.raise_for_status()
                result = response.json()
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    transcript = result.get("text", "")
    PrintStyle.debug(f"[stt_providers] OpenAI transcript: '{transcript[:80]}'")
    return {"text": transcript}


async def transcribe_with_provider(model_name: str, audio_bytes_b64: str) -> dict:
    """
    Main transcription dispatcher. Called instead of whisper.transcribe().
    Routes to the configured provider or falls back to local Whisper.
    """
    cfg = get_config()
    provider = cfg.get("provider", "local")

    audio_bytes = base64.b64decode(audio_bytes_b64)

    if provider == "deepgram":
        try:
            return await transcribe_deepgram(audio_bytes, cfg)
        except Exception as e:
            PrintStyle.error(f"[stt_providers] Deepgram error: {e} - falling back to local Whisper")
            from helpers import whisper as _whisper
            return await _whisper._transcribe(model_name, audio_bytes_b64)

    elif provider == "openai":
        try:
            return await transcribe_openai(audio_bytes, cfg)
        except Exception as e:
            PrintStyle.error(f"[stt_providers] OpenAI STT error: {e} - falling back to local Whisper")
            from helpers import whisper as _whisper
            return await _whisper._transcribe(model_name, audio_bytes_b64)

    else:
        from helpers import whisper as _whisper
        return await _whisper._transcribe(model_name, audio_bytes_b64)
