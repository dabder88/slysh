import json
import sys
from urllib.request import Request, urlopen

from slysh.youtube_metadata import (
    _chapters_from_description,
    _extract_json_blob,
    _walk_yt_nodes,
    fetch_video_metadata_watch_page,
)

sys.stdout.reconfigure(encoding="utf-8")

vid = "AFyZVN9McJc"
req = Request(
    f"https://www.youtube.com/watch?v={vid}",
    headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9",
    },
)
html = urlopen(req, timeout=20).read().decode("utf-8", "replace")
initial = _extract_json_blob(html, "var ytInitialData = ")
player = _extract_json_blob(html, "var ytInitialPlayerResponse = ")

desc = ""
if player:
    desc = str(player.get("videoDetails", {}).get("shortDescription") or "")
print("player desc lines", len(desc.splitlines()))
for line in desc.splitlines()[-8:]:
    print(repr(line))

if initial:
    bodies = _walk_yt_nodes(initial, "expandableVideoDescriptionBodyRenderer")
    print("description bodies", len(bodies))

sample = """00:00 ЧТО НОВОГО В FABLE 5.1
03:59 КАК ПРАВИЛЬНО ПРОМПТИТЬ FABLE 5.1
12:55 СОБИРАЕМ ПРЕМИУМ-САЙТ
21:15 ЗАКЛЮЧЕНИЕ"""
print("parsed", _chapters_from_description(sample))
print("watch", fetch_video_metadata_watch_page(f"https://www.youtube.com/watch?v={vid}"))
