from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import vimail
from tests.fakes import FakeQuery, make_mail


def test_list_unanswered_filters_drafted(monkeypatch) -> None:
    open_mail = make_mail(message_id="<open@x>", subject="Открытое")
    drafted = make_mail(message_id="<drafted@x>", subject="Уже с черновиком")

    monkeypatch.setattr(vimail.list_inbox_ews, "load_libraries", lambda: None)
    monkeypatch.setattr(vimail, "connect", lambda *_a, **_k: SimpleNamespace())
    monkeypatch.setattr(
        vimail,
        "inbox_query",
        lambda _account, _start, _end: FakeQuery([open_mail, drafted]),
    )
    monkeypatch.setattr(
        vimail.reply_draft_ews,
        "draft_reply_index",
        lambda _account: ({"<drafted@x>", "drafted@x"}, set()),
    )

    rows = vimail.list_unanswered("LOGIN", "PASS", start=None, end=None)
    assert len(rows) == 1
    assert rows[0].subject == "Открытое"
    assert rows[0].message_id == "<open@x>"


def test_resolve_until_rejects_future() -> None:
    try:
        vimail.resolve_date_bounds(
            day=None,
            until=date(2026, 12, 1),
            from_date=None,
            to_date=None,
            days_ago=None,
            today=date(2026, 11, 10),
        )
    except SystemExit as exc:
        assert "--until" in str(exc)
    else:
        raise AssertionError("expected SystemExit")
