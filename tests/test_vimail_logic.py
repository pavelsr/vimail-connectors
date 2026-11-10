from __future__ import annotations

import json
from types import SimpleNamespace

import reply_draft_ews
import vimail
from tests.fakes import FakeQuery, make_mail


def test_has_reply_draft_by_message_id() -> None:
    item = make_mail(message_id="<id-1@x>")
    assert reply_draft_ews.has_reply_draft(item, {"<id-1@x>", "id-1@x"}, set()) is True
    assert reply_draft_ews.has_reply_draft(item, {"<other@x>"}, set()) is False


def test_emit_unanswered_json(capsys) -> None:
    rows = [
        vimail.UnansweredMail(
            sender="A <a@x>",
            subject="Hello",
            datetime_received="2026-11-10T12:00:00+03:00",
            message_id="<m@x>",
        )
    ]
    vimail.emit_unanswered(rows, "json")
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "mails": [
            {
                "sender": "A <a@x>",
                "subject": "Hello",
                "datetime_received": "2026-11-10T12:00:00+03:00",
                "message_id": "<m@x>",
            }
        ]
    }


def test_emit_draft_warning_to_stderr(capsys) -> None:
    result = vimail.DraftResult(
        url="https://mail.vimos.ru/owa/#path=/mail/drafts&ItemID=abc",
        warning="Черновик уже существует",
        subject="Тема",
        to="me@vimos.ru",
    )
    vimail.emit_draft(result, "text")
    captured = capsys.readouterr()
    assert "Черновик уже существует" in captured.err
    assert captured.out.strip().startswith("https://mail.vimos.ru/owa/")


def test_emit_draft_json_includes_warning(capsys) -> None:
    result = vimail.DraftResult(
        url="https://example/owa",
        warning="warn",
        subject="S",
        to="t@x",
    )
    vimail.emit_draft(result, "json")
    payload = json.loads(capsys.readouterr().out)
    assert payload["warning"] == "warn"
    assert payload["url"] == "https://example/owa"


def test_find_existing_self_draft() -> None:
    draft = SimpleNamespace(
        id="draft-1",
        subject="Черновик vimail",
        body=SimpleNamespace(content=vimail.DEFAULT_DRAFT_TEXT),
        to_recipients=[SimpleNamespace(email_address="user@vimos.ru")],
    )
    account = SimpleNamespace(drafts=FakeQuery([draft]))
    found = vimail.find_existing_self_draft(
        account,
        recipient="user@vimos.ru",
        subject=vimail.DEFAULT_SELF_SUBJECT,
        body=vimail.DEFAULT_DRAFT_TEXT,
    )
    assert found is draft
    missing = vimail.find_existing_self_draft(
        account,
        recipient="user@vimos.ru",
        subject=vimail.DEFAULT_SELF_SUBJECT,
        body="другой текст",
    )
    assert missing is None


def test_create_reply_draft_warns_when_newest_already_drafted(monkeypatch) -> None:
    first = make_mail(message_id="<first@x>", subject="Первое")
    second = make_mail(message_id="<second@x>", subject="Второе", sender="b@example.com")

    class Reply:
        def save(self, _folder: object) -> SimpleNamespace:
            return SimpleNamespace(id="new-draft")

    second.create_reply = lambda **_kwargs: Reply()
    account = SimpleNamespace(
        inbox=FakeQuery([first, second]),
        drafts=FakeQuery([]),
    )

    monkeypatch.setattr(vimail.list_inbox_ews, "load_libraries", lambda: None)
    monkeypatch.setattr(vimail, "connect", lambda *_a, **_k: account)
    monkeypatch.setattr(
        vimail.reply_draft_ews,
        "draft_reply_index",
        lambda _account: ({"<first@x>", "first@x"}, set()),
    )
    monkeypatch.setattr(
        vimail.reply_draft_ews,
        "apply_threading_headers",
        lambda _account, draft_id, _parent: SimpleNamespace(id=draft_id),
    )
    monkeypatch.setattr(
        vimail.save_draft_ews,
        "draft_view_url",
        lambda item_id: f"https://owa/{item_id}",
    )

    result = vimail.create_reply_draft("LOGIN", "PASSWORD", text="Ответ")
    assert result.url == "https://owa/new-draft"
    assert result.warning is not None
    assert "пропущены письма" in result.warning
    assert "1" in result.warning
