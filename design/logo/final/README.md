# Slysh — выбранный оригинал без перерисовки

Это комплект **точно из выбранного PNG**, без изменения формы, цветов, градиентов, пропорций или надписи. Мастер скопирован из приложенного пользователем файла без перекодирования.

## Главный исходник

`source/slysh-original-board-untouched.png`

SHA-256: `4599A7B2A8DD32BD00367F16CE06B8C33E8FA0CD7B8875823C07305A3B997D48`

## Содержимое

- `png/masters/primary-symbol.png` — оригинальный большой знак;
- `png/masters/wordmark.png` — оригинальная надпись;
- `png/masters/horizontal-lockup.png` — оригинальный горизонтальный логотип;
- `png/masters/app-icon-light.png` — оригинальная светлая иконка;
- `png/masters/app-icon-dark.png` — оригинальная тёмная иконка;
- `png/masters/monochrome-symbol.png` — оригинальный монохромный знак;
- `png/sizes/` — технические уменьшенные PNG 16–1024 px;
- `ico/slysh-original.ico` — Windows ICO с оригинальным цветным знаком на прозрачном фоне;
- `svg-pixel-exact/` — SVG-контейнеры с внедрёнными оригинальными PNG;
- `source/manifest.json` — координаты кропов и способ сборки;
- `build_exact_assets.py` — воспроизводимая сборка комплекта.

## Ограничение исходника

Выбранное изображение было создано генератором как растровый PNG. Настоящего векторного файла с кривыми у него нет. Поэтому SVG в этом комплекте сохраняют изображение 1:1 посредством внедрённого PNG. Автоматическая трассировка или ручная отрисовка изменили бы знак и намеренно не выполнялись.

## Пересборка

```powershell
.\.venv\Scripts\python.exe design\logo\final\build_exact_assets.py
powershell -File scripts\sync-branding.ps1
```

Скрипт сначала проверяет SHA-256 мастера и остановится, если оригинал был изменён. `sync-branding.ps1` копирует PNG в `web/branding/` и `slysh.ico` в корень репозитория для UI и pywebview.
