from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from typing import Any, Dict, List, Optional

import requests
import websocket


CDP_HTTP = "http://127.0.0.1:9222"
GOOFISH_HOST = "goofish.com"
AUTO_MARKERS = [
    "本店无人值守",
    "无人值守",
    "回复1",
    "回复2",
    "回复3",
    "自动回复",
    "价格以页面显示为准",
    "直接下单即可",
    "不满意支持仅退款",
    "不满意可退款",
    "有事留言",
    "客服已读不回",
    "24小时自动",
    "选择与卖家协商一致秒退",
]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"¥\s+(\d+)\s+\.\s+(\d+)", r"¥\1.\2", text)
    return text


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def get_targets() -> List[Dict[str, Any]]:
    response = requests.get(f"{CDP_HTTP}/json/list", timeout=5)
    response.raise_for_status()
    return response.json()


def is_goofish_page(target: Dict[str, Any]) -> bool:
    return target.get("type") == "page" and GOOFISH_HOST in target.get("url", "")


def page_kind(url: str) -> str:
    if "/search" in url:
        return "search"
    if "/item?" in url:
        return "item"
    if "/im?" in url:
        return "chat"
    return "unknown"


class Tab:
    def __init__(self, target: Dict[str, Any]) -> None:
        self.target = target
        self.ws = websocket.create_connection(
            target["webSocketDebuggerUrl"],
            timeout=8,
            suppress_origin=True,
        )
        self._next_id = 1

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass

    def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        message_id = self._next_id
        self._next_id += 1
        self.ws.send(
            json.dumps(
                {
                    "id": message_id,
                    "method": method,
                    "params": params or {},
                }
            )
        )
        while True:
            payload = json.loads(self.ws.recv())
            if payload.get("id") == message_id:
                return payload

    def eval(self, expression: str) -> Any:
        payload = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
            },
        )
        details = payload.get("result", {}).get("exceptionDetails")
        if details:
            raise RuntimeError(details.get("text", "Runtime.evaluate failed"))
        return payload.get("result", {}).get("result", {}).get("value")

    def navigate(self, url: str, wait_seconds: float = 2.0) -> None:
        self.call("Page.enable")
        self.call("Page.navigate", {"url": url})
        time.sleep(wait_seconds)


def with_tab(target: Dict[str, Any]) -> Tab:
    return Tab(target)


def detect_focus(target: Dict[str, Any]) -> bool:
    tab = with_tab(target)
    try:
        return bool(tab.eval("document.hasFocus()"))
    finally:
        tab.close()


def activate(target_id: str) -> None:
    requests.get(f"{CDP_HTTP}/json/activate/{target_id}", timeout=5)


def resolve_target(page_ref: str) -> Dict[str, Any]:
    targets = [target for target in get_targets() if is_goofish_page(target)]
    if not targets:
        raise RuntimeError("No Goofish top-level page targets found")

    for target in targets:
        target["page_kind"] = page_kind(target.get("url", ""))

    focused: List[Dict[str, Any]] = []
    for target in targets:
        try:
            if detect_focus(target):
                focused.append(target)
        except Exception:
            continue

    if page_ref == "current":
        return focused[0] if focused else targets[0]

    if page_ref in {"search", "item", "chat"}:
        candidates = [target for target in targets if target["page_kind"] == page_ref]
        if not candidates:
            raise RuntimeError(f"No Goofish page of kind '{page_ref}' found")
        for target in focused:
            if target["page_kind"] == page_ref:
                return target
        return candidates[0]

    for target in targets:
        if page_ref == target["id"]:
            return target

    for target in targets:
        if page_ref in target.get("title", "") or page_ref in target.get("url", ""):
            return target

    raise RuntimeError(f"Could not resolve Goofish page selector: {page_ref}")


def js_helpers() -> str:
    auto_markers = json.dumps(AUTO_MARKERS, ensure_ascii=False)
    return f"""
const clean = (text) => (text || '')
  .replace(/\\u00a0/g, ' ')
  .replace(/\\u200b/g, '')
  .replace(/\\s+/g, ' ')
  .replace(/¥\\s+(\\d+)\\s+\\.\\s+(\\d+)/g, '¥$1.$2')
  .trim();
const linesOf = (text) => (text || '').split(/\\n+/).map((part) => clean(part)).filter(Boolean);
const unreadRe = /^(?:\\d+|99\\+)$/;
const autoMarkers = {auto_markers};
function parseConversation(el) {{
  const rawLines = linesOf(el.innerText || '');
  let index = 0;
  let unreadCount = null;
  if (rawLines[index] && unreadRe.test(rawLines[index])) {{
    unreadCount = rawLines[index];
    index += 1;
  }}
  const name = rawLines[index] || '';
  const rest = rawLines.slice(index + 1);
  const timeText = rest.length ? rest[rest.length - 1] : '';
  const snippet = rest.length > 1 ? clean(rest.slice(0, -1).join(' ')) : (rest[0] || '');
  return {{
    name,
    unread_count: unreadCount,
    snippet,
    time_text: timeText,
    active: (el.className || '').includes('active'),
    class_name: el.className || '',
    raw_lines: rawLines,
  }};
}}
function classifyReply(text) {{
  const normalized = clean(text);
  if (!normalized) return 'unknown';
  if (autoMarkers.some((marker) => normalized.includes(marker))) return 'likely_auto';
  if (normalized.length <= 120) return 'likely_human';
  return 'unknown';
}}
function parseMessage(el) {{
  const rawLines = linesOf(el.innerText || '');
  const rect = el.getBoundingClientRect();
  const side = rect.x > (window.innerWidth * 0.6) ? 'outgoing' : 'incoming';
  const sender = rawLines[0] || '';
  let contentLines = rawLines.slice(1);
  let status = null;
  if (side === 'outgoing' && contentLines.length) {{
    const last = contentLines[contentLines.length - 1];
    if (['未读', '已读', '发送中', '失败'].includes(last)) {{
      status = last;
      contentLines = contentLines.slice(0, -1);
    }}
  }}
  return {{
    side,
    sender,
    status,
    text: clean(contentLines.join(' ')),
    raw_lines: rawLines,
    class_name: el.className || '',
    x: rect.x,
    y: rect.y,
    w: rect.width,
    h: rect.height,
  }};
}}
function currentContact() {{
  const topbar = document.querySelector('[class*="message-topbar"]');
  if (!topbar) return '';
  const lines = linesOf(topbar.innerText || '');
  return lines[0] || '';
}}
"""


def read_search(tab: Tab, limit: int) -> Dict[str, Any]:
    expression = f"""
(() => {{
  {js_helpers()}
  const input = document.querySelector('input');
  const seen = new Set();
  const cards = [];
  for (const anchor of [...document.querySelectorAll('a[href*="/item?id="]')]) {{
    if (!anchor.offsetParent) continue;
    const href = anchor.href || '';
    const text = clean(anchor.innerText || '');
    if (!href || !text || seen.has(href)) continue;
    seen.add(href);
    const url = new URL(href);
    cards.push({{
      index: cards.length,
      href,
      item_id: url.searchParams.get('id') || '',
      text,
      class_name: anchor.className || '',
    }});
  }}
  return {{
    page_type: 'search',
    title: document.title,
    url: location.href,
    query: input ? (input.value || '') : '',
    results: cards.slice(0, {limit}),
  }};
}})()
"""
    result = tab.eval(expression)
    if result.get("page_type") != "search":
        result["warning"] = "Target page did not look like a Goofish search page"
    return result


def read_item(tab: Tab, related_limit: int) -> Dict[str, Any]:
    expression = f"""
(() => {{
  {js_helpers()}
  const currentUrl = new URL(location.href);
  const currentId = currentUrl.searchParams.get('id') || '';
  const input = document.querySelector('input');
  const chat = [...document.querySelectorAll('a,button')].find((el) => clean(el.innerText || '') === '聊一聊' || ((el.href || '').includes('/im?')));
  const buy = [...document.querySelectorAll('a,button')].find((el) => clean(el.innerText || '') === '立即购买' || ((el.href || '').includes('/create-order?')));
  const sellerAnchor = [...document.querySelectorAll('a[href*="/personal?userId="]')].find((anchor) => {{
    const text = clean(anchor.innerText || '');
    return text && !text.includes('闲鱼号');
  }});
  const seen = new Set();
  const related = [];
  for (const anchor of [...document.querySelectorAll('a[href*="/item?id="]')]) {{
    if (!anchor.offsetParent) continue;
    const href = anchor.href || '';
    const text = clean(anchor.innerText || '');
    if (!href || !text || seen.has(href) || href.includes(`id=${{currentId}}`)) continue;
    seen.add(href);
    related.push({{
      href,
      text,
      class_name: anchor.className || '',
    }});
  }}
  return {{
    page_type: 'item',
    title: document.title,
    url: location.href,
    item_id: currentId,
    top_search_value: input ? (input.value || '') : '',
    chat: chat ? {{
      text: clean(chat.innerText || ''),
      href: chat.href || '',
      class_name: chat.className || '',
    }} : null,
    buy: buy ? {{
      text: clean(buy.innerText || ''),
      href: buy.href || '',
      class_name: buy.className || '',
    }} : null,
    seller: sellerAnchor ? {{
      text: clean(sellerAnchor.innerText || ''),
      href: sellerAnchor.href || '',
    }} : null,
    related: related.slice(0, {related_limit}),
  }};
}})()
"""
    result = tab.eval(expression)
    if result.get("page_type") != "item":
        result["warning"] = "Target page did not look like a Goofish item page"
    return result


def read_chat(tab: Tab, conversation_limit: int, message_limit: int) -> Dict[str, Any]:
    expression = f"""
(() => {{
  {js_helpers()}
  const textarea = document.querySelector('textarea');
  const topbar = document.querySelector('[class*="message-topbar"]');
  const itemLink = [...document.querySelectorAll('a[href*="/item?id="]')].find((anchor) => anchor.offsetParent && anchor.getBoundingClientRect().y < 240);
  const seenConversations = new Set();
  const conversations = [];
  for (const el of [...document.querySelectorAll('[class*="conversation-item"]')]) {{
    const conversation = parseConversation(el);
    const key = [conversation.name, conversation.snippet, conversation.time_text, conversation.unread_count || ''].join('||');
    if (!conversation.name || seenConversations.has(key)) continue;
    seenConversations.add(key);
    conversations.push(conversation);
  }}
  const visibleMessages = [...document.querySelectorAll('[class*="message-row"]')]
    .map((el) => parseMessage(el))
    .filter((message) => message.w > 120 && message.h > 20 && message.y > 80 && message.y < window.innerHeight)
    .slice(-{message_limit});
  const latestIncoming = visibleMessages.filter((message) => message.side === 'incoming').slice(-1)[0] || null;
  const holder = document.querySelector('.rc-virtual-list-holder') || document.querySelector('[class*="virtual-list-holder"]');
  return {{
    page_type: 'chat',
    title: document.title,
    url: location.href,
    current_contact: currentContact(),
    topbar_text: topbar ? clean(topbar.innerText || '') : '',
    current_item: itemLink ? {{
      href: itemLink.href || '',
      text: clean(itemLink.innerText || ''),
    }} : null,
    draft_text: textarea ? (textarea.value || '') : '',
    textarea_placeholder: textarea ? (textarea.placeholder || '') : '',
    conversations: conversations.slice(0, {conversation_limit}),
    unread_conversations: conversations.filter((conversation) => conversation.unread_count).slice(0, {conversation_limit}),
    visible_messages: visibleMessages,
    latest_incoming_reply_type: latestIncoming ? classifyReply(latestIncoming.text) : 'unknown',
    latest_incoming_text: latestIncoming ? latestIncoming.text : '',
    body_tail: clean((document.body.innerText || '').slice(-2000)),
    sidebar_scroll: holder ? {{
      scroll_top: holder.scrollTop,
      client_height: holder.clientHeight,
      scroll_height: holder.scrollHeight,
    }} : null,
  }};
}})()
"""
    result = tab.eval(expression)
    if result.get("page_type") != "chat":
        result["warning"] = "Target page did not look like a Goofish chat page"
    return result


def list_pages() -> Dict[str, Any]:
    pages: List[Dict[str, Any]] = []
    for target in get_targets():
        if not is_goofish_page(target):
            continue
        page_info = {
            "id": target["id"],
            "title": target.get("title", ""),
            "url": target.get("url", ""),
            "page_kind": page_kind(target.get("url", "")),
            "focused": False,
        }
        try:
            page_info["focused"] = detect_focus(target)
        except Exception as exc:
            page_info["focus_error"] = str(exc)
        pages.append(page_info)
    return {"pages": pages}


def search_items(target: Dict[str, Any], query: str, limit: int) -> Dict[str, Any]:
    activate(target["id"])
    tab = with_tab(target)
    try:
        url = "https://www.goofish.com/search?q=" + urllib.parse.quote(query)
        tab.navigate(url)
        return read_search(tab, limit)
    finally:
        tab.close()


def open_item(target: Dict[str, Any], index: int, limit: int) -> Dict[str, Any]:
    activate(target["id"])
    tab = with_tab(target)
    try:
        summary = read_search(tab, max(limit, index + 1))
        results = summary.get("results", [])
        if index < 0 or index >= len(results):
            raise RuntimeError(f"Search result index {index} is out of range")
        tab.navigate(results[index]["href"])
        return read_item(tab, limit)
    finally:
        tab.close()


def open_chat(target: Dict[str, Any], item_limit: int, conversation_limit: int, message_limit: int) -> Dict[str, Any]:
    activate(target["id"])
    tab = with_tab(target)
    try:
        summary = read_item(tab, item_limit)
        chat = summary.get("chat") or {}
        href = chat.get("href")
        if not href:
            raise RuntimeError("Could not find a chat href on the current item page")
        tab.navigate(href)
        return read_chat(tab, conversation_limit, message_limit)
    finally:
        tab.close()


def click_visible_conversation(tab: Tab, name: str, exact: bool) -> Dict[str, Any]:
    expression = f"""
(() => {{
  {js_helpers()}
  const targetName = {json.dumps(name, ensure_ascii=False)};
  const exact = {json.dumps(exact)};
  const items = [...document.querySelectorAll('[class*="conversation-item"]')];
  const target = items.find((el) => {{
    const conversation = parseConversation(el);
    if (exact) return conversation.name === targetName;
    return conversation.name.includes(targetName) || clean(el.innerText || '').includes(targetName);
  }});
  if (!target) {{
    return {{
      ok: false,
      visible_names: items.map((el) => parseConversation(el).name).filter(Boolean),
    }};
  }}
  target.click();
  return {{
    ok: true,
    clicked: parseConversation(target),
  }};
}})()
"""
    return tab.eval(expression)


def scroll_sidebar(tab: Tab) -> Dict[str, Any]:
    expression = f"""
(() => {{
  {js_helpers()}
  const holder = document.querySelector('.rc-virtual-list-holder') || document.querySelector('[class*="virtual-list-holder"]');
  if (!holder) {{
    return {{ ok: false, reason: 'sidebar scroll holder not found' }};
  }}
  const before = holder.scrollTop;
  holder.scrollTop = holder.scrollTop + Math.max(120, holder.clientHeight * 0.8);
  holder.dispatchEvent(new Event('scroll', {{ bubbles: true }}));
  return {{
    ok: true,
    before,
    after: holder.scrollTop,
    client_height: holder.clientHeight,
    scroll_height: holder.scrollHeight,
  }};
}})()
"""
    return tab.eval(expression)


def reset_sidebar_to_top(tab: Tab) -> Dict[str, Any]:
    expression = f"""
(() => {{
  {js_helpers()}
  const holder = document.querySelector('.rc-virtual-list-holder') || document.querySelector('[class*="virtual-list-holder"]');
  if (!holder) {{
    return {{ ok: false, reason: 'sidebar scroll holder not found' }};
  }}
  const before = holder.scrollTop;
  holder.scrollTop = 0;
  holder.dispatchEvent(new Event('scroll', {{ bubbles: true }}));
  return {{
    ok: true,
    before,
    after: holder.scrollTop,
    client_height: holder.clientHeight,
    scroll_height: holder.scrollHeight,
  }};
}})()
"""
    return tab.eval(expression)


def switch_conversation(
    target: Dict[str, Any],
    name: str,
    exact: bool,
    max_scrolls: int,
    conversation_limit: int,
    message_limit: int,
) -> Dict[str, Any]:
    activate(target["id"])
    tab = with_tab(target)
    try:
        reset_sidebar_to_top(tab)
        time.sleep(0.3)
        for attempt in range(max_scrolls + 1):
            click_result = click_visible_conversation(tab, name, exact)
            if click_result.get("ok"):
                for _ in range(10):
                    time.sleep(0.3)
                    chat = read_chat(tab, conversation_limit, message_limit)
                    current = chat.get("current_contact", "")
                    if current == name or (not exact and name in current):
                        chat["switch_result"] = click_result
                        chat["switch_attempts"] = attempt
                        return chat
                raise RuntimeError(
                    f"Clicked conversation '{name}' but current contact did not switch to it"
                )
            scroll_result = scroll_sidebar(tab)
            if not scroll_result.get("ok"):
                break
            if scroll_result.get("after") == scroll_result.get("before"):
                break
            time.sleep(0.5)
        raise RuntimeError(f"Could not find conversation '{name}' in the chat sidebar")
    finally:
        tab.close()


def check_send(target: Dict[str, Any], expected_contact: str, message: str) -> Dict[str, Any]:
    activate(target["id"])
    tab = with_tab(target)
    try:
        chat = read_chat(tab, 12, 12)
    finally:
        tab.close()

    normalized_message = clean_text(message)
    current_contact = chat.get("current_contact", "")
    visible_outgoing = [
        entry for entry in chat.get("visible_messages", []) if entry.get("side") == "outgoing"
    ]
    latest_outgoing = visible_outgoing[-1] if visible_outgoing else None
    message_seen = normalized_message in clean_text(chat.get("body_tail", ""))
    if not message_seen and latest_outgoing:
        message_seen = normalized_message in clean_text(latest_outgoing.get("text", ""))

    latest_status = latest_outgoing.get("status") if latest_outgoing else None
    contact_matches = current_contact == expected_contact
    textarea_empty = not chat.get("draft_text")
    send_likely_success = (
        contact_matches
        and textarea_empty
        and message_seen
        and latest_status != "失败"
    )

    return {
        "current_contact": current_contact,
        "expected_contact": expected_contact,
        "contact_matches": contact_matches,
        "textarea_empty": textarea_empty,
        "message_seen": message_seen,
        "latest_outgoing_status": latest_status,
        "send_likely_success": send_likely_success,
        "latest_outgoing": latest_outgoing,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and operate Goofish web pages via CDP")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-pages", help="List Goofish tabs")

    read_search_parser = subparsers.add_parser("read-search", help="Read current search results")
    read_search_parser.add_argument("--page", default="search")
    read_search_parser.add_argument("--limit", type=int, default=8)

    search_parser = subparsers.add_parser("search", help="Navigate a tab to search results")
    search_parser.add_argument("--page", default="search")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--limit", type=int, default=8)

    open_item_parser = subparsers.add_parser("open-item", help="Open a visible item from search results")
    open_item_parser.add_argument("--page", default="search")
    open_item_parser.add_argument("--index", type=int, required=True)
    open_item_parser.add_argument("--limit", type=int, default=8)

    read_item_parser = subparsers.add_parser("read-item", help="Read current item page")
    read_item_parser.add_argument("--page", default="item")
    read_item_parser.add_argument("--limit", type=int, default=6)

    open_chat_parser = subparsers.add_parser("open-chat", help="Open chat from current item page")
    open_chat_parser.add_argument("--page", default="item")
    open_chat_parser.add_argument("--item-limit", type=int, default=6)
    open_chat_parser.add_argument("--conversation-limit", type=int, default=10)
    open_chat_parser.add_argument("--message-limit", type=int, default=10)

    read_chat_parser = subparsers.add_parser("read-chat", help="Read current chat state")
    read_chat_parser.add_argument("--page", default="chat")
    read_chat_parser.add_argument("--conversation-limit", type=int, default=10)
    read_chat_parser.add_argument("--message-limit", type=int, default=10)

    switch_parser = subparsers.add_parser("switch-conversation", help="Switch chat contact safely")
    switch_parser.add_argument("--page", default="chat")
    switch_parser.add_argument("--name", required=True)
    switch_parser.add_argument("--exact", action="store_true")
    switch_parser.add_argument("--max-scrolls", type=int, default=8)
    switch_parser.add_argument("--conversation-limit", type=int, default=10)
    switch_parser.add_argument("--message-limit", type=int, default=10)

    check_send_parser = subparsers.add_parser("check-send", help="Verify that a known message appears sent")
    check_send_parser.add_argument("--page", default="chat")
    check_send_parser.add_argument("--expect-contact", required=True)
    check_send_parser.add_argument("--message", required=True)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "list-pages":
            print_json(list_pages())
            return 0

        if args.command == "read-search":
            target = resolve_target(args.page)
            tab = with_tab(target)
            try:
                print_json(read_search(tab, args.limit))
            finally:
                tab.close()
            return 0

        if args.command == "search":
            target = resolve_target(args.page)
            print_json(search_items(target, args.query, args.limit))
            return 0

        if args.command == "open-item":
            target = resolve_target(args.page)
            print_json(open_item(target, args.index, args.limit))
            return 0

        if args.command == "read-item":
            target = resolve_target(args.page)
            tab = with_tab(target)
            try:
                print_json(read_item(tab, args.limit))
            finally:
                tab.close()
            return 0

        if args.command == "open-chat":
            target = resolve_target(args.page)
            print_json(
                open_chat(
                    target,
                    args.item_limit,
                    args.conversation_limit,
                    args.message_limit,
                )
            )
            return 0

        if args.command == "read-chat":
            target = resolve_target(args.page)
            tab = with_tab(target)
            try:
                print_json(read_chat(tab, args.conversation_limit, args.message_limit))
            finally:
                tab.close()
            return 0

        if args.command == "switch-conversation":
            target = resolve_target(args.page)
            print_json(
                switch_conversation(
                    target,
                    args.name,
                    args.exact,
                    args.max_scrolls,
                    args.conversation_limit,
                    args.message_limit,
                )
            )
            return 0

        if args.command == "check-send":
            target = resolve_target(args.page)
            print_json(check_send(target, args.expect_contact, args.message))
            return 0

        parser.error(f"Unknown command: {args.command}")
        return 2
    except Exception as exc:
        print_json({"error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
