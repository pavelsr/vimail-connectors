# AGENTS.md

## Project Overview

CLI-скрипты для корпоративного ящика `mail.vimos.ru` (Exchange 15.1, сборка 15.1.2507.61). Четыре самостоятельных файла в корне, без пакета и без тестов. Общие настройки EWS живут в `list_inbox_ews.py`; `send_mail_ews.py` и `save_draft_ews.py` импортируют его.

Учётные данные: файл `.env` рядом со скриптами, ключи `LOGIN` и `PASSWORD`. Логин вида `ДОМЕН\alias` или полный SMTP-адрес. `.env` указан в `.gitignore` и не коммитится.

## Скрипты

### `list_inbox.py`

Чтение «Входящих» по IMAP. Хост `mail.vimos.ru`, порт 143, `STARTTLS`, папка `INBOX` в режиме `readonly`. Заголовки `From` и `Subject` забираются через `BODY.PEEK`, поэтому письмо не помечается прочитанным. Соседние RFC 2047 encoded-words склеиваются до разбора. Фильтр обязателен: `--last N` или `--day YYYY-MM-DD`.

### `list_inbox_ews.py`

Чтение «Входящих» по EWS. Точка входа `https://mail.vimos.ru/ews/exchange.asmx`, аутентификация NTLM, autodiscover выключен, `access_type=DELEGATE`. Версия сервера задана явно: `Version(Build(15, 1, 2507, 61))`. На порту 443 в цепочке нет промежуточного сертификата: скрипт достраивает её по AIA и проверяет TLS; если это не удалось, проверка сертификата отключается. Фильтр дня строится в `Europe/Moscow`. Те же аргументы, что у `list_inbox.py`.

Отсюда же остальные EWS-скрипты берут `HOST`, `load_env`, `smtp_address`, `load_libraries`, `configure_tls` и классы exchangelib.

### `send_mail_ews.py`

Отправка письма: `Message.send()` через EWS. Аргументы `--to`, `--subject`, `--body`. Пустые значения в интерактивном режиме запрашиваются заново. Адрес получателя должен содержать `@` и не содержать пробелов.

### `save_draft_ews.py`

Черновик: `Message` с `folder=account.drafts` и `message.save()` (`CreateItem` / `SaveOnly`), без отправки. После сохранения в STDOUT печатается только ссылка OWA:

`https://mail.vimos.ru/owa/#path=/mail/drafts&ItemID=<urlencoded EWS id>&ispopout=0&viewmodel=ReadMessageItem`

`ItemID` — это `message.id`, закодированный через `urllib.parse.quote`. В OWA 15.1 маршрут `#path=/mail/drafts` открывает папку, а `ItemID` при `ispopout=0` выбирает письмо и открывает его формой `ReadMessageItem`.

## Стек Python-модулей

Скрипты рассчитаны на Python `>=3.12` и запуск через `uv run`. Сторонние пакеты объявлены в блоке PEP 723 в начале файла.

| Модуль | Где | Зачем |
| --- | --- | --- |
| `exchangelib` `>=5.4` | `list_inbox_ews.py`, `send_mail_ews.py`, `save_draft_ews.py` | Клиент EWS: `Account`, `Configuration`, `Credentials`, `NTLM`, `Version`, `Build`, `DELEGATE`, `Message`, `Mailbox` |
| `requests` `>=2.32` | `list_inbox_ews.py` | Скачать промежуточный сертификат по AIA и проверить TLS-рукопожатие с `EWS_URL` |
| `cryptography` `>=43` | `list_inbox_ews.py` | Разобрать сертификат сервера и промежуточный сертификат (`x509`) |
| `imaplib` | `list_inbox.py` | IMAP-сессия, `STARTTLS`, `SEARCH`, `FETCH` |
| `email` (`policy`, `BytesParser`) | `list_inbox.py` | Разбор заголовков `From` и `Subject` |
| `urllib.parse.quote` | `save_draft_ews.py` | Кодирование EWS ItemId в ссылке OWA |

`list_inbox.py` сторонних пакетов не требует: в его блоке PEP 723 `dependencies` пустой. Три EWS-скрипта зависят от `cryptography`, `exchangelib` и `requests`.

Из стандартной библиотеки также используются `argparse`, `ssl`, `socket`, `pathlib`, `datetime`, `zoneinfo`, `re` и `sys`. Импорт exchangelib отложен в `load_libraries()`, чтобы `--help` не требовал установленных пакетов.

## Setup Commands

```bash
uv run list_inbox.py --help
uv run list_inbox_ews.py --last 5
uv run send_mail_ews.py --to user@example.com --subject "Тема" --body "Текст"
uv run save_draft_ews.py --to user@example.com --subject "Тема" --body "Текст"
```

`.env` в корне:

```
LOGIN=ДОМЕН\alias
PASSWORD=...
```

Не подставляйте пароль в аргументы командной строки и не коммитьте `.env`.

## Development Workflow

Новый EWS-вызов подключайте через `list_inbox_ews.load_libraries()` и `list_inbox_ews.configure_tls()`, затем собирайте `Configuration` так же, как в `send_mail_ews.py`: NTLM, фиксированная версия 15.1.2507.61, `autodiscover=False`. Адрес ящика — `list_inbox_ews.smtp_address(login)`.

Новый самостоятельный `.py` начинается с блока PEP 723. Сторонние зависимости перечисляйте там; для запуска достаточно `uv run`.

## Testing Instructions

Автоматических тестов нет. Проверка — запуск против живого ящика:

- `list_inbox.py` и `list_inbox_ews.py` печатают строки `отправитель — тема`.
- `send_mail_ews.py` печатает `Отправлено: ...`.
- `save_draft_ews.py` печатает одну ссылку OWA. Её нужно открыть в браузере, уже вошедшем в `https://mail.vimos.ru/owa/`.

## Code Style

- Python 3.12, аннотации типов, `from __future__ import annotations`.
- Сообщения пользователю и тексты ошибок — на русском.
- Ошибки протокола завершают процесс через `SystemExit` с понятной фразой, без трассировки наружу.
- Секреты только из `.env`.
