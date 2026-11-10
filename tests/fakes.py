from __future__ import annotations

from types import SimpleNamespace


class FakeQuery(list):
    def order_by(self, *_args: object, **_kwargs: object) -> FakeQuery:
        return self

    def only(self, *_args: object, **_kwargs: object) -> FakeQuery:
        return self

    def filter(self, **_kwargs: object) -> FakeQuery:
        return self

    def all(self) -> FakeQuery:
        return self


def make_mail(
    *,
    message_id: str,
    subject: str = "Тема",
    sender: str = "a@example.com",
    item_class: str = "IPM.Note",
    conversation_id: str = "conv-1",
) -> SimpleNamespace:
    mailbox = SimpleNamespace(email_address=sender, name="Sender")
    return SimpleNamespace(
        item_class=item_class,
        subject=subject,
        author=mailbox,
        sender=mailbox,
        reply_to=[],
        message_id=message_id,
        in_reply_to=None,
        references=None,
        conversation_id=SimpleNamespace(id=conversation_id),
        datetime_received=None,
        create_reply=None,
    )
