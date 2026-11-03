---
name: vimail-skill
description: >-
  Configure any @vimos.ru mailbox on mail.vimos.ru and operate it via uv CLI
  scripts (EWS/IMAP): auto .env bootstrap, list inbox, save/send mail, reply
  drafts. Use for Vimos email, Exchange/EWS, OWA drafts, list_inbox_ews,
  reply_draft_ews, send_mail_ews, mailbox login/password setup.
compatibility: >-
  Python >=3.12, uv, network to mail.vimos.ru. Works in Hermes Agent, Goose,
  OpenCode, Cursor, Zed and other Agent Skills harnesses. Bundle is
  self-contained under this skill directory.
metadata:
  author: vimos
  version: "1.2"
required_environment_variables:
  - name: VIMAIL_LOGIN
    prompt: Vimos mailbox LOGIN (DOMAIN\alias or alias@vimos.ru)
    help: Written into this skill's .env as LOGIN (mode 0600).
  - name: VIMAIL_PASSWORD
    prompt: Vimos mailbox PASSWORD
    help: Written into this skill's .env as PASSWORD (mode 0600). Never log the value.
---

# vimail-skill

Self-contained: `SKILL.md` + scripts in **this directory**. Always `cd` here
before `uv run` (imports and `.env` use `__file__` parent).

## Credentials (do this first)

Before any mail command, ensure `.env` in **this directory** has `LOGIN` and
`PASSWORD`.

### 1. Reuse session / last user prompt

If the latest user message or current session already contains mailbox login
and/or password, **do not ask again**. Write them into `.env` without echoing
secrets in the assistant reply:

```bash
VIMAIL_LOGIN='…' VIMAIL_PASSWORD='…' uv run ensure_env.py --from-env
```

Pass secrets only via process environment for that one command — **never** via
CLI argv, never paste them back into chat, never commit `.env`.

### 2. Missing credentials

If `.env` is incomplete and session/prompt has no secrets:

1. Run check: `uv run ensure_env.py --check` (exit `0` = ready).
2. Prefer local masked input (no secret in LLM context):

```bash
uv run ensure_env.py
```

`ensure_env.py` prompts for `LOGIN` and uses `getpass` for `PASSWORD` when a
TTY is available, then writes `.env` with mode `0600`.

3. If there is **no TTY** (many remote/UI harnesses): ask the user once in chat
   for `LOGIN` and `PASSWORD`. Immediately run the `--from-env` command above.
   Then tell the user credentials were saved locally; **do not repeat the
   password** in later messages.
4. If the harness has a native secrets / env prompt (e.g. Hermes
   `required_environment_variables` / secrets tool), use that first, then
   `uv run ensure_env.py --from-env` so scripts still read this skill's `.env`.

`LOGIN` may be `alias@vimos.ru` or `DOMAIN\alias` (SMTP becomes `alias@vimos.ru`
when there is no `@`).

## Layout

| File | Role |
| --- | --- |
| `ensure_env.py` | Create/check `.env` (LOGIN/PASSWORD), mode 0600 |
| `list_inbox_ews.py` | Inbox via EWS; shared helpers |
| `list_inbox.py` | Inbox via IMAP (peek) |
| `send_mail_ews.py` | Send mail |
| `save_draft_ews.py` | New draft + OWA URL |
| `reply_draft_ews.py` | Reply draft to newest unanswered inbox mail |

## Commands

| Goal | Command |
| --- | --- |
| Ensure `.env` | `uv run ensure_env.py` or `--check` / `--from-env` |
| Inbox (EWS) | `uv run list_inbox_ews.py --last N` or `--day YYYY-MM-DD` |
| Inbox (IMAP peek) | `uv run list_inbox.py --last N` |
| Send | `uv run send_mail_ews.py --to user@host --subject "…" --body "…"` |
| New draft | `uv run save_draft_ews.py --to user@host --subject "…" --body "…"` |
| Reply draft | `uv run reply_draft_ews.py` |

Default to EWS. **Do not send** unless the user explicitly asks.

Server: `mail.vimos.ru`, EWS `https://mail.vimos.ru/ews/exchange.asmx`, NTLM,
Exchange `15.1.2507.61`.

## Reply draft

`reply_draft_ews.py`: newest inbox `IPM.Note` without an existing reply draft.

- Skip when draft `In-Reply-To` matches mail `Message-ID` (else `ConversationId`).
- Body: `Здравствуйте! Это ИИ асистент. Письмо получено, помечено как важное, владелец почты уведомлен`
- Sets `In-Reply-To` + `References` (RFC 5322); `ConversationId` is server-set.
- No `send()`.

## Security

- Never print `PASSWORD` / `VIMAIL_PASSWORD` in tool output summaries or replies.
- Prefer `ensure_env.py` TTY/`getpass` or harness secret capture over chat paste.
- `.env` stays in this skill directory, mode `0600`, not committed.

## Extend

New EWS `.py` here: PEP 723 + `list_inbox_ews.load_libraries()` /
`configure_tls()` / same `Configuration` as `send_mail_ews.py`. User-facing
strings in Russian.
