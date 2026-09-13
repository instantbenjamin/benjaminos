"""Behavioral regressions for source extraction, identity and calendar output."""

import copy
import datetime as dt
import json
from pathlib import Path

import pytest
from movie_calendar import cli, matching, source
from movie_calendar.google_calendar import GoogleCalendar, event_body, uid
from movie_calendar.storage import run_lock, write_json


def html(title="FILM", date="14/09/2026, 15h30", total=""):
    return f"""<div class="sectionLayoutProgram">
    <a href="?ciclo=1&amp;id=42"><div class="lista">film</div></a>
    <div class="infoDetail"><span class="infoDate">{date} | Sala Félix</span>
    <span class="infoDate">Cycle</span><h2 class="infoTitleProg">{title}</h2>
    <div class="infoBiblio">de Example Director</div>
    <div class="infoBiblio">1986 - 120 min</div>
    <div class="infoText">{total}</div></div></div>"""


def event():
    return source.extract(source.Tree(html()).root, source.BASE + "?ciclo=1&page=2")[0]


def test_extract_date_timezone_and_deep_link():
    e = event()
    assert e["start"] == "2026-09-14T15:30:00+01:00"
    assert e["url"].endswith("?ciclo=1&page=2&id=42")
    assert e["year"] == 1986
    winter = source.extract(source.Tree(html(date="14/12/2026, 15h30")).root, source.BASE)[0]
    assert winter["start"].endswith("+00:00")


def test_multi_film_does_not_inherit_first_films_duration():
    unknown = source.extract(source.Tree(html(title="ONE | TWO")).root, source.BASE)[0]
    assert unknown["runtime_minutes"] is None
    known = source.extract(
        source.Tree(html(title="ONE | TWO", total="Duração total: 160 min")).root, source.BASE
    )[0]
    assert known["runtime_minutes"] == 160


def test_structure_mismatch_fails():
    with pytest.raises(ValueError, match="mismatch"):
        source.extract(
            source.Tree(html().replace('class="lista"', 'class="unknown"')).root, source.BASE
        )


def test_ics_uid_escaping_utf8_folding_and_utc():
    e = event() | {"title": "á" * 90 + ",;\\\r\nBEGIN:VEVENT"}
    ics = source.calendar([e])
    assert "UID:" + uid(e) in ics
    assert "DTSTART:20260914T143000Z" in ics
    assert "DTEND:20260914T163000Z" in ics
    assert ics.count("\r\nBEGIN:VEVENT\r\n") == 1
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))
    assert "\\,\\;\\\\\\nBEGIN:VEVENT" in ics.replace("\r\n ", "")
    assert "TRANSP:TRANSPARENT" in ics


def test_wrong_director_and_unknown_multi_film_stay_unresolved():
    e = event()
    catalog = {"films": [{**e, "director": "Other Director", "trakt_id": 1}]}
    matched, unresolved = matching.match([e], catalog)
    assert not matched[0]["trakt_ids"]
    assert len(unresolved) == 1
    matched, unresolved = matching.match([e | {"multiple_films": True}], catalog)
    assert matched == []
    assert "Multi-film" in unresolved[0]["reason"]


def test_partial_multi_film_match_keeps_one_screening():
    e = event() | {"multiple_films": True}
    film = {"title": "Short", "year": 2000, "director": "Director"}
    catalog = {
        "films": [film | {"trakt_id": 12}],
        "screening_overrides": {"42": [film, film | {"title": "Unknown"}]},
    }
    matched, unresolved = matching.match([e], catalog)
    assert len(matched) == len(unresolved) == 1
    assert matched[0]["trakt_ids"] == [12]
    assert matched[0]["runtime_minutes"] == e["runtime_minutes"]


class Reply:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class FakeEvents:
    def __init__(self):
        self.rows = []
        self.writes = 0

    def events(self):
        return self

    def list(self, **kwargs):
        return Reply(
            {"items": [copy.deepcopy(e) for e in self.rows if e["iCalUID"] == kwargs["iCalUID"]]}
        )

    def import_(self, **kwargs):
        self.rows.append(copy.deepcopy(kwargs["body"]) | {"id": "google-1"})
        self.writes += 1
        return Reply(self.rows[-1])

    def patch(self, **kwargs):
        assert kwargs["sendUpdates"] == "none"
        self.rows[0].update(kwargs["body"])
        self.writes += 1
        return Reply(self.rows[0])


def google():
    adapter = GoogleCalendar.__new__(GoogleCalendar)
    adapter.service = FakeEvents()
    adapter.calendar_id = "dedicated"
    return adapter


def test_two_syncs_one_event_then_changed_time_updates():
    adapter = google()
    e = event()
    adapter.apply(adapter.plan([e]))
    adapter.apply(adapter.plan([e]))
    assert adapter.service.writes == 1
    assert len(adapter.service.rows) == 1
    e["start"] = "2026-09-14T17:30:00+01:00"
    adapter.apply(adapter.plan([e]))
    assert adapter.service.writes == 2
    assert len(adapter.service.rows) == 1


def test_existing_ics_import_adopted_reminders_preserved():
    adapter = google()
    e = event()
    adapter.service.rows = [
        {
            **event_body(e),
            "id": "old-import",
            "iCalUID": uid(e),
            "description": "Old imported description",
            "reminders": {"useDefault": True},
        }
    ]
    assert adapter.plan([e])[0]["action"] == "update"
    adapter.apply(adapter.plan([e]))
    assert adapter.service.rows[0]["id"] == "old-import"
    assert adapter.service.rows[0]["reminders"] == {"useDefault": True}


def test_cancelled_duplicate_and_missing_duration():
    adapter = google()
    e = event()
    adapter.service.rows = [{"id": "cancelled", "iCalUID": uid(e), "status": "cancelled"}]
    adapter.apply(adapter.plan([e]))
    assert adapter.service.writes == 0
    adapter.service.rows *= 2
    with pytest.raises(ValueError, match="Duplicate"):
        adapter.plan([e])
    assert adapter.plan([e | {"runtime_minutes": None}])[0]["action"] == "review"


def test_crawl_visits_pagination_and_deduplicates(monkeypatch, tmp_path):
    calls = []

    def fetch(url, cache, ttl):
        calls.append(url)
        value = '<a href="?ciclo=1">cycle</a>' if url == source.BASE else html()
        if url.endswith("?ciclo=1"):
            value += '<div class="sectionPagination"><a href="?ciclo=1&amp;page=2">2</a></div>'
        return source.Tree(value).root

    monkeypatch.setattr(source, "fetch", fetch)
    report = source.scrape(tmp_path, "2026-09-01")
    assert len(calls) == 3
    assert report["total_screenings"] == 1
    assert len(report["pages"]) == 2


def test_source_failure_prevents_downstream_access(monkeypatch, tmp_path):
    def fail(*args):
        raise ValueError("broken source")

    monkeypatch.setattr(cli, "scrape", fail)
    with pytest.raises(ValueError, match="broken source"):
        cli.run({"state_dir": str(tmp_path)}, apply=True, use_google=True, use_trakt=True)
    assert not (tmp_path / "plan.json").exists()


def test_private_atomic_storage_and_lock(tmp_path):
    target = tmp_path / "tokens.json"
    write_json(target, {"test": 1})
    assert target.stat().st_mode & 0o777 == 0o600
    assert json.loads(target.read_text()) == {"test": 1}
    with run_lock(tmp_path), pytest.raises(RuntimeError, match="active"), run_lock(tmp_path):
        pass


def test_bundled_catalog_is_valid():
    catalog = json.loads(Path(matching.__file__).with_name("catalog.json").read_text())
    assert len(catalog["films"]) == 43
    assert len({matching.key(f) for f in catalog["films"]}) == 43
    matching.match([], catalog)
    assert dt.date.fromisoformat(catalog["reviewed_on"])
