"""Portable Lisbon programme collection, preview, iCal export and Google sync."""

import argparse
import datetime as dt
import json
import os
from collections import Counter
from pathlib import Path

from movie_calendar.infisical import credentials
from movie_calendar.storage import run_lock, write_json

from .calendar import CultureCalendar
from .model import LISBON, ical
from .normalize import normalize
from .sources import Reader, collect


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=os.getenv("CULTURE_CALENDAR_CONFIG"),
        required=not os.getenv("CULTURE_CALENDAR_CONFIG"),
    )
    parser.add_argument("--from", dest="start", default=dt.datetime.now(LISBON).date().isoformat())
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument(
        "--snapshot", type=Path, help="Use an operator-provided raw programme snapshot"
    )
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--google", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.days <= 366:
        parser.error("--days must be between 1 and 366")
    if args.apply and not args.google:
        parser.error("--apply requires --google")
    config = json.loads(Path(args.config).expanduser().read_text())
    state = Path(config["state_dir"]).expanduser()
    end = (dt.date.fromisoformat(args.start) + dt.timedelta(days=args.days)).isoformat()
    with run_lock(state):
        raw = (
            json.loads(args.snapshot.read_text())
            if args.snapshot
            else collect(Reader(state, args.fresh), args.start, end)
        )
        plan = normalize(raw, args.start, end, config.get("excluded_institutions", []))
        write_json(state / "raw.json", raw)
        write_json(state / "events.json", plan["events"])
        (state / "calendar.ics").write_text(ical(plan["events"]), newline="")
        plan["applied"] = False
        write_json(state / "plan.json", plan)
        if args.google:
            if not all(raw.get(source) for source in ("ccb", "gulbenkian", "agendalx")):
                raise ValueError("All three source collections are required before Google writes")
            with credentials(config.get("infisical"), trakt=False, google=True):
                calendar = CultureCalendar(config["google"], state)
                ledger_file = state / "google-ledger.json"
                ledger = json.loads(ledger_file.read_text()) if ledger_file.exists() else {}
                plan["google_changes"] = calendar.plan(plan["events"], ledger)
                write_json(state / "plan.json", plan)
                if args.apply:
                    if not plan["events"]:
                        raise ValueError("Empty programme: refusing writes")
                    calendar.apply(plan["google_changes"], ledger)
                    verification = calendar.plan(plan["events"], ledger)
                    if any(x["action"] in {"create", "update"} for x in verification):
                        raise RuntimeError(
                            "Google verification failed; inspect plan before retrying"
                        )
                    plan["verification"] = dict(Counter(x["action"] for x in verification))
                    plan["applied"] = True
                    write_json(state / "plan.json", plan)
        print(
            json.dumps(
                {
                    "events": len(plan["events"]),
                    "by_source": dict(Counter(e["source"] for e in plan["events"])),
                    "review": len(plan["review"]),
                    "skipped": len(plan["skipped"]),
                    "applied": plan["applied"],
                    "changes": dict(Counter(x["action"] for x in plan.get("google_changes", []))),
                    "verification": plan.get("verification"),
                    "state_dir": str(state),
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
