# a0_STTs -- Multi-Provider Speech-to-Text for Agent Zero

A cloud STT plugin for [Agent Zero](https://github.com/frdel/agent-zero). Replace the built-in local Whisper with Deepgram or OpenAI Whisper API -- no model downloads, no GPU required.

> [!WARNING]
> **This repository has not been human-tested.** The plugin was developed and assembled by AI (Agent Zero). Use at your own risk and verify the code before deploying in production.


---

## Overview

a0_STTs is a **native Agent Zero plugin** that transparently replaces the built-in speech-to-text engine with cloud providers. It patches the A0 STT pipeline at runtime -- the web UI microphone button and YATCA Telegram voice messages both benefit automatically.

| Built-in Whisper | a0_STTs |
|---|---|
| Local model download (hundreds of MB) | Cloud API, no downloads |
| GPU/CPU intensive | Lightweight HTTP call |
| Limited language support | 30+ languages (Deepgram), auto-detect |
| Single provider | Deepgram, OpenAI Whisper API, or local fallback |
| Slow cold start | Fast cloud inference |

---

## Features

- **Deepgram** -- nova-2, nova-2-general, nova-2-meeting, nova-2-phonecall, nova-3, enhanced, base
- **OpenAI Whisper API** -- whisper-1
- **Local Whisper fallback** -- falls back to built-in Whisper if provider is unconfigured or fails
- **Web UI mic** -- works transparently with the Agent Zero voice input button
- **YATCA integration** -- auto-transcribes Telegram voice messages (.ogg) when YATCA is installed
- **Language selection** -- ISO 639-1 codes (cs, en, de ...) or empty for auto-detect
- **Automatic fallback** -- on API error, falls back to local Whisper with error log
- **Runtime provider switching** -- change provider in settings without restart

---

## Quick Install

### Via Agent Zero Plugin Manager

Once published to the [a0-plugins](https://github.com/agent0ai/a0-plugins) index, a0_STTs will be installable directly from the Agent Zero WebUI plugin browser.

### Manual Install

Clone this repo into your Agent Zero plugins directory:

```bash
cd /path/to/agent-zero/usr/plugins
git clone https://github.com/mirecekd/a0_STTs.git stt_providers
```

Then:

1. Open the Agent Zero WebUI
2. Go to **Settings** and find the **stt_providers** plugin
3. Enable the plugin
4. Click **Settings** next to the plugin
5. Select your provider and enter your API key
6. Set the language code (e.g. `cs` for Czech, `en` for English)
7. Save -- takes effect on the next voice input

> **Tip:** Leave the language field empty to let the provider auto-detect the language.

---

## API Keys

| Provider | Where to get | Free tier |
|---|---|---|
| Deepgram | [console.deepgram.com](https://console.deepgram.com) | 200 hours/month |
| OpenAI | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | Pay-per-use |

---

## Plugin Structure

```text
stt_providers/                         # Plugin root
|-- plugin.yaml                        # Plugin metadata
|-- default_config.yaml                # Default configuration
|-- README.md                          # This file
|
|-- helpers/
|   |-- transcribe.py                  # Deepgram + OpenAI API client logic
|   +-- yatca_voice.py                 # YATCA _download_attachments patch
|
|-- extensions/python/
|   +-- job_loop/
|       +-- _05_stt_patch.py           # Runtime patch for whisper.transcribe
|
+-- webui/
    +-- config.html                    # Settings panel (provider, API key, language)
```

---

## Configuration Reference

All settings are configured via the WebUI.

| Setting | Default | Description |
|---------|---------|-------------|
| `provider` | `local` | Active provider: `local`, `deepgram`, or `openai` |
| `deepgram.api_key` | `` | Deepgram API key |
| `deepgram.model` | `nova-2` | Deepgram model name |
| `deepgram.language` | `cs` | ISO 639-1 language code, empty = auto-detect |
| `openai.api_key` | `` | OpenAI API key |
| `openai.model` | `whisper-1` | OpenAI model name |
| `openai.language` | `cs` | ISO 639-1 language code, empty = auto-detect |

### Deepgram Models

| Model | Best for |
|---|---|
| `nova-2` | General use (recommended) |
| `nova-2-meeting` | Meeting recordings |
| `nova-2-phonecall` | Phone call audio |
| `nova-3` | Latest generation |
| `enhanced` | High accuracy |
| `base` | Fastest, lowest cost |

---

## Architecture

```text
+-------------------+         +----------------------+         +-----------------+
| Web UI Microphone |  /api/  | helpers.whisper      |  HTTP   | Deepgram /       |
|   (browser WAV)   |-------->| .transcribe()        |-------->| OpenAI Whisper   |
+-------------------+ transc. | [patched by plugin]  |  REST   | API              |
                              +----------------------+         +-----------------+

+-------------------+         +----------------------+         +-----------------+
| Telegram voice    |  .ogg   | YATCA                |  HTTP   | Deepgram /       |
|   message (YATCA) |-------->| _download_attachments|-------->| OpenAI Whisper   |
+-------------------+         | [patched by plugin]  |  REST   | API              |
                              +----------------------+         +-----------------+
                                         |
                                         +--> .transcript.txt sent to agent
```

---

## YATCA Voice Messages

When [YATCA](https://github.com/mirecekd/yatca) is installed alongside a0_STTs, voice messages sent via Telegram are automatically transcribed using the configured cloud provider. The plugin patches YATCA's download pipeline to intercept audio files (.ogg, .opus, .mp3, .m4a, .wav, .flac, .webm) and attach a transcript text file to the agent message.

---

## License

MIT
