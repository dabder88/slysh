from slysh.youtube_metadata import (
    _chapters_from_description,
    _chapters_from_initial_data,
    _parse_ru_date_text,
    _upload_date_from_initial_data,
    enrich_video_payload,
    merge_video_metadata,
    video_metadata_needs_enrichment,
)


def test_merge_video_metadata_prefers_existing_title():
    payload = {"title": "Старое", "channel": ""}
    extra = {"title": "Новое", "channel": "Канал"}
    merged = merge_video_metadata(payload, extra)
    assert merged["title"] == "Старое"
    assert merged["channel"] == "Канал"


def test_enrich_video_payload_uses_oembed(monkeypatch):
    monkeypatch.setattr(
        "slysh.youtube_metadata.fetch_video_metadata_oembed",
        lambda url: {
            "title": "Claude Fable",
            "channel": "AI Волчёнок",
            "channel_url": "https://www.youtube.com/@VolchenkoAI",
            "thumbnail_url": "https://i.ytimg.com/vi/AFyZVN9McJc/hqdefault.jpg",
            "upload_date": "",
            "duration_s": None,
            "chapters": [],
        },
    )
    monkeypatch.setattr(
        "slysh.youtube_ytdlp.fetch_video_metadata_ytdlp",
        lambda url: {},
    )
    monkeypatch.setattr(
        "slysh.youtube_metadata.fetch_video_metadata_watch_page",
        lambda url: {
            "upload_date": "2026-09-06",
            "chapters": [{"title": "Вступление", "start_ms": 0}],
            "chapters_checked": True,
        },
    )
    enriched = enrich_video_payload(
        "https://www.youtube.com/watch?v=AFyZVN9McJc",
        {"title": "", "channel": "", "segments": []},
    )
    assert enriched["title"] == "Claude Fable"
    assert enriched["channel"] == "AI Волчёнок"
    assert enriched["channel_url"].endswith("@VolchenkoAI")
    assert enriched["upload_date"] == "2026-09-06"
    assert enriched["chapters"][0]["title"] == "Вступление"
    assert enriched["metadata_enriched"] is True


def test_video_metadata_needs_enrichment_after_partial_oembed():
    video = {
        "title": "Видео",
        "channel": "Канал",
        "upload_date": "2026-09-06",
        "chapters": [],
        "metadata_enriched": True,
    }
    assert video_metadata_needs_enrichment(video) is True


def test_video_metadata_skips_when_chapters_checked_without_chapters():
    video = {
        "title": "Видео",
        "channel": "Канал",
        "upload_date": "2026-09-06",
        "chapters": [],
        "chapters_checked": True,
    }
    assert video_metadata_needs_enrichment(video) is False


def test_title_matches_chapter_title_triggers_reenrichment():
    video = {
        "title": "Заключение",
        "channel": "AI Прорыв",
        "upload_date": "2026-09-06",
        "chapters": [{"title": "Заключение", "start_ms": 1275000}],
        "chapters_checked": True,
    }
    assert video_metadata_needs_enrichment(video) is True


def test_enrich_heals_chapter_title(monkeypatch):
    video = {
        "title": "Заключение",
        "channel": "AI Прорыв",
        "upload_date": "2026-09-06",
        "chapters": [{"title": "Заключение", "start_ms": 1275000}],
        "chapters_checked": True,
    }
    monkeypatch.setattr(
        "slysh.youtube_metadata.fetch_video_metadata_oembed",
        lambda url: {
            "title": "Claude Fable 5.1 — Это ПРОРЫВ!",
            "channel": "AI Прорыв",
            "channel_url": "https://www.youtube.com/@test",
            "thumbnail_url": "https://example.com/thumb.jpg",
            "upload_date": "",
            "duration_s": None,
            "chapters": [],
        },
    )
    monkeypatch.setattr(
        "slysh.youtube_ytdlp.fetch_video_metadata_ytdlp",
        lambda url: {},
    )
    monkeypatch.setattr(
        "slysh.youtube_metadata.fetch_video_metadata_watch_page",
        lambda url: {},
    )
    enriched = enrich_video_payload(
        "https://www.youtube.com/watch?v=AFyZVN9McJc",
        video,
    )
    assert enriched["title"] == "Claude Fable 5.1 — Это ПРОРЫВ!"


def test_chapters_from_description():
    description = """00:00 ЧТО НОВОГО В FABLE 5.1
03:59 КАК ПРАВИЛЬНО ПРОМПТИТЬ FABLE 5.1
12:55 СОБИРАЕМ ПРЕМИУМ-САЙТ
21:15 ЗАКЛЮЧЕНИЕ"""
    chapters = _chapters_from_description(description)
    assert len(chapters) == 4
    assert chapters[1]["start_ms"] == 239000


def test_parse_ru_date_text():
    assert _parse_ru_date_text("6 сент. 2026\u202fг.") == "2026-09-06"


def test_chapters_from_initial_data_dedupes_markers():
    initial_data = {
        "contents": {
            "macroMarkersListItemRenderer": {
                "title": {"simpleText": "Вступление"},
                "timeDescription": {
                    "simpleText": "0:00",
                    "accessibility": {
                        "accessibilityData": {"label": "0 секунд"},
                    },
                },
            }
        },
        "duplicate": {
            "macroMarkersListItemRenderer": {
                "title": {"simpleText": "Вступление"},
                "timeDescription": {"simpleText": "0:00"},
            }
        },
        "next": {
            "macroMarkersListItemRenderer": {
                "title": {"simpleText": "Разбор"},
                "timeDescription": {
                    "simpleText": "3:59",
                    "accessibility": {
                        "accessibilityData": {"label": "3 минуты 59 секунд"},
                    },
                },
            }
        },
    }
    chapters = _chapters_from_initial_data(initial_data)
    assert len(chapters) == 2
    assert chapters[0] == {"title": "Вступление", "start_ms": 0}
    assert chapters[1]["start_ms"] == 239000


def test_upload_date_from_video_description_header():
    initial_data = {
        "header": {
            "videoDescriptionHeaderRenderer": {
                "dateText": {"simpleText": "6 сент. 2026\u202fг."},
            }
        }
    }
    assert _upload_date_from_initial_data(initial_data) == "2026-09-06"
