# Goofish Web Page Model

## Preconditions

- The browser is already logged into Goofish/闲鱼.
- Chrome DevTools HTTP is reachable at `http://127.0.0.1:9222`.
- CDP websocket connections must suppress the `Origin` header. Without that, Chrome may reject the connection with HTTP 403.

## Page Types

Classify pages from URL first:

- Search page: `https://www.goofish.com/search?...`
- Item page: `https://www.goofish.com/item?id=...`
- Chat page: `https://www.goofish.com/im?...`

The page title is a useful secondary signal:

- Search: `<query>_闲鱼`
- Item: `<item title>_闲鱼`
- Chat: `聊天_闲鱼`

Ignore the `xdomain-storage` iframe targets returned by CDP. Operate on top-level `type=page` targets.

## Search Page

Reliable read model:

- Query text comes from the visible top search input.
- Result cards are visible anchors whose `href` contains `/item?id=`.
- The card text already contains most of what matters: title, price, location, seller hints, response-speed hints, and release recency.

Preferred extraction pattern:

- Filter to visible anchors with non-empty text.
- Deduplicate by `href`.
- Treat the first visible cards as the ranking order.

Do not rely on:

- exact hashed class suffixes
- the presence of every filter chip in the DOM
- invisible cards outside the current virtualized viewport

## Item Page

Reliable read model:

- `聊一聊` points to `/im?itemId=...&peerUserId=...`
- `立即购买` points to `/create-order?itemId=...`
- seller profile anchors point to `/personal?userId=...`
- the page title is usually the cleanest single-line item title

Good fields to read:

- item title
- item id from URL
- seller block text
- chat href
- buy href
- related visible cards below the fold

Important distinction:

- the visible seller block can contain location, recent activity, age on platform, volume sold, and praise rate
- related cards are not the same thing as the current item; keep them separate

## Chat Page

### Current contact

Use the right-side top bar as the source of truth.

Do not use the page URL as the source of truth after switching conversations. In live testing, the top bar changed to a different seller while the URL still showed the old `peerUserId`.

### Left conversation list

Reliable read model:

- each visible conversation row contains:
  - optional unread count on the first line, such as `1` or `99+`
  - seller/contact name
  - latest snippet
  - relative time
- the active row carries an additional active class
- the list is virtualized, so only visible rows are guaranteed to exist in the DOM

Reliable unread signal:

- the red badge is visible in the UI
- the DOM also exposes the unread number as the first text line in the conversation row
- prefer the textual unread count over trying to read CSS colors

### Right message pane

Useful signals:

- textarea placeholder: `请输入消息，按Enter键发送或点击发送按钮发送`
- outgoing rows are right-aligned
- incoming rows are left-aligned
- outgoing rows may end with a status line such as `未读` or `已读`

Message send verification should combine multiple checks:

1. current contact still matches the intended seller
2. textarea is empty after send
3. the sent text appears in the latest body tail or visible outgoing row
4. the latest outgoing status is not `失败`

Do not trust only one signal:

- URL can be stale
- send button availability can be misleading
- body text alone can be noisy when long histories are loaded

## Auto-Reply vs Human Reply

This is heuristic.

Strong auto-reply indicators:

- boilerplate service notices such as `本店无人值守`
- menu prompts such as `回复1` / `回复2` / `回复3`
- refund or support templates repeated across sellers
- long instructions with numbered steps that do not answer the last question
- generic phrases like `价格以页面显示为准`, `直接下单即可`, `不满意可退款`

Strong human indicators:

- short contextual answers such as `对`, `50装好`, `3天售后`
- direct reference to the exact question
- back-and-forth clarification instead of a fixed template
- reply length is short and seller-specific

Use three buckets:

- `likely_auto`
- `likely_human`
- `unknown`

Return `unknown` when the evidence is mixed.

## Common Failure Modes

### CDP / browser issues

- websocket handshake 403 because `Origin` was not suppressed
- hidden or background tabs that still appear in `json/list`
- top-level page plus helper iframe both present in CDP results

### Frontend quirks

- hashed CSS names change; rely on prefixes, href patterns, and text
- chat conversation list is virtualized
- direct text-node clicks can fail; click the outer conversation item row
- send button lookup can be brittle; verification should not depend on button text alone

### Shell / encoding issues

- Chinese text can be mangled when injected through the wrong shell path
- when building automation, prefer UTF-8 source files and JSON-encoded strings

### Operational safety risks

- reusing the only chat tab for search navigation can lose context
- switching the left conversation without re-reading the top bar can cause cross-chat mistakes
- assuming any long reply is human can misclassify automation templates
