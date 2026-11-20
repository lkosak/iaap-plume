"""Pull official pages. Failure of a source becomes a visible gap, not a crash."""

from __future__ import annotations

import csv
import re
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path

import requests

USER_AGENT = "IAAAPIndependentScreening/1.0 (relative footprint dashboard)"

OFFICIAL_SOURCES = (
    {
        "id": "epa-public-notice",
        "publisher": "U.S. EPA Region 7",
        "kind": "official",
        "title_fallback": "EPA public notice — IAAAP emergency permit",
        "url": "https://www.epa.gov/ia/iowa-army-ammunition-plant-middletown-iowa-3",
    },
    {
        "id": "epa-osc",
        "publisher": "U.S. EPA On-Scene Coordinator",
        "kind": "official",
        "title_fallback": "EPA OSC site profile — IAAAP lead azide",
        "url": "https://response.epa.gov/site/site_profile.aspx?site_id=17211",
    },
    {
        "id": "army-advisory",
        "publisher": "U.S. Army",
        "kind": "official",
        "title_fallback": "Army public advisory",
        "url": "https://www.army.mil/article/296772",
    },
    {
        "id": "army-asc",
        "publisher": "U.S. Army Sustainment Command",
        "kind": "official",
        "title_fallback": "ASC installation community notifications",
        "url": "https://www.army.mil/asc#org-iowa-army-ammunition-plant",
    },
    {
        "id": "iowa-hhs",
        "publisher": "Iowa Health and Human Services",
        "kind": "official",
        "title_fallback": "Iowa HHS fact sheet",
        "url": "https://hhs.iowa.gov/media/19822/download?inline=",
    },
    {
        "id": "illinois-epa",
        "publisher": "Illinois EPA and Illinois Department of Public Health",
        "kind": "official",
        "title_fallback": "Illinois EPA / IDPH statement",
        "url": "https://epa.illinois.gov/content/dam/soi/en/web/epa/about-us/documents/news-releases/2026/11-18-2026-IEPA-IDPH-Iowa-Army-Detonation-Final.pdf",
    },
    {
        "id": "press-cbs",
        "publisher": "CBS Chicago",
        "kind": "press",
        "title_fallback": "CBS Chicago report",
        "url": "https://www.cbsnews.com/chicago/news/army-lead-azide-detonation-iowa-toxic-dust-plume/",
    },
    {
        "id": "press-abc",
        "publisher": "ABC News",
        "kind": "press",
        "title_fallback": "ABC News report",
        "url": "https://abcnews.com/US/iowa-army-plant-lead-azide-detonation/story?id=138261613",
    },
)


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "nav", "header", "footer", "aside", "svg", "form"}:
            self._skip += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "nav", "header", "footer", "aside", "svg", "form"} and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title_parts.append(data)
        else:
            self.parts.append(data)


_CHROME = re.compile(
    r"Skip to main content|An official website of the United States government|"
    r"Here.?s how you know|Official websites use \.gov|"
    r".{0,12}\.gov website belongs to an official government organization.{0,40}|"
    r"Secure \.gov websites use HTTPS|"
    r"A lock \(.{0,80}\) or https:// means you.{0,80}|"
    r"Share sensitive information only on official, secure websites\.?|"
    r"Lock Primary navigation|Primary navigation|Menu Search|"
    r"Share on Twitter|Share on Facebook|Share on Reddit|Share on LinkedIn|Share via Email",
    re.IGNORECASE,
)


def clean_text(text: str, limit: int = 420, prefer: tuple[str, ...] = ()) -> str:
    collapsed = _CHROME.sub(" ", text)
    collapsed = re.sub(r"\s+", " ", collapsed).strip()
    for token in prefer:
        index = collapsed.lower().find(token.lower())
        if index >= 0:
            collapsed = collapsed[index:]
            break
    if len(collapsed) <= limit:
        return collapsed
    cut = collapsed[:limit]
    space = cut.rfind(" ")
    if space > 200:
        cut = cut[:space]
    return cut + "…"


def parse_html(html: str) -> tuple[str, str]:
    parser = _TextExtractor()
    parser.feed(html)
    title = clean_text(" ".join(parser.title_parts), limit=180)
    body = clean_text(
        " ".join(parser.parts),
        prefer=("emergency permit", "controlled detonation", "middletown, iowa --", "public notice of emergency"),
    )
    return title, body


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        }
    )
    return session


def fetch_one(session: requests.Session, source: dict) -> dict:
    base = {
        "id": source["id"],
        "publisher": source["publisher"],
        "kind": source["kind"],
        "url": source["url"],
        "title": source["title_fallback"],
        "status": "unavailable",
        "excerpt": None,
        "note": "",
    }
    try:
        response = session.get(source["url"], timeout=20, allow_redirects=True)
    except requests.RequestException as exc:
        base["note"] = f"Could not retrieve this page ({exc.__class__.__name__}). The link is unchanged."
        return base
    if response.status_code >= 400:
        base["note"] = f"HTTP {response.status_code}. The link is unchanged."
        return base
    raw = response.content[:1_000_000]
    content_type = (response.headers.get("Content-Type") or "").lower()
    if raw.startswith(b"%PDF") or "pdf" in content_type or "pdf" in source["url"].lower():
        base["status"] = "linked"
        base["note"] = "PDF or document link. This archive stores the link, not the file. Open it for the agency's text."
        return base
    text = raw.decode(response.encoding or "utf-8", errors="replace")
    title, body = parse_html(text)
    if title:
        base["title"] = title
    if source["kind"] == "press":
        base["status"] = "linked"
        base["excerpt"] = None
        base["note"] = "News report, not an official advisory. Only the title is kept; the article body is not stored."
        return base
    base["status"] = "excerpt"
    base["excerpt"] = body or None
    if not body or len(body) < 40:
        base["note"] = "The page returned very little text. It may be drawn by a script. Use the link."
    else:
        base["note"] = "Excerpt from the page as retrieved, trimmed for length."
    return base


def read_monitoring(path: Path | None) -> dict:
    missing = (
        "No monitoring file was provided at data/monitoring.csv. "
        "This dashboard does not invent sample results, and model footprints are not measurements."
    )
    if path is None or not Path(path).is_file():
        return {"status": "not_provided", "note": missing, "rows": []}
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        required = {"time", "lat", "lon", "value", "unit", "source"}
        if not required.issubset(set(fields)):
            return {
                "status": "unreadable",
                "note": "data/monitoring.csv must have columns time, lat, lon, value, unit, source.",
                "rows": [],
            }
        rows = []
        for row in reader:
            rows.append({key: (row.get(key) or "").strip() for key in ("time", "lat", "lon", "value", "unit", "source")})
            if len(rows) >= 200:
                break
    note = "Values are shown as supplied. They are not compared with the model and they are not a health determination."
    if len(rows) >= 200:
        note += " Only the first 200 rows are stored."
    return {"status": "listed", "note": note, "rows": rows}


def fetch_official(session: requests.Session | None = None, monitoring_path: Path | None = None) -> dict:
    from pipeline.timeutil import stamp, utc_now

    moment = utc_now()
    if session is not None:
        items = [fetch_one(session, source) for source in OFFICIAL_SOURCES]
    else:
        def run(source):
            with make_session() as local:
                return fetch_one(local, source)

        with ThreadPoolExecutor(max_workers=4) as pool:
            items = list(pool.map(run, OFFICIAL_SOURCES))
    order = {source["id"]: index for index, source in enumerate(OFFICIAL_SOURCES)}
    items.sort(key=lambda item: order[item["id"]])
    return {
        "retrieved_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "retrieved_at_chicago": stamp(moment),
        "preface": (
            "This section is agency and news material. It is not output from the screening model. "
            "If a source was unreachable, the link is still listed."
        ),
        "sources": items,
        "monitoring": read_monitoring(monitoring_path),
    }
