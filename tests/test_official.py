from pathlib import Path

import requests

from pipeline.official import fetch_official, parse_html, read_monitoring

HTML = """
<html><head><title> Public Notice </title><style>.x{color:red}</style></head>
<body>
<script>secretToken()</script>
<p>The permit is effective November 13, 2026 through February 11, 2027.</p>
</body></html>
"""


class _Response:
    def __init__(self, status, body, content_type="text/html"):
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self.encoding = "utf-8"
        if isinstance(body, str):
            self.content = body.encode()
        else:
            self.content = body


class _Session:
    def __init__(self, responses):
        self.responses = responses

    def get(self, url, timeout=None, allow_redirects=True):
        item = self.responses[url]
        if isinstance(item, Exception):
            raise item
        return item


def test_html_excerpt_drops_government_chrome():
    title, body = parse_html(
        "<html><title>Public Notice | US EPA Lock Primary navigation</title>"
        "<body><p>Skip to main content An official website of the United States government</p>"
        "<p>The permit is effective November 13, 2026.</p></body></html>"
    )
    assert "Lock" not in title
    assert "Skip to main content" not in body
    assert "November 13, 2026" in body


def test_html_excerpt_drops_script_and_style():
    title, body = parse_html(HTML)
    assert title == "Public Notice"
    assert "November 13, 2026" in body
    assert "secretToken" not in body
    assert "color:red" not in body


def test_fetch_degrades_when_a_source_fails():
    from pipeline.official import OFFICIAL_SOURCES

    responses = {}
    for source in OFFICIAL_SOURCES:
        if source["id"] == "epa-public-notice":
            responses[source["url"]] = _Response(200, HTML)
        elif source["id"] == "iowa-hhs":
            responses[source["url"]] = _Response(200, b"%PDF-1.7 fake", "application/pdf")
        elif source["id"] == "press-cbs":
            responses[source["url"]] = _Response(200, "<html><title>CBS headline</title><body>long article body</body></html>")
        elif source["id"] == "army-advisory":
            responses[source["url"]] = requests.ConnectionError("offline")
        else:
            responses[source["url"]] = _Response(503, "nope")
    payload = fetch_official(session=_Session(responses), monitoring_path=Path("/no/such/monitoring.csv"))
    by_id = {item["id"]: item for item in payload["sources"]}
    assert "November 13, 2026" in by_id["epa-public-notice"]["excerpt"]
    assert by_id["iowa-hhs"]["status"] == "linked"
    assert by_id["iowa-hhs"]["excerpt"] is None
    assert by_id["press-cbs"]["excerpt"] is None
    assert "not an official advisory" in by_id["press-cbs"]["note"]
    assert by_id["army-advisory"]["status"] == "unavailable"
    assert by_id["army-advisory"]["url"].startswith("https://")
    assert payload["monitoring"]["status"] == "not_provided"


def test_monitoring_csv_is_listed_without_being_judged(tmp_path):
    path = tmp_path / "monitoring.csv"
    path.write_text("time,lat,lon,value,unit,source\n2026-11-23T18:00Z,41.01,-91.96,0.2,ug/m3,Example lab\n")
    listed = read_monitoring(path)
    assert listed["status"] == "listed"
    assert listed["rows"][0]["unit"] == "ug/m3"
    assert "not compared" in listed["note"]
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n")
    assert read_monitoring(bad)["status"] == "unreadable"
