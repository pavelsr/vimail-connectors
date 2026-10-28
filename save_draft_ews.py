#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "cryptography>=43",
#   "exchangelib>=5.4",
#   "requests>=2.32",
# ]
# ///
"""Сохранить черновик через EWS и напечатать ссылку на его просмотр в OWA."""

from __future__ import annotations

import argparse
import sys
from urllib.parse import quote

import list_inbox_ews


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Сохранить черновик через EWS. Без аргументов поля спрашиваются в консоли.",
    )
    parser.add_argument("--to", metavar="EMAIL", help="получатель")
    parser.add_argument("--subject", metavar="TEXT", help="тема письма")
    parser.add_argument("--body", metavar="TEXT", help="текст письма")
    return parser.parse_args(argv)


def require_text(value: str | None, label: str) -> str:
    """Взять непустое значение из аргумента или спросить его в консоли."""
    if value is not None and value.strip():
        return value.strip()
    if not sys.stdin.isatty():
        raise SystemExit(f"Укажите {label} аргументом: стандартный ввод не интерактивный")
    while True:
        entered = input(f"{label}: ").strip()
        if entered:
            return entered
        print("Пустое значение, введите ещё раз.", file=sys.stderr)


def recipient_address(value: str) -> str:
    if "@" not in value or any(char.isspace() for char in value):
        raise SystemExit(f"Некорректный адрес получателя: {value}")
    return value


def draft_view_url(item_id: str) -> str:
    """Ссылка OWA: папка «Черновики» и выбранное письмо.

    Маршрут #path=/mail/$fid открывает папку. Конкретное письмо клиент берёт
    из ItemID при ispopout=0 и открывает его формой ReadMessageItem.
    """
    item = quote(item_id, safe="")
    return (
        f"https://{list_inbox_ews.HOST}/owa/"
        f"#path=/mail/drafts&ItemID={item}&ispopout=0&viewmodel=ReadMessageItem"
    )


def save_draft(login: str, password: str, *, recipient: str, subject: str, body: str) -> str:
    list_inbox_ews.load_libraries()
    list_inbox_ews.configure_tls()
    from exchangelib import Mailbox, Message

    credentials = list_inbox_ews.Credentials(login, password)
    config = list_inbox_ews.Configuration(
        server=list_inbox_ews.HOST,
        credentials=credentials,
        auth_type=list_inbox_ews.NTLM,
        version=list_inbox_ews.Version(list_inbox_ews.Build(15, 1, 2507, 61)),
    )
    account = list_inbox_ews.Account(
        list_inbox_ews.smtp_address(login),
        config=config,
        autodiscover=False,
        access_type=list_inbox_ews.DELEGATE,
        credentials=credentials,
    )
    message = Message(
        account=account,
        folder=account.drafts,
        subject=subject,
        body=body,
        to_recipients=[Mailbox(email_address=recipient)],
    )
    message.save()
    if not message.id:
        raise RuntimeError("сервер не вернул идентификатор черновика")
    return draft_view_url(message.id)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    recipient = recipient_address(require_text(args.to, "Получатель"))
    subject = require_text(args.subject, "Тема")
    body = require_text(args.body, "Текст")
    env = list_inbox_ews.load_env(list_inbox_ews.ENV_PATH)
    try:
        link = save_draft(
            env["LOGIN"],
            env["PASSWORD"],
            recipient=recipient,
            subject=subject,
            body=body,
        )
    except Exception as exc:
        raise SystemExit(f"Не удалось сохранить черновик по EWS: {exc}") from exc
    print(link)


if __name__ == "__main__":
    main()
