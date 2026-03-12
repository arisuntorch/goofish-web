# goofish-web

`goofish-web` is a Codex skill plus a small CDP helper script for operating the Goofish/Xianyu web app from an already-open logged-in browser session.

It is built for tasks such as:

- reading search results
- opening item pages
- entering seller chats
- identifying the current contact
- switching between sellers safely
- checking unread badges
- estimating auto-reply vs human reply
- reducing cross-chat mistakes before sending messages

## What Is Included

- `SKILL.md`: the skill instructions used by Codex
- `references/page-model.md`: the DOM model, heuristics, and failure notes
- `scripts/goofish_web.py`: the executable helper script

## Requirements

- a logged-in Goofish browser session
- Chrome DevTools HTTP exposed at `http://127.0.0.1:9222`
- Python 3.12+
- Python packages:
  - `requests`
  - `websocket-client`

## Quick Start

List current Goofish tabs:

```powershell
python scripts/goofish_web.py list-pages
```

Read visible search results:

```powershell
python scripts/goofish_web.py search --page search --query "openclaw deployment"
python scripts/goofish_web.py read-search --page search --limit 5
```

Open an item and inspect it:

```powershell
python scripts/goofish_web.py open-item --page search --index 0
python scripts/goofish_web.py read-item --page item
```

Enter chat and inspect the current conversation:

```powershell
python scripts/goofish_web.py open-chat --page item
python scripts/goofish_web.py read-chat --page chat
```

Switch to a seller safely:

```powershell
python scripts/goofish_web.py switch-conversation --page chat --name "seller-name" --exact
```

Check whether a message appears to have been sent:

```powershell
python scripts/goofish_web.py check-send --page chat --expect-contact "seller-name" --message "hello"
```

## Safety Model

The script is intentionally conservative.

- It treats the right-side chat top bar as the source of truth for the current contact.
- It does not trust the chat URL alone after conversation switches.
- It uses multiple signals to judge whether a message was sent.
- It treats auto-reply classification as heuristic, not exact.
- It assumes the left conversation list is virtualized and only visible rows are safe to act on directly.

## Why This Exists

Goofish web pages are workable through CDP, but the UI has enough quirks that ad hoc automation is easy to get wrong:

- conversation switches can succeed without changing the URL
- unread state is easier to read from row text than from CSS color alone
- long seller templates can look like real replies if you only read body text
- direct clicks on inner text nodes are less reliable than acting on the row container

This repository packages those lessons into a reusable Codex skill.
