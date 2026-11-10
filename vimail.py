#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "cryptography>=43",
#   "exchangelib>=5.4",
#   "requests>=2.32",
# ]
# ///
"""CLI-утилита vimail: неотвеченные письма и черновики через EWS."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import list_inbox_ews
import reply_draft_ews
import save_draft_ews

DEFAULT_DRAFT_TEXT = "Это черновик, созданный утилитой vimail"
DEFAULT_SELF_SUBJECT = "Черновик vimail"
MAILBOX_TZ = ZoneInfo("Europe/Moscow")
INBOX_FIELDS = (
    *reply_draft_ews.INBOX_FIELDS,
    "datetime_received",
)
DRAFT_SELF_FIELDS = ("subject", "body", "to_recipients")


@dataclass(frozen=True)
class UnansweredMail:
    sender: str
    subject: str
    datetime_received: str
    message_id: str


@dataclass(frozen=True)
class DraftResult:
    url: str
    warning: str | None = None
    subject: str | None = None
    to: str | None = None


def parse_iso_date(value: str, option: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{option} ожидается в формате YYYY-MM-DD"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    format_parent = argparse.ArgumentParser(add_help=False)
    format_parent.add_argument(
        "--format",
        choices=("text", "json"),
        default=argparse.SUPPRESS,
        help="формат вывода (по умолчанию text)",
    )
    parser = argparse.ArgumentParser(
        prog="vimail",
        description="Неотвеченные письма и черновики для mail.vimos.ru (EWS).",
        parents=[format_parent],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    unanswered = sub.add_parser(
        "unanswered",
        parents=[format_parent],
        help="показать неотвеченные входящие (без черновика ответа)",
    )
    unanswered.add_argument(
        "--day",
        metavar="YYYY-MM-DD",
        type=lambda value: parse_iso_date(value, "--day"),
        help="письма только за этот день",
    )
    unanswered.add_argument(
        "--until",
        metavar="YYYY-MM-DD",
        type=lambda value: parse_iso_date(value, "--until"),
        help="письма с этой даты по сегодня включительно",
    )
    unanswered.add_argument(
        "--from",
        dest="from_date",
        metavar="YYYY-MM-DD",
        type=lambda value: parse_iso_date(value, "--from"),
        help="начало диапазона (включительно), вместе с --to",
    )
    unanswered.add_argument(
        "--to",
        dest="to_date",
        metavar="YYYY-MM-DD",
        type=lambda value: parse_iso_date(value, "--to"),
        help="конец диапазона (включительно), вместе с --from",
    )
    unanswered.add_argument(
        "--days-ago",
        type=int,
        metavar="N",
        help="письма ровно за день N дней назад",
    )

    draft_self = sub.add_parser(
        "draft-self",
        parents=[format_parent],
        help="создать черновик письма самому себе",
    )
    draft_self.add_argument(
        "--text",
        default=DEFAULT_DRAFT_TEXT,
        help=f'текст письма (по умолчанию: "{DEFAULT_DRAFT_TEXT}")',
    )
    draft_self.add_argument(
        "--subject",
        default=DEFAULT_SELF_SUBJECT,
        help=f'тема письма (по умолчанию: "{DEFAULT_SELF_SUBJECT}")',
    )

    draft_reply = sub.add_parser(
        "draft-reply",
        parents=[format_parent],
        help="создать черновик ответа на последнее неотвеченное входящее",
    )
    draft_reply.add_argument(
        "--text",
        default=DEFAULT_DRAFT_TEXT,
        help=f'текст ответа (по умолчанию: "{DEFAULT_DRAFT_TEXT}")',
    )
    return parser


def resolve_date_bounds(
    *,
    day: date | None,
    until: date | None,
    from_date: date | None,
    to_date: date | None,
    days_ago: int | None,
    today: date,
) -> tuple[date | None, date | None]:
    """Вернуть [start, end) в календарных днях MSK или (None, None) без фильтра."""
    modes = [
        day is not None,
        until is not None,
        from_date is not None or to_date is not None,
        days_ago is not None,
    ]
    if sum(modes) > 1:
        raise SystemExit(
            "Укажите только один режим фильтра: --day, --until, --from/--to или --days-ago"
        )
    if day is not None:
        return day, day + timedelta(days=1)
    if until is not None:
        if until > today:
            raise SystemExit("--until не может быть позже сегодняшнего дня")
        return until, today + timedelta(days=1)
    if from_date is not None or to_date is not None:
        if from_date is None or to_date is None:
            raise SystemExit("Для диапазона укажите и --from, и --to")
        if from_date > to_date:
            raise SystemExit("--from не может быть позже --to")
        return from_date, to_date + timedelta(days=1)
    if days_ago is not None:
        if days_ago < 0:
            raise SystemExit("--days-ago должен быть не меньше 0")
        target = today - timedelta(days=days_ago)
        return target, target + timedelta(days=1)
    return None, None


def connect(login: str, password: str) -> Any:
    return reply_draft_ews.connect(login, password)


def format_received(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        local = value.astimezone(MAILBOX_TZ) if value.tzinfo else value.replace(tzinfo=MAILBOX_TZ)
        return local.isoformat(timespec="seconds")
    return str(value)


def inbox_query(account: Any, start: date | None, end: date | None) -> Any:
    query = account.inbox.all()
    if start is not None and end is not None:
        tz = list_inbox_ews.EWSTimeZone.from_timezone(MAILBOX_TZ)
        ews_start = list_inbox_ews.EWSDateTime(start.year, start.month, start.day, tzinfo=tz)
        ews_end = list_inbox_ews.EWSDateTime(end.year, end.month, end.day, tzinfo=tz)
        query = query.filter(datetime_received__gte=ews_start, datetime_received__lt=ews_end)
    return query.order_by("-datetime_received").only(*INBOX_FIELDS)


def list_unanswered(
    login: str,
    password: str,
    *,
    start: date | None,
    end: date | None,
) -> list[UnansweredMail]:
    list_inbox_ews.load_libraries()
    account = connect(login, password)
    tokens, conversations = reply_draft_ews.draft_reply_index(account)
    rows: list[UnansweredMail] = []
    for item in inbox_query(account, start, end):
        if not reply_draft_ews.is_mail(item):
            continue
        if not reply_draft_ews.reply_addresses(item):
            continue
        if reply_draft_ews.has_reply_draft(item, tokens, conversations):
            continue
        rows.append(
            UnansweredMail(
                sender=list_inbox_ews.format_sender(getattr(item, "sender", None)),
                subject=list_inbox_ews.format_subject(getattr(item, "subject", None)),
                datetime_received=format_received(getattr(item, "datetime_received", None)),
                message_id=str(getattr(item, "message_id", "") or ""),
            )
        )
    return rows


def draft_body_text(value: object | None) -> str:
    if value is None:
        return ""
    text = getattr(value, "content", None)
    if text is None:
        text = value
    return str(text).strip()


def find_existing_self_draft(account: Any, *, recipient: str, subject: str, body: str) -> Any | None:
    want_subject = subject.strip()
    want_body = body.strip()
    want_to = recipient.casefold()
    for draft in account.drafts.all().only(*DRAFT_SELF_FIELDS):
        if list_inbox_ews.format_subject(getattr(draft, "subject", None)) != want_subject:
            continue
        if draft_body_text(getattr(draft, "body", None)) != want_body:
            continue
        recipients = getattr(draft, "to_recipients", None) or []
        emails = {
            str(getattr(mailbox, "email_address", "") or "").strip().casefold()
            for mailbox in recipients
        }
        if want_to in emails:
            return draft
    return None


def create_self_draft(
    login: str,
    password: str,
    *,
    text: str,
    subject: str = DEFAULT_SELF_SUBJECT,
) -> DraftResult:
    body = text.strip() or DEFAULT_DRAFT_TEXT
    subject_text = subject.strip() or DEFAULT_SELF_SUBJECT
    recipient = list_inbox_ews.smtp_address(login)
    list_inbox_ews.load_libraries()
    account = connect(login, password)
    existing = find_existing_self_draft(
        account,
        recipient=recipient,
        subject=subject_text,
        body=body,
    )
    if existing is not None and getattr(existing, "id", None):
        return DraftResult(
            url=save_draft_ews.draft_view_url(existing.id),
            warning="Черновик письма себе с таким текстом уже существует",
            subject=subject_text,
            to=recipient,
        )
    url = save_draft_ews.save_draft(
        login,
        password,
        recipient=recipient,
        subject=subject_text,
        body=body,
    )
    return DraftResult(url=url, subject=subject_text, to=recipient)


def create_reply_draft(login: str, password: str, *, text: str) -> DraftResult:
    body = text.strip() or DEFAULT_DRAFT_TEXT
    list_inbox_ews.load_libraries()
    account = connect(login, password)
    tokens, conversations = reply_draft_ews.draft_reply_index(account)
    skipped = 0
    first_eligible_had_draft = False
    seen_eligible = False
    chosen = None
    query = account.inbox.all().order_by("-datetime_received").only(*reply_draft_ews.INBOX_FIELDS)
    for item in query:
        if not reply_draft_ews.is_mail(item):
            continue
        if not reply_draft_ews.reply_addresses(item):
            continue
        if reply_draft_ews.has_reply_draft(item, tokens, conversations):
            if not seen_eligible:
                first_eligible_had_draft = True
            seen_eligible = True
            skipped += 1
            continue
        seen_eligible = True
        chosen = item
        break
    if chosen is None:
        raise SystemExit(
            "Черновик ответа на последнее неотвеченное уже создан; "
            "писем без черновика ответа нет"
        )
    warning = None
    if first_eligible_had_draft or skipped:
        warning = (
            f"Предупреждение: пропущены письма с уже созданным черновиком ответа: {skipped}"
        )
    reply = chosen.create_reply(
        subject=reply_draft_ews.reply_subject(getattr(chosen, "subject", None)),
        body=body,
        to_recipients=reply_draft_ews.reply_addresses(chosen),
    )
    result = reply.save(account.drafts)
    draft_id = reply_draft_ews.created_item_id(result)
    try:
        draft = reply_draft_ews.apply_threading_headers(account, draft_id, chosen)
        draft_id = draft.id
    except RuntimeError as exc:
        # У части писем (часто Fw:/внешние) Exchange не совпадает ConversationId —
        # In-Reply-To/References уже записаны, черновик пригоден.
        if "ConversationId" not in str(exc):
            raise
        conv_warning = f"Предупреждение: {exc}"
        warning = f"{warning}; {conv_warning}" if warning else conv_warning
    return DraftResult(
        url=save_draft_ews.draft_view_url(draft_id),
        warning=warning,
        subject=reply_draft_ews.reply_subject(getattr(chosen, "subject", None)),
        to=", ".join(reply_draft_ews.reply_addresses(chosen)),
    )


def emit_unanswered(rows: list[UnansweredMail], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps({"mails": [asdict(row) for row in rows]}, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("Неотвеченных писем не найдено")
        return
    for row in rows:
        print(f"{row.sender} — {row.subject}")


def emit_draft(result: DraftResult, fmt: str) -> None:
    if result.warning:
        print(result.warning, file=sys.stderr)
    if fmt == "json":
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return
    print(result.url)


def today_moscow() -> date:
    return datetime.now(MAILBOX_TZ).date()


def output_format(args: argparse.Namespace) -> str:
    return getattr(args, "format", "text")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    fmt = output_format(args)
    env = list_inbox_ews.load_env(list_inbox_ews.ENV_PATH)
    login = env["LOGIN"]
    password = env["PASSWORD"]

    if args.command == "unanswered":
        start, end = resolve_date_bounds(
            day=args.day,
            until=args.until,
            from_date=args.from_date,
            to_date=args.to_date,
            days_ago=args.days_ago,
            today=today_moscow(),
        )
        try:
            rows = list_unanswered(login, password, start=start, end=end)
        except Exception as exc:
            raise SystemExit(f"Не удалось получить неотвеченные письма: {exc}") from exc
        emit_unanswered(rows, fmt)
        return

    if args.command == "draft-self":
        try:
            result = create_self_draft(
                login,
                password,
                text=args.text,
                subject=args.subject,
            )
        except Exception as exc:
            raise SystemExit(f"Не удалось создать черновик себе: {exc}") from exc
        emit_draft(result, fmt)
        return

    if args.command == "draft-reply":
        try:
            result = create_reply_draft(login, password, text=args.text)
        except SystemExit:
            raise
        except Exception as exc:
            raise SystemExit(f"Не удалось создать черновик ответа: {exc}") from exc
        emit_draft(result, fmt)
        return

    parser.error(f"неизвестная команда: {args.command}")


if __name__ == "__main__":
    main()
