"""
Scout trending travel / vacation destinations.

Sources (public RSS + lightweight pages — no scraping of private IG/TikTok):
  - Travel section feeds (BBC Travel, Lonely Planet-style, National Geographic Travel)
  - Reddit r/travel, r/TravelPorn, r/solotravel (JSON; may 403 from cloud IPs)

Returns clean location-style queries suitable for stock video search
(e.g. "Santorini sunset aerial", "Bali rice terraces drone").
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

import requests

log = logging.getLogger("travel_scout")

USER_AGENT = (
    "AmbsonAI/1.0 (+https://github.com/ambson1989-rgb/Ambson-ai; travel scenic reels)"
)

TRAVEL_RSS = [
    ("BBC Travel", "https://feeds.bbci.co.uk/news/travel/rss.xml"),
    ("NatGeo Travel", "https://www.nationalgeographic.com/travel/rss"),
    ("Smithsonian Travel", "https://www.smithsonianmag.com/rss/travel/"),
    ("CNN Travel", "http://rss.cnn.com/rss/edition_travel.rss"),
    ("Guardian Travel", "https://www.theguardian.com/uk/travel/rss"),
]

REDDIT_TRAVEL = ["travel", "TravelPorn", "solotravel", "earthporn", "VillagePorn"]

# Pull place-like phrases out of headlines
PLACE_HINT = re.compile(
    r"\b("
    r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}|"  # Proper-ish names in titles often lowercased in RSS
    r")\b"
)

# Common destination keywords (case-insensitive boost)
KNOWN_PLACES = re.compile(
    r"\b("
    r"bali|santorini|santoríni|iceland|reykjavik|paris|tokyo|kyoto|osaka|"
    r"maldives|santorini|amalfi|positano|capri|tuscany|florence|rome|venice|"
    r"swiss\s*alps|interlaken|zermatt|norway|fjord|lofoten|"
    r"patagonia|machu\s*picchu|cusco|banff|jasper|"
    r"grand\s*canyon|yosemite|hawaii|maui|oahu|"
    r"dubai|abu\s*dhabi|cappadocia|istanbul|"
    r"morocco|marrakech|sahara|egypt|cairo|"
    r"thailand|bangkok|phuket|chiang\s*mai|vietnam|ha\s*long|"
    r"new\s*zealand|queenstown|milford|"
    r"scotland|isle\s*of\s*skye|ireland|cliffs\s*of\s*moher|"
    r"greece|mykonos|crete|croatia|dubrovnik|"
    r"portugal|algarve|lisbon|spain|barcelona|seville|"
    r"japan|seoul|singapore|sydney|melbourne|"
    r"canada|alaska|norway|sweden|finland|lapland|"
    r"petraf|jordan|dead\s*sea|"
    r"kerala|goa|ladakh|manali|himalaya|rajasthan|udaipur|"
    r"kashmir|andaman|munnar|ooty|"
    r"santorini|amalfi|cinque\s*terre"
    r")\b",
    re.I,
)

BLOCK = re.compile(
    r"\b(kill|death|war|attack|protest|crime|scam|accident)\b", re.I
)

# Map place → good stock-video search phrase (cinematic travel look)
PLACE_TO_QUERY = {
    "bali": "Bali rice terraces aerial drone tropical",
    "santorini": "Santorini white buildings sunset ocean Greece",
    "iceland": "Iceland waterfall green landscape aerial",
    "maldives": "Maldives overwater bungalow clear turquoise water",
    "amalfi": "Amalfi coast Italy cliff ocean drone",
    "positano": "Positano colorful houses cliff sea Italy",
    "tuscany": "Tuscany rolling hills cypress sunset",
    "swiss alps": "Swiss Alps mountain lake aerial",
    "norway": "Norway fjord mountains drone",
    "lofoten": "Lofoten islands Norway dramatic peaks",
    "patagonia": "Patagonia mountains lake windy landscape",
    "machu picchu": "Machu Picchu ruins mountains mist",
    "banff": "Banff national park turquoise lake mountains",
    "grand canyon": "Grand Canyon aerial sunset cliffs",
    "yosemite": "Yosemite valley waterfalls granite cliffs",
    "hawaii": "Hawaii tropical beach waterfall lush",
    "dubai": "Dubai skyline desert golden hour",
    "cappadocia": "Cappadocia hot air balloons sunrise Turkey",
    "marrakech": "Morocco desert dunes camel sunset",
    "sahara": "Sahara desert sand dunes sunrise",
    "thailand": "Thailand tropical beach longtail boat",
    "phuket": "Phuket beach clear water aerial",
    "ha long": "Ha Long Bay Vietnam limestone islands boat",
    "queenstown": "Queenstown New Zealand mountains lake",
    "milford": "Milford Sound New Zealand fjord",
    "scotland": "Scottish highlands misty mountains",
    "isle of skye": "Isle of Skye cliffs ocean Scotland",
    "mykonos": "Mykonos white buildings blue dome Greece",
    "croatia": "Dubrovnik old town Adriatic coast",
    "dubrovnik": "Dubrovnik walls sea Croatia aerial",
    "algarve": "Algarve Portugal cliffs ocean caves",
    "barcelona": "Barcelona city coast aerial sunny",
    "kyoto": "Kyoto Japan temple garden cherry blossom",
    "tokyo": "Tokyo Japan city night neon skyline",
    "paris": "Paris Eiffel Tower sunset city",
    "rome": "Rome Colosseum Italy golden hour",
    "venice": "Venice canals gondola Italy",
    "ladakh": "Ladakh Himalaya mountains monastery landscape",
    "kerala": "Kerala backwaters houseboat tropical India",
    "goa": "Goa beach palm trees sunset India",
    "himalaya": "Himalaya snow peaks aerial dramatic",
    "rajasthan": "Rajasthan palace desert India golden",
    "udaipur": "Udaipur lake palace India sunset",
}


def _rss_titles(name: str, url: str, limit: int = 10) -> list[str]:
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/xml,text/xml,*/*"},
            timeout=18,
        )
        if resp.status_code != 200:
            log.warning("Travel RSS %s status %s", name, resp.status_code)
            return []
        root = ET.fromstring(resp.content)
        titles = []
        for item in root.findall(".//item")[:limit]:
            t = item.find("title")
            if t is not None and t.text:
                titles.append(t.text.strip())
        if not titles:
            for e in root.findall(".//{http://www.w3.org/2005/Atom}entry")[:limit]:
                t = e.find("{http://www.w3.org/2005/Atom}title")
                if t is not None and t.text:
                    titles.append(t.text.strip())
        return titles
    except Exception as e:
        log.warning("Travel RSS %s failed: %s", name, e)
        return []


def _reddit_titles(sub: str, limit: int = 8) -> list[str]:
    try:
        resp = requests.get(
            f"https://www.reddit.com/r/{sub}/hot.json",
            params={"limit": limit, "raw_json": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        out = []
        for child in resp.json().get("data", {}).get("children", []):
            d = child.get("data") or {}
            if d.get("stickied"):
                continue
            title = (d.get("title") or "").strip()
            if title:
                out.append(title)
        return out
    except Exception:
        return []


def _extract_places(text: str) -> list[str]:
    found = []
    for m in KNOWN_PLACES.finditer(text or ""):
        place = m.group(0).lower().strip()
        place = re.sub(r"\s+", " ", place)
        if place not in found:
            found.append(place)
    return found


def _to_stock_query(place: str, headline: str = "") -> str:
    key = place.lower().strip()
    if key in PLACE_TO_QUERY:
        return PLACE_TO_QUERY[key]
    # Generic cinematic travel query
    return f"{place} travel destination landscape aerial cinematic"


def fetch_trending_travel(max_items: int = 12) -> list[dict[str, Any]]:
    """
    Returns list of {
      place, query, headline, source, score
    }
    sorted by score (trending-ish).
    """
    headlines: list[tuple[str, str, int]] = []  # title, source, score

    for name, url in TRAVEL_RSS:
        for title in _rss_titles(name, url):
            if BLOCK.search(title):
                continue
            headlines.append((title, name, 50))

    for sub in REDDIT_TRAVEL:
        for title in _reddit_titles(sub):
            if BLOCK.search(title):
                continue
            headlines.append((title, f"r/{sub}", 40))

    by_place: dict[str, dict[str, Any]] = {}
    for title, source, base in headlines:
        places = _extract_places(title)
        if not places:
            continue
        for place in places:
            q = _to_stock_query(place, title)
            score = base + (10 if place in PLACE_TO_QUERY else 0)
            prev = by_place.get(place)
            if not prev or score > prev["score"]:
                by_place[place] = {
                    "place": place.title(),
                    "query": q,
                    "headline": title[:120],
                    "source": source,
                    "score": score,
                }

    ranked = sorted(by_place.values(), key=lambda x: x["score"], reverse=True)

    # Always seed evergreen high-demand travel looks so we never return empty
    evergreen = [
        ("Santorini", PLACE_TO_QUERY["santorini"]),
        ("Bali", PLACE_TO_QUERY["bali"]),
        ("Maldives", PLACE_TO_QUERY["maldives"]),
        ("Swiss Alps", PLACE_TO_QUERY["swiss alps"]),
        ("Amalfi", PLACE_TO_QUERY["amalfi"]),
        ("Iceland", PLACE_TO_QUERY["iceland"]),
        ("Cappadocia", PLACE_TO_QUERY["cappadocia"]),
        ("Ladakh", PLACE_TO_QUERY["ladakh"]),
        ("Norway", PLACE_TO_QUERY["norway"]),
        ("Kyoto", PLACE_TO_QUERY["kyoto"]),
    ]
    seen = {r["place"].lower() for r in ranked}
    for place, q in evergreen:
        if place.lower() in seen:
            continue
        ranked.append({
            "place": place,
            "query": q,
            "headline": f"Evergreen travel favourite: {place}",
            "source": "evergreen",
            "score": 20,
        })

    top = ranked[:max_items]
    log.info("Travel scout: %d trending location candidates", len(top))
    for i, t in enumerate(top[:6]):
        log.info("  #%d %s ← %s (%s)", i + 1, t["place"], t["source"], t["headline"][:60])
    return top
