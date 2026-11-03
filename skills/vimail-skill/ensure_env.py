#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Проверить или создать .env с LOGIN/PASSWORD рядом со skill.

Приоритет значений: существующий .env → переменные окружения
(VIMAIL_LOGIN/VIMAIL_PASSWORD или LOGIN/PASSWORD) → интерактивный ввод.
Пароль в TTY читается через getpass (без эха). Значения секретов
в STDOUT/STDERR не печатаются.
"""

from __future__ import annotations

import argparse
import getpass
import os
import stat
import sys
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent / ".env"


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def env_lookup(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def quote_env_value(value: str) -> str:
    """Сериализация под load_env: снимаются только внешние кавычки, без unescape."""
    if "\n" in value or "\r" in value:
        raise SystemExit("значение не должно содержать перевод строки")
    if any(ch in value for ch in ' \t#"\'') or value.startswith("="):
        if '"' not in value:
            return f'"{value}"'
        if "'" not in value:
            return f"'{value}'"
        raise SystemExit("значение содержит и ' и \"; задайте его без одной из кавычек")
    return value


def write_env(path: Path, *, login: str, password: str) -> None:
    if "\n" in login or "\r" in login or "\n" in password or "\r" in password:
        raise SystemExit("LOGIN/PASSWORD не должны содержать перевод строки")
    body = (
        f"LOGIN={quote_env_value(login)}\n"
        f"PASSWORD={quote_env_value(password)}\n"
    )
    path.write_text(body, encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def credentials_ready(values: dict[str, str]) -> bool:
    return bool(values.get("LOGIN") and values.get("PASSWORD"))


def prompt_login(default: str = "") -> str:
    if not sys.stdin.isatty():
        raise SystemExit(
            "Нет TTY для ввода LOGIN. Передайте VIMAIL_LOGIN и VIMAIL_PASSWORD "
            "в окружении процесса или создайте .env через ensure_env.py с TTY."
        )
    hint = f" [{default}]" if default else ""
    while True:
        entered = input(f"LOGIN (DOMAIN\\alias или alias@vimos.ru){hint}: ").strip()
        if not entered:
            entered = default
        if entered:
            return entered
        print("Пустой LOGIN, введите ещё раз.", file=sys.stderr)


def prompt_password() -> str:
    if not sys.stdin.isatty():
        raise SystemExit(
            "Нет TTY для ввода пароля. Задайте VIMAIL_PASSWORD в окружении "
            "процесса (не в argv) и снова запустите ensure_env.py."
        )
    while True:
        entered = getpass.getpass("PASSWORD (ввод скрыт): ")
        if entered:
            return entered
        print("Пустой пароль, введите ещё раз.", file=sys.stderr)


def resolve_credentials(*, interactive: bool) -> tuple[str, str]:
    file_values = parse_env_file(ENV_PATH)
    login = file_values.get("LOGIN", "") or env_lookup("VIMAIL_LOGIN", "LOGIN")
    password = file_values.get("PASSWORD", "") or env_lookup("VIMAIL_PASSWORD", "PASSWORD")
    if login and password:
        return login, password
    if not interactive:
        missing = [name for name, value in (("LOGIN", login), ("PASSWORD", password)) if not value]
        raise SystemExit(
            "Нет учётных данных: "
            + ", ".join(missing)
            + f". Нужен {ENV_PATH.name} или VIMAIL_LOGIN/VIMAIL_PASSWORD в окружении."
        )
    if not login:
        login = prompt_login()
    if not password:
        password = prompt_password()
    return login, password


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Проверить или записать .env с LOGIN/PASSWORD для vimail-skill.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="только проверить наличие LOGIN и PASSWORD; код 0 если ок",
    )
    parser.add_argument(
        "--from-env",
        action="store_true",
        help="записать .env только из окружения/файла, без интерактивного ввода",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.check:
        if credentials_ready(parse_env_file(ENV_PATH)):
            print(f"OK: учётные данные есть в {ENV_PATH}")
            return
        raise SystemExit(f"MISSING: нет полного LOGIN/PASSWORD в {ENV_PATH}")

    login, password = resolve_credentials(interactive=not args.from_env)
    existing = parse_env_file(ENV_PATH)
    if existing.get("LOGIN") == login and existing.get("PASSWORD") == password:
        print(f"OK: {ENV_PATH} уже актуален")
        return
    write_env(ENV_PATH, login=login, password=password)
    print(f"OK: записан {ENV_PATH} (режим 0600)")


if __name__ == "__main__":
    main()
