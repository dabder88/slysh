# Вне плана продукта

Решение владельца (2026-10-02). **Не** входят в roadmap, **не** ожидаются от агента и **не** считаются «незакрытыми задачами» в [`implementation-status.md`](implementation-status.md).

| Тема | Что остаётся в продукте |
|------|-------------------------|
| Подпись Setup / SmartScreen | Установщик без code signing; в [`installer/КАК-ЗАПУСТИТЬ.txt`](installer/КАК-ЗАПУСТИТЬ.txt) — подсказка пользователю «Подробнее → Выполнить в любом случае». |
| Автообновление в фоне | Только **ручная** проверка обновлений (GitHub Releases) и SHA-256 перед запуском Setup — см. E.4 / `updates.py`. |
| Юридический due diligence | Справочник [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) в payload (`licenses\`); отдельная legal-работа **не планируется**. |
| Обязательное скачивание всех весов в `models/` | Модели и engine по выбору пользователя (Настройки, облако); `models/` не обязателен при клоне/первом запуске. |

Актуальный план работ: [`implementation-order.md`](implementation-order.md), статус: [`implementation-status.md`](implementation-status.md).
