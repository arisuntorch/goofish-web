---
name: goofish-web
description: Safely operate the Goofish/Xianyu/闲鱼 web app from an already-open logged-in browser session. Use when Codex needs to search listings, read search results, inspect item pages, enter seller chats, identify the current contact, switch among multiple conversations, verify unread markers, judge likely auto-replies vs human replies, or avoid cross-chat mistakes on Goofish web.
---

# Goofish Web

Use this skill against an already logged-in Goofish browser session with Chrome DevTools exposed on `http://127.0.0.1:9222`.

The bundled script is the default interface:

```powershell
python C:\Users\arisu\.codex\skills\goofish-web\scripts\goofish_web.py <command> ...
```

Read [references/page-model.md](./references/page-model.md) when you need the DOM model, send-verification rules, auto-reply heuristics, or failure modes.

## Workflow

1. Discover the active Goofish tabs.

```powershell
python C:\Users\arisu\.codex\skills\goofish-web\scripts\goofish_web.py list-pages
```

2. If you need product discovery, drive a disposable search or item tab, not the active chat tab.

```powershell
python C:\Users\arisu\.codex\skills\goofish-web\scripts\goofish_web.py search --page search --query "openclaw部署"
python C:\Users\arisu\.codex\skills\goofish-web\scripts\goofish_web.py open-item --page search --index 0
python C:\Users\arisu\.codex\skills\goofish-web\scripts\goofish_web.py read-item --page item
python C:\Users\arisu\.codex\skills\goofish-web\scripts\goofish_web.py open-chat --page item
```

3. Before any chat action, inspect chat state and confirm the current contact from the right-side top bar.

```powershell
python C:\Users\arisu\.codex\skills\goofish-web\scripts\goofish_web.py read-chat --page chat
```

4. When switching sellers, use the conversation switcher and verify the contact after the switch.

```powershell
python C:\Users\arisu\.codex\skills\goofish-web\scripts\goofish_web.py switch-conversation --page chat --name "低调的华丽"
```

5. When checking whether a message was really sent, do not trust only the URL or the send button state. Verify all of:
   - `current_contact` still matches the expected seller
   - the textarea draft is empty
   - the sent text appears in the latest chat tail or outgoing bubble
   - the latest outgoing status is not `失败`

```powershell
python C:\Users\arisu\.codex\skills\goofish-web\scripts\goofish_web.py check-send --page chat --expect-contact "低调的华丽" --message "你好，想了解下远程部署和售后。"
```

## Safety Rules

- Treat `read-chat.current_contact` as the source of truth. After switching conversations, the browser URL may remain on the original `peerUserId`.
- Prefer semantic anchors and text over hashed CSS suffixes. Stable patterns are URL fragments like `/search`, `/item?id=`, `/im?`, `/personal?userId=`, `/create-order?itemId=`.
- Treat the left conversation list as virtualized. Only visible rows are guaranteed to exist in the DOM. Scroll deliberately when a seller is not immediately visible.
- Before opening a new item or search results, decide which tab is disposable. Do not accidentally repurpose the only chat tab you still need.
- If reply classification is `unknown`, say so. Auto-reply vs human is heuristic, not exact.

## Commands

### Read-only

- `list-pages`: List Goofish tabs with page kind and focus state.
- `read-search`: Parse the current visible search results.
- `read-item`: Parse the current item page, seller block, and chat link.
- `read-chat`: Parse the current chat contact, visible conversations, unread counts, visible messages, and likely reply type.
- `check-send`: Verify whether a known message already appears as a likely-sent outgoing message.

### Mutating navigation

- `search`: Navigate the target tab to a search results page.
- `open-item`: Navigate the target search tab to one of the visible item cards.
- `open-chat`: Navigate the current item tab to its `聊一聊` chat URL.
- `switch-conversation`: Click a visible or scrolled-into-view seller in the left conversation list and verify the resulting contact.

## When the Script Is Not Enough

Use direct CDP only as a fallback. If you do, keep the same invariants:

- connect with `suppress_origin=True`
- classify the page from URL and title first
- on chat pages, verify the right-side top bar before any send
- after a switch or send, re-read the page instead of assuming the click worked
