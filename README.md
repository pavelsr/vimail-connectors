# Почта mail.vimos.ru

Короткие скрипты для ящика на `mail.vimos.ru`: чтение «Входящих», отправка письма и сохранение черновика. Учётные данные берутся из `.env` в корне (`LOGIN`, `PASSWORD`). Этот файл не попадает в git.

Запуск через [uv](https://docs.astral.sh/uv/): зависимости указаны в каждом скрипте, отдельно ставить пакеты не нужно.

```bash
uv run list_inbox.py --last 10
uv run list_inbox_ews.py --last 10
uv run send_mail_ews.py --to user@example.com --subject "Тема" --body "Текст"
uv run save_draft_ews.py --to user@example.com --subject "Тема" --body "Текст"
```

## Скрипты

### `list_inbox.py`

Показывает отправителя и тему писем из «Входящих» по IMAP (`mail.vimos.ru:143`, STARTTLS). Папка открывается только на чтение, флаг «прочитано» не ставится.

Нужен один из фильтров: `--last N` (последние N писем) или `--day YYYY-MM-DD` (письма за этот день).

### `list_inbox_ews.py`

То же самое, что `list_inbox.py`, но через Exchange Web Services: `https://mail.vimos.ru/ews/exchange.asmx`. Аргументы `--last` и `--day` те же. День считается в часовом поясе Europe/Moscow.

### `send_mail_ews.py`

Отправляет письмо через EWS. Параметры `--to`, `--subject`, `--body`. Без аргументов скрипт спрашивает эти поля в консоли.

### `save_draft_ews.py`

Сохраняет письмо в «Черновики» через EWS и не отправляет его. Параметры те же, что у `send_mail_ews.py`. В STDOUT печатается одна ссылка на просмотр черновика в OWA, вида `https://mail.vimos.ru/owa/#path=/mail/drafts&ItemID=...`.
