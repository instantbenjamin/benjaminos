import pytest
from culture_calendar.sources import ccb, gulbenkian


class FakeReader:
    def __init__(self, pages):
        self.pages = pages

    def json(self, url, **params):
        return self.pages[params.get("page", 1)], {}


def test_ccb_follows_all_pages_and_rejects_repeats():
    reader = FakeReader(
        {
            1: {"events": [{"id": 1}], "total_pages": 2, "total": 2},
            2: {"events": [{"id": 2}], "total_pages": 2, "total": 2},
        }
    )
    assert [e["id"] for e in ccb(reader, "2026-09-13", "2026-12-13")] == [1, 2]
    reader.pages[2]["events"] = [{"id": 1}]
    with pytest.raises(ValueError, match="incomplete or repeated"):
        ccb(reader, "2026-09-13", "2026-12-13")


def test_gulbenkian_same_production_can_span_multiple_session_pages():
    class Reader:
        def get(self, url, **params):
            assert params["page"] in {1, 2}
            return '<article data-event-id="123"></article>', {"x-wp-totalpages": "2"}

        def json(self, url, **params):
            assert params["include"] == "123"
            return [{"id": 123}], {}

    assert gulbenkian(Reader()) == [{"id": 123}]


def test_gulbenkian_missing_details_aborts():
    class Reader:
        def get(self, url, **params):
            return '<article data-event-id="123"></article>', {"x-wp-totalpages": "1"}

        def json(self, url, **params):
            return [], {}

    with pytest.raises(ValueError, match="details incomplete"):
        gulbenkian(Reader())
