# Сторонние компоненты (краткий перечень)

Установщик Slysh включает или загружает при первом запуске компоненты с отдельными лицензиями. Это не выбор лицензии для всего продукта.

| Компонент | Назначение | Лицензия / ссылка |
|-----------|------------|-------------------|
| Python 3.12 | runtime | PSF |
| uv | менеджер пакетов | Apache-2.0 / MIT (Astral) |
| ffmpeg | декодирование медиа | LGPL 2.1+ — см. `licenses/ffmpeg-LGPL.txt` в payload |
| Microsoft Edge WebView2 Runtime | окно UI (Chromium) | лицензия Microsoft |
| PyPI-зависимости `slysh` | UI и опционально engine | см. метаданные пакетов в `uv.lock` |
| GigaAM (optional extra) | локальный ASR | лицензия репозитория salute-developers/GigaAM |
| PyTorch / NeMo (optional extras) | ASR / диаризация | соответствующие лицензии NVIDIA |

Полный список версий зафиксирован в `uv.lock` в каталоге установки.
