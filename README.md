# Почта mail.vimos.ru

Короткие скрипты для ящика на `mail.vimos.ru`: чтение «Входящих», отправка письма, сохранение черновика и черновик ответа. Учётные данные берутся из `.env` в корне (`LOGIN`, `PASSWORD`). Этот файл не попадает в git.

Запуск через [uv](https://docs.astral.sh/uv/): зависимости указаны в каждом скрипте, отдельно ставить пакеты не нужно.

```bash
uv run list_inbox.py --last 10
uv run list_inbox_ews.py --last 10
uv run send_mail_ews.py --to user@example.com --subject "Тема" --body "Текст"
uv run save_draft_ews.py --to user@example.com --subject "Тема" --body "Текст"
uv run reply_draft_ews.py
uv run vimail.py unanswered
uv run vimail.py draft-self
uv run vimail.py draft-reply --text "Текст ответа"
uv run --group dev pytest
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

### `reply_draft_ews.py`

Сохраняет **черновик ответа** на последнее входящее письмо `IPM.Note`, у которого такого черновика ещё нет. Письмо не отправляется. Текст ответа фиксированный. В STDOUT — ссылка OWA на черновик (как у `save_draft_ews.py`).

### `vimail.py`

Единая CLI-утилита:

```bash
uv run vimail.py unanswered
uv run vimail.py unanswered --day 2026-11-10
uv run vimail.py unanswered --until 2026-11-01
uv run vimail.py unanswered --from 2026-11-01 --to 2026-11-05
uv run vimail.py unanswered --days-ago 3
uv run vimail.py --format json unanswered
uv run vimail.py draft-self --text "..."
uv run vimail.py draft-reply --text "..."
```

Неотвеченное — входящее `IPM.Note` без черновика ответа. Если черновик уже был создан, в STDERR будет warning.

Скрипт явно выставляет заголовки треда:

| Поле | Откуда | Зачем |
| --- | --- | --- |
| `In-Reply-To` | `Message-ID` исходного письма | Указывает, на какое именно письмо отвечают (RFC 5322). По нему клиенты и этот скрипт понимают: «черновик ответа на это письмо уже есть». |
| `References` | цепочка `References`/`In-Reply-To` родителя + его `Message-ID` | Полная цепочка идентификаторов ветки (RFC 5322). Нужна почтовым клиентам, чтобы собрать тред, если `In-Reply-To` потерялся или ответ глубже одного шага. |
| `ConversationId` | копирует Exchange при `ReplyToItem` (в EWS поле read-only) | Идентификатор беседы Microsoft Exchange/OWA. Связывает письма в одну переписку на сервере; скрипт только проверяет совпадение с исходным письмом. |

Без этих полей ответ выглядит как новое письмо: не попадает в ту же цепочку в OWA/Outlook и при повторном запуске скрипт не сможет надёжно пропустить уже обработанное входящее.

Если на самое новое письмо черновик ответа уже есть, берётся следующее входящее.

## Навык для ИИ-агента (`vimail-skill`)

В репозитории лежит self-contained skill: `skills/vimail-skill/` (`SKILL.md` + те же CLI-скрипты). Его можно поставить в Cursor, OpenCode, Zed, Goose, Hermes Agent и другие агенты через [skills-cli](https://github.com/vercel-labs/skills).

```bash
# интерактивно: CLI сам предложит агентов
npx skills add pavelsr/vimail-connectors --skill vimail-skill

# сразу в нужные агенты
npx skills add pavelsr/vimail-connectors --skill vimail-skill \
  -a hermes-agent -a goose -a cursor -a opencode -a zed -y
```

Либо попросите агента установить skill из репозитория `https://github.com/pavelsr/vimail-connectors` (команда выше или встроенный установщик skills у агента).

После установки создайте `.env` **внутри каталога навыка** (`LOGIN`, `PASSWORD`) и запускайте скрипты из этой папки через `uv run`.

## Другие полезные skills

- [max-messenger/max-agents-skill](https://github.com/max-messenger/max-agents-skill)
- [affaan-m/ECC](https://github.com/affaan-m/ECC)
- [wshobson/agents](https://github.com/wshobson/agents)
- [sickn33/agentic-awesome-skills](https://github.com/sickn33/agentic-awesome-skills)
