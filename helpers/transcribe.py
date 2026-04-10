"""
STT Providers Plugin - Multi-provider speech-to-text transcription.
Supports: Deepgram, OpenAI Whisper API, local Whisper (fallback).
"""

import base64
import os
import json

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _log(msg: str, level: str = "info") -> None:
    """Safe logger - works without external dependencies."""
    try:
        from helpers.print_style import PrintStyle
        if level == "error":
            PrintStyle.error(msg)
        else:
            PrintStyle.standard(msg)
    except Exception:
        print(msg, flush=True)


def get_config() -> dict:
    """Load plugin config directly from config.json."""
    config_path = os.path.join(PLUGIN_DIR, "config.json")
    default_path = os.path.join(PLUGIN_DIR, "default_config.yaml")

    cfg = {}
    try:
        import yaml
        with open(default_path, 'r') as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        pass

    try:
        with open(config_path, 'r') as f:
            user_cfg = json.load(f)
        for k, v in user_cfg.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    except Exception:
        pass

    return cfg


def detect_audio_content_type(audio_bytes: bytes) -> tuple:
    """Detect real audio format from magic bytes."""
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

    content_type, ext = detect_audio_content_type(audio_bytes)
    _log(f"[stt_providers] Deepgram: {content_type}, {len(audio_bytes)} bytes")

    url = "https://api.deepgram.com/v1/listen"
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": content_type,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, params=params, headers=headers, content=audio_bytes)
        response.raise_for_status()
        data = response.json()

    try:
        transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"]
    except (KeyError, IndexError):
        transcript = ""
        _log(f"[stt_providers] Deepgram unexpected response: {data}", "error")

    _log(f"[stt_providers] Deepgram transcript: '{transcript[:80]}'")
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

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        url = "https://api.openai.com/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {api_key}"}
        files = {"file": (f"audio.{ext}", open(tmp_path, "rb"), content_type)}
        data = {"model": model}
        if language:
            data["language"] = language

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, files=files, data=data)
            response.raise_for_status()
            result = response.json()
    finally:
        os.unlink(tmp_path)

    transcript = result.get("text", "")
    _log(f"[stt_providers] OpenAI transcript: '{transcript[:80]}'")
    return {"text": transcript}


async def transcribe_with_provider(model_name: str, audio_bytes_b64: str) -> dict:
    """Main dispatcher - routes to configured provider."""
    import helpers.whisper as _whisper

    cfg = get_config()
    provider = cfg.get("provider", "local")

    # Strip data URL prefix if present (e.g. 'data:audio/wav;base64,...')
    if isinstance(audio_bytes_b64, str) and ";base64," in audio_bytes_b64:
        audio_bytes_b64 = audio_bytes_b64.split(";base64,", 1)[1]

    audio_bytes = base64.b64decode(audio_bytes_b64)

    try:
        if provider == "deepgram":
            return await transcribe_deepgram(audio_bytes, cfg)
        elif provider == "openai":
            return await transcribe_openai(audio_bytes, cfg)
        else:
            return await _whisper._transcribe(model_name, audio_bytes_b64)
    except Exception as e:
        _log(f"[stt_providers] {provider} error: {e} - falling back to local Whisper", "error")
        return await _whisper._transcribe(model_name, audio_bytes_b64)
