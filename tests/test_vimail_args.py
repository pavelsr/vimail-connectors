from __future__ import annotations

from datetime import date

import pytest

import vimail


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        vimail.build_parser().parse_args(["--help"])
    assert exc.value.code == 0


def test_unanswered_default_no_date_filter() -> None:
    args = vimail.build_parser().parse_args(["unanswered"])
    assert args.command == "unanswered"
    assert args.day is None
    assert args.until is None
    assert args.from_date is None
    assert args.to_date is None
    assert args.days_ago is None
    assert vimail.output_format(args) == "text"


def test_format_json_global() -> None:
    args = vimail.build_parser().parse_args(["--format", "json", "draft-self"])
    assert vimail.output_format(args) == "json"
    assert args.text == vimail.DEFAULT_DRAFT_TEXT


def test_format_json_after_subcommand() -> None:
    args = vimail.build_parser().parse_args(["unanswered", "--format", "json", "--day", "2026-11-10"])
    assert vimail.output_format(args) == "json"
    assert args.day.isoformat() == "2026-11-10"


def test_format_default_text() -> None:
    args = vimail.build_parser().parse_args(["unanswered"])
    assert vimail.output_format(args) == "text"


def test_draft_reply_custom_text() -> None:
    args = vimail.build_parser().parse_args(["draft-reply", "--text", "Привет"])
    assert args.text == "Привет"


@pytest.mark.parametrize(
    ("argv", "start", "end"),
    [
        (["unanswered", "--day", "2026-11-10"], date(2026, 11, 10), date(2026, 11, 11)),
        (["unanswered", "--until", "2026-11-01"], date(2026, 11, 1), date(2026, 11, 11)),
        (
            ["unanswered", "--from", "2026-11-01", "--to", "2026-11-05"],
            date(2026, 11, 1),
            date(2026, 11, 6),
        ),
        (["unanswered", "--days-ago", "3"], date(2026, 11, 7), date(2026, 11, 8)),
        (["unanswered"], None, None),
    ],
)
def test_resolve_date_bounds(argv: list[str], start: date | None, end: date | None) -> None:
    args = vimail.build_parser().parse_args(argv)
    got_start, got_end = vimail.resolve_date_bounds(
        day=args.day,
        until=args.until,
        from_date=args.from_date,
        to_date=args.to_date,
        days_ago=args.days_ago,
        today=date(2026, 11, 10),
    )
    assert (got_start, got_end) == (start, end)


def test_resolve_rejects_mixed_filters() -> None:
    args = vimail.build_parser().parse_args(["unanswered", "--day", "2026-11-10", "--days-ago", "1"])
    with pytest.raises(SystemExit, match="только один режим"):
        vimail.resolve_date_bounds(
            day=args.day,
            until=args.until,
            from_date=args.from_date,
            to_date=args.to_date,
            days_ago=args.days_ago,
            today=date(2026, 11, 10),
        )


def test_resolve_requires_both_from_and_to() -> None:
    args = vimail.build_parser().parse_args(["unanswered", "--from", "2026-11-01"])
    with pytest.raises(SystemExit, match="и --from, и --to"):
        vimail.resolve_date_bounds(
            day=args.day,
            until=args.until,
            from_date=args.from_date,
            to_date=args.to_date,
            days_ago=args.days_ago,
            today=date(2026, 11, 10),
        )
