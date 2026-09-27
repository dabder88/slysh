# Ручная проверка обновлений (GitHub Releases)

Пользователь сам открывает **«Проверить обновления»** в боковом меню (только в установленной копии). Автопроверки при старте нет.

## Канал

- Публичный репозиторий GitHub, релизы с asset **`Slysh-Setup.exe`**.
- Страница загрузки для людей: `https://github.com/{owner}/{repo}/releases/latest`.
- В payload при сборке пишется [`version.json`](../../dist/payload/version.json) (`version`, `channel`, `github_repo`). По умолчанию `github_repo` — `slysh-app/slysh`, override: env `SLYSH_GITHUB_REPO` при `build-installer-payload.ps1`.

## API (UI)

| Метод | Путь |
|-------|------|
| GET | `/api/app/info` |
| POST | `/api/updates/check` |
| GET | `/api/updates/status` |
| POST | `/api/updates/download` |
| POST | `/api/updates/apply` |

Код: [`src/slysh/updates.py`](../../src/slysh/updates.py).

## Сеть

Прямой HTTPS на `api.github.com` и `objects.githubusercontent.com`. Прокси из настроек ASR/YouTube **не** используется.

Для private repo на этапе разработки API без токена недоступен конечным пользователям — после **public** + Release проверка работает без токена. `GITHUB_TOKEN` только локально/CI, не в установщике.

## Установка

После скачивания и проверки SHA256 (опционально из `sha256: …` в body релиза) запускается тот же Inno Setup с `/CURRENTUSER /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS`, приложение завершается.

Данные в `%LOCALAPPDATA%\Slysh` и `{app}\models` не удаляются.

## После обновления приложения

Если изменился `uv.lock` и локальные пакеты уже стоят — `engine_resync_recommended` в `/api/setup`; UI предлагает переустановить пакеты расшифровки.

## Чеклист релиза

1. Поднять `version` в `pyproject.toml` и `src/slysh/__init__.py`.
2. `powershell -File scripts\build-installer-payload.ps1`
3. `powershell -File scripts\build-slysh-setup.ps1`
4. GitHub Release: тег `vX.Y.Z`, прикрепить `dist\Slysh-Setup.exe`, в описании changelog и строка `sha256: …`.
5. README: ссылка на `releases/latest`.

См. [wiki/installer.md](../../wiki/installer.md).
