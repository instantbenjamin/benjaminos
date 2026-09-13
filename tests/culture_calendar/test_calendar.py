from types import SimpleNamespace

from culture_calendar.calendar import CultureCalendar, same
from culture_calendar.model import deduplicate, event, google_body, ical
from culture_calendar.normalize import normalize, session_times


def test_lisbon_dst_and_utf8_ical():
    summer = event(
        "ccb",
        "1",
        "Á" * 100,
        "2026-10-24T20:00:00Z",
        "2026-10-24T21:00:00Z",
        "CCB",
        "https://www.ccb.pt/",
    )
    winter = event(
        "ccb",
        "2",
        "Film",
        "2026-10-25T20:00:00Z",
        "2026-10-25T21:00:00Z",
        "CCB",
        "https://www.ccb.pt/",
    )
    assert summer["start"].endswith("+01:00")
    assert winter["start"].endswith("+00:00")
    encoded = ical([summer, winter])
    assert "DTSTART:20261024T200000Z" in encoded
    assert all(len(line.encode()) <= 75 for line in encoded.split("\r\n"))
    assert "SUMMARY:" + "Á" * 100 in encoded.replace("\r\n ", "")


def test_weekday_times_and_unknown_expressions():
    assert session_times("qui: 21h; sex: 21h; sáb: 21h; dom: 17h", "2026-09-13") == [
        ("17:00", None)
    ]
    assert session_times("ter: 21h", "2026-09-13") == []
    assert session_times("21h30–23h00", "2026-09-13") == [("21:30", "23:00")]
    assert session_times("vários horários", "2026-09-13") is None
    assert session_times("21h, consultar programa", "2026-09-13") is None
    assert session_times("25h", "2026-09-13") is None


def agenda(venue="MUDE", subject="artes", hours="vários horários", dates=None):
    return dict(
        id=1,
        title={"rendered": "An exhibition"},
        subject=subject,
        venue={"mude": {"id": 1, "name": venue, "cities": ["Lisboa"]}},
        occurences=dates or ["2026-09-" + str(x) for x in range(13, 20)],
        string_times=hours,
        string_dates="13 a 19 setembro",
        link="https://www.agendalx.pt/event/test",
    )


def test_exhibition_exclusive_end_and_exclusions():
    raw = dict(ccb=[], gulbenkian=[], agendalx=[agenda()])
    plan = normalize(raw, "2026-09-13", "2026-12-13", [])
    assert plan["events"][0]["all_day"]
    assert plan["events"][0]["end"] == "2026-09-20"
    raw["agendalx"] = [agenda(venue="Teatro Maria Matos")]
    plan = normalize(raw, "2026-09-13", "2026-12-13", ["Maria Matos"])
    assert not plan["events"]
    assert plan["skipped"][0]["reason"] == "Excluded institution"


def test_sparse_art_workshop_is_not_exhibition():
    raw = dict(
        ccb=[], gulbenkian=[], agendalx=[agenda(hours="15h00", dates=["2026-09-13", "2026-10-13"])]
    )
    plan = normalize(raw, "2026-09-13", "2026-12-13", [])
    assert len(plan["events"]) == 2
    assert all(not e["all_day"] for e in plan["events"])
    assert "estimated" in plan["events"][0]["notes"]


def test_aggregator_duplicate_and_other_city():
    raw = dict(ccb=[], gulbenkian=[], agendalx=[agenda(venue="MAC/CCB")])
    assert not normalize(raw, "2026-09-13", "2026-12-13", [])["events"]
    raw["agendalx"][0]["venue"]["mude"]["cities"] = ["Porto"]
    assert normalize(raw, "2026-09-13", "2026-12-13", [])["review"]


def test_dedupe_keeps_direct_source_and_distinct_performances():
    a = event(
        "ccb", "1", "Film", "2026-09-13T20:00", "2026-09-13T21:00", "CCB", "https://www.ccb.pt/"
    )
    b = event(
        "agendalx",
        "2",
        "Film",
        a["start"],
        a["end"],
        "Centro Cultural de Belém",
        "https://www.agendalx.pt/",
    )
    c = event(
        "ccb", "3", "Film", "2026-09-14T20:00", "2026-09-14T21:00", "CCB", "https://www.ccb.pt/"
    )
    selected, duplicates = deduplicate([b, a, c])
    assert len(selected) == 2 and selected[0]["source"] == "ccb"
    assert len(duplicates) == 1


class FakeEvents:
    def __init__(self):
        self.items = {}
        self.writes = 0

    def list(self, **kwargs):
        return SimpleNamespace(execute=lambda: {"items": list(self.items.values())})

    def import_(self, calendarId, body):
        def run():
            self.writes += 1
            value = {**body, "id": str(self.writes), "status": "confirmed"}
            self.items[value["id"]] = value
            return value

        return SimpleNamespace(execute=run)

    def patch(self, calendarId, eventId, body, sendUpdates):
        def run():
            self.writes += 1
            self.items[eventId].update(body)
            return self.items[eventId]

        return SimpleNamespace(execute=run)


def test_google_roundtrip_preserves_reminders_and_removals(tmp_path):
    api = FakeEvents()
    cal = object.__new__(CultureCalendar)
    cal.calendar_id, cal.state = "dedicated", tmp_path
    cal.service = SimpleNamespace(
        events=lambda: api, new_batch_http_request=lambda callback: FakeBatch(callback)
    )
    e = event(
        "ccb", "1", "Film", "2026-09-13T20:00", "2026-09-13T21:00", "CCB", "https://www.ccb.pt/"
    )
    ledger = {}
    cal.apply(cal.plan([e], ledger), ledger)
    assert api.writes == 1
    assert cal.plan([e], ledger)[0]["action"] == "unchanged"
    api.items["1"]["reminders"] = {"useDefault": True}
    e["title"] = "Film (updated)"
    cal.apply(cal.plan([e], ledger), ledger)
    assert api.items["1"]["reminders"] == {"useDefault": True}
    assert same(api.items["1"], google_body(e))
    api.items.clear()
    assert cal.plan([e], ledger)[0]["action"] == "skip_removed"


def test_date_and_datetime_are_not_equivalent():
    assert not same(
        {"start": {"date": "2026-09-13"}}, {"start": {"dateTime": "2026-09-13T20:00:00+01:00"}}
    )


class FakeBatch:
    def __init__(self, callback):
        self.callback = callback
        self.requests = []

    def add(self, request, request_id):
        self.requests.append((request_id, request))

    def execute(self):
        for request_id, request in self.requests:
            try:
                result = request.execute()
            except Exception as exc:
                self.callback(request_id, None, exc)
            else:
                self.callback(request_id, result, None)


def test_event_across_fall_clock_change():
    e = event(
        "ccb",
        "night",
        "Night show",
        "2026-10-25T00:45:00Z",
        "2026-10-25T01:15:00Z",
        "CCB",
        "https://www.ccb.pt/",
    )
    assert e["start"] == "2026-10-25T01:45:00+01:00"
    assert e["end"] == "2026-10-25T01:15:00+00:00"
