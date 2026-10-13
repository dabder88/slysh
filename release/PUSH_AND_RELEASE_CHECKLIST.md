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

Загрузите assets:

- `dist\Slysh-Setup-1.0.0-ru.exe`
- `dist\Slysh-Setup-1.0.0-en.exe`

Рекомендуется также загрузить копии с именами `Slysh-Setup-ru.exe` и `Slysh-Setup-en.exe` для кнопок README и in-app updates.

## 4. Проверка

- README на github.com: логотип, скриншоты, EN ↔ RU
- Actions: зелёный workflow `pytest` на последнем push
- Скачать Setup с Releases → установить → «Проверить обновления»
