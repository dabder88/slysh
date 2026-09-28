# Журнал

Сюда дописывать дату и что изменилось в продовой копии. Старые строки не переписывать.

## 2026-09-23

Продовая копия доведена до неподписанного установщика Windows.

- Пакет переименован: код в `src/slysh`, команда `slysh`, лаунчер `Slysh.bat`.
- Каталог данных по умолчанию — `%LOCALAPPDATA%\Slysh`. Отдельный `GIGAAM_DESKTOP_HOME` лаунчер не задаёт.
- `Slysh.bat` задаёт `SLYSH_INSTALL_ROOT` на папку программы, модели и кэш Hugging Face — на `models` рядом с программой.
- Установщик Inno Setup: `installer/Slysh.iss`. Комплект сборки — `dist/payload`. Готовый файл — `dist/Slysh-Setup.exe`. Папка `dist` в git не входит.
- В установщике лёгкий Python без torch, свой `bin/ffmpeg.exe`, пустой `models`. База, ключи и веса этой машины в exe не входят.
- Установка в профиль пользователя, без прав администратора: `%LOCALAPPDATA%\Programs\Slysh`. Ярлык Slysh в меню Пуск. Удаление через «Приложения». Папку `models` деинсталлятор не стирает.
- Подписи exe нет. Кнопки «Обновить» нет. На GitHub Releases файл не выкладывался.

До этого в той же копии уже были: свой ffmpeg, окно первого запуска, локальные веса GigaAM, YouTube и диаризация внутри пакета. Подробности поведения — в [[first-run]], [[installer]], [[data-and-models]].

## 2026-09-26

Редизайн модала «Настройки» (Modern Pro Bento, ветка `prod-launch`).

- Пять вкладок: ASR, Сеть, Облако, YouTube, Система; класс `settings-bento` на `#settings-modal`.
- Перенос существующих секций без смены id полей и привязок `shell.js`.
- Visual parity: шапка, picker локальной модели, прогресс скачивания.
- Parity ASR / облако / прокси: плоская секция прокси, карточки облачных пресетов, deep-link на вкладку и спойлер провайдера.
- Документация: строка в `docs/core/ARCHITECTURE.md`, черновик `docs/design/settings_modal_bento/README.md`.

## 2026-09-27

Доработки UI и документации.

- Ширина модала настроек **640px**; микро-типографика в scope bento **+2px**.
- Legacy «Файлы и пакеты»: удалён дублирующий `#compute-hint`; отступы у `#files-chrome` и `#batches-chrome` под фильтры.
- Вики: [[settings-ui]], обновлён design README, правило «все значимые правки — в md» в [[rules]] и AGENTS.md.
- Legacy: flex `gap` подсказки и «Фильтров», `app.css?v=113`.
- Архив: убрана кнопка topbar «Загрузить» (была ярлыком на панель); загрузка — сайдбар / dashboard.

## 2026-09-27 (обновления)

- Ручная проверка обновлений: меню «Проверить обновления», GitHub Releases, API `/api/app/info`, `/api/updates/*`.
- Сборка: `version.json` в payload, `AppVersion` в Inno из `pyproject.toml`.
- Документация: [docs/features/APP-UPDATES.md](../docs/features/APP-UPDATES.md), [[installer]].

## 2026-09-27 (gitignore)

- Расширен `.gitignore`: `.test-home/`, `refs/`, `design/`, `web/dist/`, кэш локалей, legacy `web/app.js` / `web/styles.css`, логи лаунчера в корне.
- Сняты с отслеживания макеты `refs/`, исходники `design/`, дубликат CSS и кэш; в git остаются `web/branding/` и `slysh.ico`.
