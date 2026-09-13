"""One entry point for humans, agents and schedulers; preview is the default."""

import argparse
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .google_calendar import GoogleCalendar
from .infisical import credentials
from .matching import match
from .source import calendar, scrape
from .storage import run_lock, write_json
from .trakt import Trakt


def run(
    config: dict,
    *,
    apply: bool = False,
    use_trakt: bool = False,
    use_google: bool = False,
    from_date: str | None = None,
    fresh: bool = False,
) -> dict:
    """Produce a complete plan before downstream mutations. Never delete events."""
    state = Path(config["state_dir"]).expanduser().resolve()
    if apply and not (use_trakt or use_google):
        raise ValueError("--apply requires --trakt or --google")
    selection = config.get("selection", "all")
    if selection not in {"all", "list", "watchlist"}:
        raise ValueError("selection must be all, list or watchlist")
    if selection != "all" and not use_trakt:
        raise ValueError("List/watchlist selection requires --trakt")
    catalog_path = Path(
        config.get("catalog", Path(__file__).with_name("catalog.json"))
    ).expanduser()
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1:
        raise ValueError("Unsupported catalog schema")
    with run_lock(state), credentials(config.get("infisical"), trakt=use_trakt, google=use_google):
        report = scrape(
            state / "cache",
            from_date or dt.datetime.now(ZoneInfo("Europe/Lisbon")).date().isoformat(),
            0 if fresh else 3600,
        )
        events, unresolved = match(report["upcoming_screenings"], catalog)
        reviewed_ids = {ident for event in events for ident in event["trakt_ids"]}
        additions, watch_matches, selected = [], [], report["upcoming_screenings"]
        trakt = None
        google = None
        try:
            if use_trakt:
                target = config["trakt"]
                trakt = Trakt(state, target["username"])
                trakt.verify_account()
                list_id = str(target["list_id"])
                listed = trakt.movie_ids(trakt.list_path(list_id) + "/movies")
                watched = trakt.movie_ids("users/me/watchlist/movies")
                if target.get("add_reviewed_to_list", False):
                    additions = sorted(reviewed_ids - listed)
                watch_matches = sorted(reviewed_ids & watched)
                selected_ids = watched if selection == "watchlist" else listed | set(additions)
                if selection != "all":
                    selected = [
                        event for event in events if selected_ids.intersection(event["trakt_ids"])
                    ]
            changes = []
            if use_google:
                target = config["google"]
                google = GoogleCalendar(
                    target["calendar_id"], target["subject"], target["service_account"]
                )
                changes = google.plan(selected)
            plan = {
                "schema_version": 1,
                "fetched_at": report["fetched_at"],
                "scope": report["scope"],
                "screenings": len(report["upcoming_screenings"]),
                "selected_screenings": len(selected),
                "reviewed_movies": len(reviewed_ids),
                "trakt_additions": additions,
                "watchlist_matches": watch_matches,
                "unresolved": unresolved,
                "google_changes": changes,
                "applied": False,
            }
            write_json(state / "programme.json", report)
            write_json(state / "plan.json", plan)
            write_json(state / "selected-screenings.json", selected)
            # Atomic replacement so a subscriber never reads a partial calendar.
            temporary = state / "calendar.ics.tmp"
            temporary.write_bytes(calendar(selected).encode("utf-8"))
            temporary.replace(state / "calendar.ics")
            if apply:
                if trakt and additions:
                    trakt.add(list_id, additions)
                    if not set(additions).issubset(
                        trakt.movie_ids(trakt.list_path(list_id) + "/movies")
                    ):
                        raise RuntimeError("Trakt list verification failed; plan retained")
                if google:
                    google.apply(changes)
                    remaining = google.plan(selected)
                    if any(item["action"] in {"create", "update"} for item in remaining):
                        raise RuntimeError("Calendar verification failed; rerun is safe")
                plan["applied"] = True
                write_json(state / "plan.json", plan)
            return plan
        finally:
            if trakt:
                trakt.http.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "login"])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--from", dest="from_date")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--trakt", action="store_true")
    parser.add_argument("--google", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.expanduser().read_text(encoding="utf-8"))
    if args.command == "login":
        state = Path(config["state_dir"]).expanduser()
        with run_lock(state), credentials(config.get("infisical"), trakt=True, google=False):
            client = Trakt(state, config["trakt"]["username"])
            try:
                client.login()
            finally:
                client.http.close()
        print("Trakt account verified; tokens saved privately.")
        return
    plan = run(
        config,
        apply=args.apply,
        use_trakt=args.trakt,
        use_google=args.google,
        from_date=args.from_date,
        fresh=args.fresh,
    )
    print(
        json.dumps(
            {
                k: plan[k]
                for k in (
                    "screenings",
                    "selected_screenings",
                    "reviewed_movies",
                    "watchlist_matches",
                    "applied",
                )
            }
            | {
                "unresolved": len(plan["unresolved"]),
                "trakt_additions": len(plan["trakt_additions"]),
                "calendar_changes": {
                    action: sum(c["action"] == action for c in plan["google_changes"])
                    for action in ("create", "update", "unchanged", "review", "skip_cancelled")
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
