#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Показать темы и отправителей писем из «Входящих» по IMAP."""

from __future__ import annotations

import argparse
import imaplib
import re
import sys
from datetime import date, datetime, timedelta
from email import policy
from email.parser import BytesParser
from pathlib import Path

HOST = "mail.vimos.ru"
PORT = 143
ENV_PATH = Path(__file__).resolve().parent / ".env"
# Пробел или перенос между соседними encoded-words не является частью текста.
_ENCODED_WORD_GAP = re.compile(
    rb"(=\?[^?\s]+?\?[BbQq]\?[^?\s]*\?=)(?:\r\n)?[ \t]+(=\?)"
)

IMAP_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def load_env(path: Path) -> dict[str, str]:
    """Прочитать пары KEY=VALUE из .env."""
    if not path.is_file():
        raise SystemExit(f"Нет файла с учётными данными: {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    missing = [key for key in ("LOGIN", "PASSWORD") if not values.get(key)]
    if missing:
        raise SystemExit(f"В {path} не заданы: {', '.join(missing)}")
    return values


def imap_date(day: date) -> str:
    """Дата в формате IMAP SEARCH (месяц всегда по-английски)."""
    return f"{day.day:02d}-{IMAP_MONTHS[day.month - 1]}-{day.year}"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Темы и отправители писем из «Входящих» (IMAP).",
    )
    parser.add_argument(
        "--last",
        "-n",
        type=int,
        metavar="N",
        help="показать N последних писем",
    )
    parser.add_argument(
        "--day",
        metavar="YYYY-MM-DD",
        help="показать письма только за этот день",
    )
    args = parser.parse_args(argv)
    if args.last is None and args.day is None:
        parser.error("укажите --last N или --day YYYY-MM-DD")
    if args.last is not None and args.last < 1:
        parser.error("--last должен быть не меньше 1")
    if args.day is not None:
        try:
            args.day = datetime.strptime(args.day, "%Y-%m-%d").date()
        except ValueError:
            parser.error("--day ожидается в формате YYYY-MM-DD")
    return args


def search_ids(imap: imaplib.IMAP4, *, day: date | None) -> list[bytes]:
    """Номера писем от старых к новым."""
    if day is None:
        criteria = "ALL"
    else:
        next_day = day + timedelta(days=1)
        criteria = f'(SINCE {imap_date(day)} BEFORE {imap_date(next_day)})'
    status, data = imap.search(None, criteria)
    if status != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def join_encoded_words(raw: bytes) -> bytes:
    """Склеить соседние RFC 2047 encoded-words до разбора заголовка."""
    previous: bytes | None = None
    while previous != raw:
        previous = raw
        raw = _ENCODED_WORD_GAP.sub(rb"\1\2", raw)
    return raw


def header_text(raw: bytes | None) -> tuple[str, str]:
    message = BytesParser(policy=policy.default).parsebytes(join_encoded_words(raw or b""))
    sender = str(message.get("from") or "").replace("\n", " ").strip() or "(без отправителя)"
    subject = str(message.get("subject") or "").replace("\n", " ").strip() or "(без темы)"
    return sender, subject


def fetch_headers(imap: imaplib.IMAP4, message_ids: list[bytes]) -> list[tuple[str, str]]:
    """Темы и отправители, сначала более новые письма. Не ставит флаг \\Seen."""
    rows: list[tuple[str, str]] = []
    for message_id in reversed(message_ids):
        status, fetched = imap.fetch(message_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
        if status != "OK" or not fetched:
            raise SystemExit(f"Не удалось прочитать заголовки письма {message_id.decode()}")
        raw = next((item[1] for item in fetched if isinstance(item, tuple)), None)
        if not isinstance(raw, bytes):
            raise SystemExit(f"Пустой ответ сервера для письма {message_id.decode()}")
        rows.append(header_text(raw))
    return rows


def list_inbox(login: str, password: str, *, last: int | None, day: date | None) -> list[tuple[str, str]]:
    with imaplib.IMAP4(HOST, PORT, timeout=30) as imap:
        imap.starttls()
        imap.login(login, password)
        status, _ = imap.select("INBOX", readonly=True)
        if status != "OK":
            raise SystemExit("Не удалось открыть папку «Входящие»")
        message_ids = search_ids(imap, day=day)
        if last is not None:
            message_ids = message_ids[-last:]
        return fetch_headers(imap, message_ids)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    env = load_env(ENV_PATH)
    rows = list_inbox(env["LOGIN"], env["PASSWORD"], last=args.last, day=args.day)
    if not rows:
        print("Писем не найдено")
        return
    for sender, subject in rows:
        print(f"{sender} — {subject}")


if __name__ == "__main__":
    main()
