#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "cryptography>=43",
#   "exchangelib>=5.4",
#   "requests>=2.32",
# ]
# ///
"""Показать темы и отправителей писем из «Входящих» по EWS."""

from __future__ import annotations

import argparse
import socket
import ssl
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HOST = "mail.vimos.ru"
EWS_URL = f"https://{HOST}/ews/exchange.asmx"
ENV_PATH = Path(__file__).resolve().parent / ".env"
# Внутренние даты писем на этом сервере в MSK. Фильтр дня считается в той же зоне.
MAILBOX_TZ = ZoneInfo("Europe/Moscow")


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


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Темы и отправители писем из «Входящих» (EWS).",
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


def smtp_address(login: str) -> str:
    """Адрес ящика: логин с @ как есть, иначе alias из ДОМЕН\\alias на vimos.ru."""
    if "@" in login:
        return login
    alias = login.split("\\")[-1]
    return f"{alias}@vimos.ru"


def load_libraries() -> None:
    """Импорт EWS-библиотек после разбора аргументов, чтобы --help не требовал их."""
    global requests, urllib3, x509, Encoding, AuthorityInformationAccessOID, ExtensionOID
    global Account, Build, Configuration, Credentials, DELEGATE, EWSDateTime, EWSTimeZone, NTLM, Version
    global BaseProtocol, NoVerifyHTTPAdapter
    import requests as requests_mod
    import urllib3 as urllib3_mod
    from cryptography import x509 as x509_mod
    from cryptography.hazmat.primitives.serialization import Encoding as Encoding_mod
    from cryptography.x509.oid import AuthorityInformationAccessOID as AiaOid
    from cryptography.x509.oid import ExtensionOID as ExtensionOid
    from exchangelib import Account as AccountCls
    from exchangelib import Build as BuildCls
    from exchangelib import Configuration as ConfigurationCls
    from exchangelib import Credentials as CredentialsCls
    from exchangelib import DELEGATE as DelegateAccess
    from exchangelib import EWSDateTime as EwsDateTimeCls
    from exchangelib import EWSTimeZone as EwsTimeZoneCls
    from exchangelib import NTLM as NtlmAuth
    from exchangelib import Version as VersionCls
    from exchangelib.protocol import BaseProtocol as BaseProtocolCls
    from exchangelib.protocol import NoVerifyHTTPAdapter as NoVerifyAdapter

    requests = requests_mod
    urllib3 = urllib3_mod
    x509 = x509_mod
    Encoding = Encoding_mod
    AuthorityInformationAccessOID = AiaOid
    ExtensionOID = ExtensionOid
    Account = AccountCls
    Build = BuildCls
    Configuration = ConfigurationCls
    Credentials = CredentialsCls
    DELEGATE = DelegateAccess
    EWSDateTime = EwsDateTimeCls
    EWSTimeZone = EwsTimeZoneCls
    NTLM = NtlmAuth
    Version = VersionCls
    BaseProtocol = BaseProtocolCls
    NoVerifyHTTPAdapter = NoVerifyAdapter


def leaf_certificate() -> x509.Certificate:
    """Сертификат сервера. На 443 в цепочке нет промежуточного."""
    context = ssl._create_unverified_context()
    with socket.create_connection((HOST, 443), timeout=20) as raw:
        with context.wrap_socket(raw, server_hostname=HOST) as tls:
            der = tls.getpeercert(binary_form=True)
    if not der:
        raise ValueError("сервер не прислал сертификат")
    return x509.load_der_x509_certificate(der)


def intermediate_pem(leaf: x509.Certificate) -> str:
    """Скачать промежуточный сертификат по ссылке из AIA."""
    aia = leaf.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS)
    urls = [
        description.access_location.value
        for description in aia.value
        if description.access_method == AuthorityInformationAccessOID.CA_ISSUERS
        and isinstance(description.access_location.value, str)
        and description.access_location.value.lower().startswith(("http://", "https://"))
    ]
    if not urls:
        raise ValueError("в сертификате нет ссылки на промежуточный")
    response = requests.get(urls[0], timeout=20)
    response.raise_for_status()
    data = response.content
    try:
        certificate = x509.load_der_x509_certificate(data)
    except ValueError:
        certificate = x509.load_pem_x509_certificate(data)
    return certificate.public_bytes(Encoding.PEM).decode()


def verifying_context() -> ssl.SSLContext:
    """Системные корневые плюс недостающий промежуточный сертификат."""
    context = ssl.create_default_context()
    context.load_verify_locations(cadata=intermediate_pem(leaf_certificate()))
    return context


def adapter_for(context: ssl.SSLContext) -> type[requests.adapters.HTTPAdapter]:
    class VerifiedAdapter(requests.adapters.HTTPAdapter):
        def init_poolmanager(self, connections: int, maxsize: int, block: bool = False, **kwargs: object) -> None:
            kwargs["ssl_context"] = context
            super().init_poolmanager(connections, maxsize, block, **kwargs)

    return VerifiedAdapter


def tls_handshake_ok(context: ssl.SSLContext) -> None:
    session = requests.Session()
    session.mount("https://", adapter_for(context)())
    session.get(EWS_URL, timeout=20)


def configure_tls() -> None:
    """Проверять TLS с достроенной цепочкой. Иначе отключить проверку."""
    try:
        context = verifying_context()
        tls_handshake_ok(context)
    except Exception as exc:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter
        print(
            f"Не удалось добавить промежуточный сертификат ({exc}). Проверка TLS отключена.",
            file=sys.stderr,
        )
        return
    BaseProtocol.HTTP_ADAPTER_CLS = adapter_for(context)


def format_sender(sender: object) -> str:
    if sender is None:
        return "(без отправителя)"
    name = str(getattr(sender, "name", "") or "").replace("\n", " ").strip()
    email = str(getattr(sender, "email_address", "") or "").replace("\n", " ").strip()
    if name and email:
        return f"{name} <{email}>"
    return name or email or "(без отправителя)"


def format_subject(subject: str | None) -> str:
    return (subject or "").replace("\n", " ").strip() or "(без темы)"


def list_inbox(login: str, password: str, *, last: int | None, day: date | None) -> list[tuple[str, str]]:
    load_libraries()
    configure_tls()
    credentials = Credentials(login, password)
    config = Configuration(
        server=HOST,
        credentials=credentials,
        auth_type=NTLM,
        version=Version(Build(15, 1, 2507, 61)),
    )
    account = Account(
        smtp_address(login),
        config=config,
        autodiscover=False,
        access_type=DELEGATE,
        credentials=credentials,
    )
    if day is None:
        query = account.inbox.all()
    else:
        tz = EWSTimeZone.from_timezone(MAILBOX_TZ)
        start = EWSDateTime(day.year, day.month, day.day, tzinfo=tz)
        end = start + timedelta(days=1)
        query = account.inbox.filter(datetime_received__gte=start, datetime_received__lt=end)
    query = query.order_by("-datetime_received").only("sender", "subject")
    if last is not None:
        query = query[:last]
    return [(format_sender(item.sender), format_subject(item.subject)) for item in query]


def main(argv: list[str] | None = None) -> None:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    env = load_env(ENV_PATH)
    try:
        rows = list_inbox(env["LOGIN"], env["PASSWORD"], last=args.last, day=args.day)
    except Exception as exc:
        raise SystemExit(f"Не удалось прочитать почту по EWS: {exc}") from exc
    if not rows:
        print("Писем не найдено")
        return
    for sender, subject in rows:
        print(f"{sender} — {subject}")


if __name__ == "__main__":
    main()
