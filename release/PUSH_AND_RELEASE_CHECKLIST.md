# После коммита `65bab08` — push, GitHub UI, Release

## 1. Push (нужна авторизация GitHub)

```powershell
cd F:\ProjectsAI\Slysh-prod-GPT
git push -u origin prod-launch
git push origin v1.0.0
```

В Settings → General → Default branch: выберите **prod-launch** (если ещё не default).

## 2. GitHub About (браузер)

https://github.com/dabder88/slysh/settings

- **Description:** `Free speech-to-text workstation for Windows. SOTA Russian (GigaAM), Whisper, bot-free meeting recording (WASAPI loopback) & batch YouTube processing.`
- **Website:** `https://slyshai.pro/`
- **Topics:** speech-to-text, speech-recognition, whisper, faster-whisper, gigaam, transcription, meeting-recorder, meeting-transcription, wasapi-loopback, audio-transcription, diarization, speaker-diarization, youtube-transcription, voice-typing, subtitles-generator, windows-app, desktop-app, fastapi, pywebview, uv
- **Social preview:** загрузить баннер 1280×640 (Settings → General → Social preview)

## 3. Release v1.0.0

Создайте release от тега `v1.0.0`. Текст и SHA-256: см. [GITHUB_RELEASE_v1.0.0.md](GITHUB_RELEASE_v1.0.0.md).

Загрузите assets (автоматически через `publish_release_assets.py`):

- `dist\Slysh-Setup-X.Y.Z-ru.exe` и `dist\Slysh-Setup-X.Y.Z-en.exe`
- алиасы **`Slysh-Setup-ru.exe`** и **`Slysh-Setup-en.exe`** (стабильные URL в README)

Догрузка только алиасов в существующий релиз: `publish_release_assets.py --version X.Y.Z --canonical-only`.

## 4. Проверка

- README на github.com: логотип, скриншоты, EN ↔ RU
- Actions: зелёный workflow `pytest` на последнем push
- Скачать Setup с Releases → установить → «Проверить обновления»
