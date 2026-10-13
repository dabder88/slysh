<p align="center">
  <a href="README.md"><b>🇬🇧 English Version</b></a> • <b>🇷🇺 Русский</b>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/horizontal-lockup.png">
    <img src="docs/assets/brand/horizontal-lockup.png" alt="Логотип Slysh!" width="380">
  </picture>
</p>

<p align="center">
  <strong>Бесплатная программа для Windows: расшифровка аудио и видео на GigaAM и Whisper</strong><br>
  <em>Из звука. В смысл.</em>
</p>

<p align="center">
  <a href="https://github.com/dabder88/slysh/releases/latest"><img src="https://img.shields.io/github/v/release/dabder88/slysh?style=flat-square&color=10B981&label=версия%201.0.0" alt="Последний релиз"></a>
  <a href="https://slyshai.pro/"><img src="https://img.shields.io/badge/сайт-slyshai.pro-6366F1?style=flat-square" alt="Сайт"></a>
  <img src="https://img.shields.io/badge/платформа-Windows%2010%20%7C%2011-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Платформа">
  <a href="LICENSE"><img src="https://img.shields.io/badge/лицензия-Бесплатно%20для%20личного%20использования-blue?style=flat-square" alt="Лицензия"></a>
  <img src="https://img.shields.io/badge/модели-GigaAM%20%7C%20Whisper%20%7C%20NeMo-F97316?style=flat-square" alt="Модели">
  <img src="https://img.shields.io/badge/сборка-uv-DE5FE9?style=flat-square&logo=astral&logoColor=white" alt="uv package manager">
  <a href="https://t.me/dabder88"><img src="https://img.shields.io/badge/Telegram-Автор-229ED9?style=flat-square&logo=telegram&logoColor=white" alt="Telegram"></a>
  <a href="https://pay.cloudtips.ru/p/4e14b5b2"><img src="https://img.shields.io/badge/Поддержать-CloudTips-EC4899?style=flat-square&logo=heart&logoColor=white" alt="Поддержать"></a>
</p>

<p align="center">
  <a href="https://github.com/dabder88/slysh/releases/latest/download/Slysh-Setup-1.0.0-ru.exe">
    <img src="https://img.shields.io/badge/⬇️_Скачать_для_Windows_(.exe)-0078D4?style=for-the-badge&logo=windows&logoColor=white" alt="Скачать для Windows">
  </a>
  <a href="https://slyshai.pro/">
    <img src="https://img.shields.io/badge/🌐_Официальный_сайт-24292e?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Официальный сайт">
  </a>
  <a href="README.md">
    <img src="https://img.shields.io/badge/🇬🇧_English_Version-107C41?style=for-the-badge&logo=readme&logoColor=white" alt="English">
  </a>
</p>

<details>
  <summary><b>📖 Оглавление</b> <i>(нажмите, чтобы развернуть)</i></summary>

  - [💡 Что такое Slysh!?](#-что-такое-slysh)
  - [⚡ Сравнение с аналогами](#-сравнение-с-аналогами)
  - [🖥️ Возможности и скриншоты программы](#️-возможности-и-скриншоты-программы)
  - [🚀 Быстрый старт на Windows](#-быстрый-старт-на-windows)
  - [🏗️ Архитектура и устройство](#️-архитектура-и-устройство)
  - [📄 Лицензия и условия использования](#-лицензия-и-условия-использования)
  - [💖 Поддержать автора](#-поддержать-автора)
  - [📈 Динамика звёзд на GitHub](#-динамика-звёзд-на-github)
</details>

---

## 💡 Что такое Slysh!?

**Slysh!** — персональная десктопная программа для Windows, созданная для точной, приватной и удобной расшифровки аудио и видео в текст. Разработана для журналистов, редакторов, исследователей, подкастеров, аналитиков и продакт-менеджеров, которым нужна надежная рабочая библиотека без поминутной оплаты сторонним сервисам.

- 🏆 **Максимальная точность на русском языке**: Основная модель — **GigaAM v3** (Conformer RNNT от Salute Developers / Sber AI). Превосходит Whisper Large v3 на русской речи, не галлюцинирует на тишине и безошибочно распознает сложную терминологию.
- 🌍 **Мультиязычность**: Встроенные модели **OpenAI Whisper** и **Faster-Whisper** для уверенного распознавания более чем 90 мировых языков.
- 🎙️ **Запись встреч без ботов**: Прямой захват звука системы (WASAPI loopback) и вашего микрофона в Zoom, Microsoft Teams, Google Meet, Slack и Telegram. Никакие подозрительные боты не заходят в звонок, а звук не покидает ваш ПК.
- 👥 **Разделение по спикерам (диаризация)**: Интеграция NVIDIA NeMo Sortformer позволяет точно определять, кто какую реплику произнес, без отправки биометрии голоса в интернет.
- 📺 **YouTube: каналы и плейлисты**: Пакетный сбор готовых субтитров по ссылке на канал или плейлист с фильтрацией по дате и пропуском дубликатов, без скачивания тяжелых видеофайлов.
- ⚡ **Гибридный запуск**: Работает на 100% офлайн за счет вашей видеокарты NVIDIA GPU / процессора CPU, либо подключается к бесплатным облачным тарифам (Groq до 8 ч/день бесплатно, Gladia, Deepgram, OpenRouter) без нагрузки на ноутбук.
- 🗄️ **Локальная библиотека в SQLite**: Интерактивная звуковая волна, встроенный плеер, мгновенный полнотекстовый поиск по архиву и очередь фоновой обработки.

---

## ⚡ Сравнение с аналогами

| Возможность / Критерий | 🎙️ **Slysh!** | ⚡ **Vibe** | 🤖 **OpenAI Whisper Desktop** | ☁️ **Otter.ai / Fireflies** |
|:---|:---:|:---:|:---:|:---:|
| **Качество русского языка** | **🏆 SOTA (GigaAM v3)** | Среднее (Whisper) | Среднее (Whisper) | Низкое / Обрезано |
| **Запись созвонов** | **✅ WASAPI Loopback + Микрофон** | ⚠️ Только системный звук | ❌ Только файлы | ⚠️ Бот заходит в звонок |
| **Приватность созвона** | **✅ Невидим для участников** | ✅ Локально | ✅ Локально | ❌ Запись уходит в облако |
| **Разделение спикеров** | **✅ Локально (NeMo Sortformer)** | ❌ Нет | ❌ Нет | ✅ Облако |
| **Каналы YouTube пакетом** | **✅ Субтитры каналов и плейлистов** | ❌ Только скачивание аудио | ❌ Только скриптами | ❌ Нет |
| **100% Офлайн режим** | **✅ Полная изоляция от сети** | ✅ Локально | ✅ Локально | ❌ Только облако ($15–$30/мес) |
| **Облачный режим без GPU** | **✅ Бесплатные Groq / Gladia** | ❌ Нет облачного режима | ❌ Нет | ✅ Только облако |
| **Рабочая база и архив** | **✅ SQLite, очередь и редактор** | ⚠️ Экспорт в 1 файл | ❌ Нет | ✅ Веб-кабинет |
| **Стоимость** | **Бесплатно для личного использования** | Бесплатно | Бесплатно | Платная подписка |

> 🔬 **Воспроизводимость тестов**: Бенчмарки измерены на Windows 11 с видеокартой NVIDIA CUDA. На тестовом датасете Golos модель GigaAM RNNT показала 8–12% WER против 22–26% у Whisper-large-v3 на спонтанной русской речи.

---

## 🖥️ Возможности и скриншоты программы

### 1. Синхронный редактор и аудиоплеер
Кликните на любое слово или фразу в расшифровке, чтобы мгновенно услышать этот фрагмент в записи. Исправляйте опечатки и термины на лету с сохранением миллисекундных таймкодов.

<p align="center">
  <img src="docs/assets/screenshots/ru/1-main-ru.png" alt="Slysh! — Редактор со звуковой волной и плеером" width="880" style="border-radius: 8px; box-shadow: 0 8px 30px rgba(0,0,0,0.12);">
</p>

---

### 2. Запись встреч без ботов (WASAPI Loopback + микрофон)
Записывайте рабочие звонки в Zoom, Google Meet, Microsoft Teams, Slack или Telegram. Slysh! захватывает системный звук Windows (голоса собеседников) и ваш микрофон без добавления ботов в конференцию.

<p align="center">
  <img src="docs/assets/screenshots/ru/2-meeting-ru.png" alt="Slysh! — Запись созвонов без ботов" width="880" style="border-radius: 8px; box-shadow: 0 8px 30px rgba(0,0,0,0.12);">
</p>

---

### 3. Голосовой ввод и диктофон на ПК
Быстро надиктовывайте мысли, черновики статей или голосовые заметки прямо на компьютере. Нейросеть сама расставляет знаки препинания и сразу сохраняет результат в постоянную базу.

<p align="center">
  <img src="docs/assets/screenshots/ru/3-voice-recorder-ru.png" alt="Slysh! — Голосовой ввод и диктофон" width="880" style="border-radius: 8px; box-shadow: 0 8px 30px rgba(0,0,0,0.12);">
</p>

---

### 4. YouTube: каналы и плейлисты в субтитры
Вставьте ссылку на плейлист или канал для пакетного извлечения авторских или автоматических субтитров. Фильтруйте ролики по дате и экспортируйте готовый Markdown без скачивания гигабайтов видео.

<p align="center">
  <img src="docs/assets/screenshots/ru/4-youtube-ru.png" alt="Slysh! — Пакетная работа с YouTube" width="880" style="border-radius: 8px; box-shadow: 0 8px 30px rgba(0,0,0,0.12);">
</p>

---

### 5. Выбор движков и конвейер обработки

| Выбор движка и настройка облачных API | Очередь задач и локальный SQLite-архив |
|:---:|:---:|
| <img src="docs/assets/screenshots/ru/5-engine-ru.png" width="430" alt="Выбор движков"> | <img src="docs/assets/screenshots/ru/6-queue-ru.png" width="430" alt="Очередь и архив"> |
| *Переключение между CUDA GPU, CPU и бесплатными API* | *Фоновая очередь задач и надежная база на диске* |

---

## 🚀 Быстрый старт на Windows

### Вариант А: Официальный установщик (Рекомендуется)
1. Скачайте **`Slysh-Setup-1.0.0-ru.exe`** (или **`Slysh-Setup-ru.exe`** из того же релиза) в [GitHub Releases](https://github.com/dabder88/slysh/releases/latest) или на [slyshai.pro](https://slyshai.pro/).
2. Запустите установщик и откройте Slysh! с рабочего стола или меню Пуск.
3. Выберите режим: подключите бесплатный API-ключ (Groq/Gladia) для работы без мощной видеокарты, либо нажмите **Скачать модель** в Настройках для 100% офлайн-работы.

---

### Вариант Б: Запуск из исходников (Для разработчиков)

#### Требования
- Windows 10 или Windows 11 (64-bit)
- Установленный менеджер пакетов [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [ffmpeg](https://ffmpeg.org/download.html) в системном `PATH`
- Python 3.12

```powershell
# 1. Клонируйте репозиторий
git clone https://github.com/dabder88/slysh.git
cd slysh

# 2. Запустите лаунчер
.\Slysh.bat
```
*При первом старте `uv` быстро подготовит лёгкое окружение интерфейса. Модели и тяжелые пакеты PyTorch/NeMo можно доустановить по кнопке согласия прямо из окна программы.*

---

## 🏗️ Архитектура и устройство

В Slysh! реализована строгая изоляция процессов: интерфейс и тяжелый инференс нейросетей разделены, поэтому окно никогда не зависает во время расшифровки длинных аудиофайлов:

```
Slysh.bat / Slysh.exe
    │
    ├── Процесс интерфейса (FastAPI + uvicorn + pywebview)
    │     ├── Отдает локальный веб-интерфейс и базу SQLite app.db
    │     ├── Захватывает звук WASAPI loopback и микрофон
    │     └── Не держит PyTorch в памяти (мгновенный запуск окна)
    │
    └── Фоновый процесс распознавания (Engine Subprocess)
          ├── PyTorch (CUDA / CPU)
          ├── GigaAM (RNNT / CTC) и Faster-Whisper
          └── Диаризация спикеров NVIDIA NeMo
```

Ограничения архитектуры и тесты: [CONTRIBUTING.md](CONTRIBUTING.md). Правообладатель: [COPYRIGHT-HOLDER.md](COPYRIGHT-HOLDER.md).

---

## 📄 Лицензия и условия использования

Программа **Slysh!** является проприетарным программным обеспечением, предоставляемым **бесплатно для личного некоммерческого использования**.
- Просмотр исходного кода и персональная сборка разрешены на условиях [LICENSE](LICENSE).
- Официальные готовые сборки регулируются пользовательским соглашением (EULA), отображаемым в мастере установки.
- Сторонние открытые библиотеки и веса моделей используются в соответствии с их лицензиями (см. [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).

---

## 💖 Поддержать автора

Slysh! развивается независимо, без рекламы и венчурных инвестиций. Если программа экономит вам время:
- ⭐ **Поставьте звезду** этому репозиторию на GitHub!
- ☕ **Поддержите автора** через [CloudTips](https://pay.cloudtips.ru/p/4e14b5b2).
- 💬 **Обратная связь и вопросы**: Telegram автора [@dabder88](https://t.me/dabder88) | Почта: [dabder@mail.ru](mailto:dabder@mail.ru)

---

## 📈 Динамика звёзд на GitHub

<p align="center">
  <a href="https://star-history.com/#dabder88/slysh&Date">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=dabder88/slysh&type=Date&theme=dark" />
      <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=dabder88/slysh&type=Date" />
      <img alt="График звёзд Slysh!" src="https://api.star-history.com/svg?repos=dabder88/slysh&type=Date" width="700" />
    </picture>
  </a>
</p>

<p align="center">
  <i>Если Slysh! сэкономил вам часы на расшифровке встреч, лекций или интервью — поддержите проект звёздочкой ⭐ на GitHub! Это помогает развивать проект и сохранять приватный офлайн AI доступным для всех.</i>
</p>
