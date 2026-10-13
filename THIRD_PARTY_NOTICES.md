# Third-Party Notices & Licenses

Slysh! incorporates or interacts with open-source software and model weights licensed under various permissive and copyleft licenses. Below is a summary of the key components and their licenses:

---

## 1. AI Models & ASR Engines

### GigaAM (Salute Developers / Sber AI)
- **License**: Apache License 2.0
- **Repository**: [https://github.com/salute-developers/GigaAM](https://github.com/salute-developers/GigaAM)
- **Copyright**: (c) Salute Developers, Sber AI

### OpenAI Whisper
- **License**: MIT License
- **Repository**: [https://github.com/openai/whisper](https://github.com/openai/whisper)
- **Copyright**: (c) OpenAI

### Faster-Whisper (SYSTRAN)
- **License**: MIT License
- **Repository**: [https://github.com/SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- **Copyright**: (c) SYSTRAN

### NVIDIA NeMo (Sortformer / MSDD Diarization)
- **License**: Apache License 2.0
- **Repository**: [https://github.com/NVIDIA/NeMo](https://github.com/NVIDIA/NeMo)
- **Copyright**: (c) NVIDIA Corporation

---

## 2. Core Python Framework & UI Libraries

### FastAPI
- **License**: MIT License
- **Repository**: [https://github.com/fastapi/fastapi](https://github.com/fastapi/fastapi)
- **Copyright**: (c) Sebastián Ramírez

### PyWebView
- **License**: BSD-3-Clause License
- **Repository**: [https://github.com/r0x0r/pywebview](https://github.com/r0x0r/pywebview)
- **Copyright**: (c) Roman Sakno

### Uvicorn
- **License**: BSD-3-Clause License
- **Repository**: [https://github.com/encode/uvicorn](https://github.com/encode/uvicorn)
- **Copyright**: (c) Encode OSS Ltd.

### SoundDevice & SoundFile
- **License**: MIT License / BSD-3-Clause
- **Copyright**: (c) Matthias Geier, Bastian Bechtold

### NumPy
- **License**: BSD-3-Clause License
- **Copyright**: (c) NumPy Developers

---

## 3. External Binaries & Media Tools

### FFmpeg
- **License**: GNU Lesser General Public License (LGPL) version 2.1 or later / GPL
- **Website**: [https://ffmpeg.org](https://ffmpeg.org)
- FFmpeg is an external utility invoked as a subprocess for audio extraction and format conversion. Slysh does not statically link FFmpeg into its binaries. Pre-built builds redistribute LGPL-compliant dynamic FFmpeg executables without modifications.

---

## 4. Frontend & Styling

### Tailwind CSS
- **License**: MIT License
- **Copyright**: (c) Tailwind Labs, Inc.

### Material Symbols (Google)
- **License**: Apache License 2.0
- **Copyright**: (c) Google LLC
