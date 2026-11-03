#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "cryptography>=43",
#   "exchangelib>=5.4",
#   "requests>=2.32",
# ]
# ///
"""Черновик ответа на последнее входящее, у которого такого черновика ещё нет."""

from __future__ import annotations

import argparse
import sys

import list_inbox_ews
import save_draft_ews

REPLY_TEXT = (
    "Здравствуйте! Это ИИ асистент. Письмо получено, помечено как важное, "
    "владелец почты уведомлен"
)
INBOX_FIELDS = (
    "item_class",
    "subject",
    "author",
    "sender",
    "reply_to",
    "message_id",
    "in_reply_to",
    "references",
    "conversation_id",
)
DRAFT_FIELDS = ("in_reply_to", "references", "conversation_id")


def header_tokens(value: str | None) -> set[str]:
    """Идентификаторы из In-Reply-To: с угловыми скобками и без них."""
    if not value:
        return set()
    tokens: set[str] = set()
    for part in value.replace(",", " ").split():
        token = part.strip().casefold()
        if not token:
            continue
        tokens.add(token)
        bare = token.strip("<>")
        if bare:
            tokens.add(bare)
    return tokens


def conversation_token(value: object) -> str:
    if value is None:
        return ""
    raw = getattr(value, "id", None)
    return str(raw if raw else value).strip()


def mailbox_email(mailbox: object) -> str:
    email = str(getattr(mailbox, "email_address", "") or "").strip()
    if "@" not in email or any(char.isspace() for char in email):
        return ""
    return email


def reply_addresses(item: object) -> list[str]:
    """Куда отвечать: Reply-To, иначе From, иначе Sender."""
    reply_to = getattr(item, "reply_to", None) or []
    addresses = [email for mailbox in reply_to if (email := mailbox_email(mailbox))]
    if addresses:
        return addresses
    for mailbox in (getattr(item, "author", None), getattr(item, "sender", None)):
        email = mailbox_email(mailbox) if mailbox is not None else ""
        if email:
            return [email]
    return []


def reply_subject(subject: str | None) -> str:
    text = list_inbox_ews.format_subject(subject)
    if text.casefold().startswith("re:"):
        return text
    return f"RE: {text}"


def message_id_token(value: str | None) -> str:
    token = (value or "").strip()
    if not token:
        return ""
    if token[0] != "<" or token[-1] != ">":
        token = f"<{token.strip('<>')}>"
    return token


def reference_tokens(value: str | None) -> list[str]:
    """Message-ID из References/In-Reply-To в порядке появления, без дублей."""
    seen: set[str] = set()
    ordered: list[str] = []
    for part in (value or "").replace(",", " ").split():
        token = message_id_token(part)
        if not token:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(token)
    return ordered


def reply_in_reply_to(parent: object) -> str:
    token = message_id_token(getattr(parent, "message_id", None))
    if not token:
        raise RuntimeError("у входящего письма нет Message-ID — нельзя собрать In-Reply-To")
    return token


def reply_references(parent: object) -> str:
    """References ответа по RFC 5322 §3.6.4: цепочка родителя плюс его Message-ID."""
    parent_id = reply_in_reply_to(parent)
    chain = reference_tokens(getattr(parent, "references", None))
    if not chain:
        chain = reference_tokens(getattr(parent, "in_reply_to", None))
    if parent_id.casefold() not in {token.casefold() for token in chain}:
        chain.append(parent_id)
    return " ".join(chain)


def connect(login: str, password: str) -> object:
    list_inbox_ews.load_libraries()
    list_inbox_ews.configure_tls()
    credentials = list_inbox_ews.Credentials(login, password)
    config = list_inbox_ews.Configuration(
        server=list_inbox_ews.HOST,
        credentials=credentials,
        auth_type=list_inbox_ews.NTLM,
        version=list_inbox_ews.Version(list_inbox_ews.Build(15, 1, 2507, 61)),
    )
    return list_inbox_ews.Account(
        list_inbox_ews.smtp_address(login),
        config=config,
        autodiscover=False,
        access_type=list_inbox_ews.DELEGATE,
        credentials=credentials,
    )


def draft_reply_index(account: object) -> tuple[set[str], set[str]]:
    """In-Reply-To черновиков и их беседы, если интернет-id у письма нет."""
    tokens: set[str] = set()
    conversations: set[str] = set()
    for draft in account.drafts.all().only(*DRAFT_FIELDS):
        reply_tokens = header_tokens(getattr(draft, "in_reply_to", None))
        if not reply_tokens:
            continue
        tokens |= reply_tokens
        conversation = conversation_token(getattr(draft, "conversation_id", None))
        if conversation:
            conversations.add(conversation)
    return tokens, conversations


def has_reply_draft(item: object, tokens: set[str], conversations: set[str]) -> bool:
    message_keys = header_tokens(getattr(item, "message_id", None))
    if message_keys:
        return bool(message_keys & tokens)
    conversation = conversation_token(getattr(item, "conversation_id", None))
    return bool(conversation) and conversation in conversations


def is_mail(item: object) -> bool:
    item_class = str(getattr(item, "item_class", "") or "")
    return item_class.startswith("IPM.Note")


def choose_incoming(account: object) -> tuple[object, int]:
    """Самое новое письмо IPM.Note без черновика ответа и число пропущенных."""
    tokens, conversations = draft_reply_index(account)
    skipped = 0
    query = account.inbox.all().order_by("-datetime_received").only(*INBOX_FIELDS)
    for item in query:
        if not is_mail(item):
            continue
        if not reply_addresses(item):
            continue
        if has_reply_draft(item, tokens, conversations):
            skipped += 1
            continue
        return item, skipped
    raise SystemExit("Во входящих нет писем без черновика ответа")


def created_item_id(result: object) -> str:
    if isinstance(result, (list, tuple)):
        if len(result) != 1:
            raise RuntimeError(f"сервер вернул {len(result)} результатов вместо одного")
        result = result[0]
    if isinstance(result, Exception):
        raise result
    item_id = getattr(result, "id", None)
    if not isinstance(item_id, str) or not item_id:
        raise RuntimeError("сервер не вернул идентификатор черновика")
    return item_id


def apply_threading_headers(account: object, draft_id: str, parent: object) -> object:
    """Проставить In-Reply-To и References. ConversationId только читается: в EWS он read-only."""
    draft = account.drafts.get(id=draft_id)
    in_reply_to = reply_in_reply_to(parent)
    references = reply_references(parent)
    parent_conversation = conversation_token(getattr(parent, "conversation_id", None))
    draft.in_reply_to = in_reply_to
    draft.references = references
    draft.save(update_fields=["in_reply_to", "references"])
    draft.refresh()
    draft_conversation = conversation_token(getattr(draft, "conversation_id", None))
    if parent_conversation and draft_conversation != parent_conversation:
        raise RuntimeError(
            "ConversationId черновика не совпал с входящим письмом "
            f"({draft_conversation!r} != {parent_conversation!r})"
        )
    print(f"In-Reply-To: {draft.in_reply_to}", file=sys.stderr)
    print(f"References: {draft.references}", file=sys.stderr)
    print(f"ConversationId: {draft_conversation or '(нет)'}", file=sys.stderr)
    return draft


def save_reply_draft(login: str, password: str) -> str:
    """CreateItem ReplyToItem с SaveOnly, затем UpdateItem для заголовков треда."""
    account = connect(login, password)
    item, skipped = choose_incoming(account)
    if skipped:
        print(f"Пропущены письма, у которых уже есть черновик ответа: {skipped}", file=sys.stderr)
    sender = list_inbox_ews.format_sender(getattr(item, "sender", None))
    subject = list_inbox_ews.format_subject(getattr(item, "subject", None))
    print(f"Черновик ответа: {sender} — {subject}", file=sys.stderr)
    reply = item.create_reply(
        subject=reply_subject(getattr(item, "subject", None)),
        body=REPLY_TEXT,
        to_recipients=reply_addresses(item),
    )
    result = reply.save(account.drafts)
    draft = apply_threading_headers(account, created_item_id(result), item)
    return save_draft_ews.draft_view_url(draft.id)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Сохранить черновик ответа на последнее входящее письмо, "
            "у которого такого черновика ещё нет. Письмо не отправляется."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    parse_args(sys.argv[1:] if argv is None else argv)
    env = list_inbox_ews.load_env(list_inbox_ews.ENV_PATH)
    try:
        link = save_reply_draft(env["LOGIN"], env["PASSWORD"])
    except SystemExit:
        raise
    except Exception as exc:
        raise SystemExit(f"Не удалось сохранить черновик ответа по EWS: {exc}") from exc
    print(link)


if __name__ == "__main__":
    main()
