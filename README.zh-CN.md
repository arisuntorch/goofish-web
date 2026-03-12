# goofish-web

[English](./README.md)

`goofish-web` 是一个 Codex skill，加上一份小型 CDP 辅助脚本，用来在“已经打开并登录”的闲鱼网页会话上执行稳定操作。

它主要用于以下任务：

- 读取搜索结果
- 打开商品页
- 进入卖家聊天页
- 识别当前联系人
- 在多个卖家之间安全切换
- 检查未读气泡
- 粗略判断自动回复和真人回复
- 在发消息前降低串台和误判风险

## 仓库内容

- `SKILL.md`：供 Codex 调用时使用的 skill 说明
- `references/page-model.md`：页面结构、启发式规则和风险记录
- `scripts/goofish_web.py`：可直接执行的辅助脚本

## 运行前提

- 浏览器里已经登录闲鱼
- Chrome DevTools HTTP 已暴露在 `http://127.0.0.1:9222`
- Python 3.12+
- Python 依赖：
  - `requests`
  - `websocket-client`

## 快速开始

列出当前闲鱼标签页：

```powershell
python scripts/goofish_web.py list-pages
```

读取搜索结果：

```powershell
python scripts/goofish_web.py search --page search --query "openclaw deployment"
python scripts/goofish_web.py read-search --page search --limit 5
```

打开商品并读取商品页：

```powershell
python scripts/goofish_web.py open-item --page search --index 0
python scripts/goofish_web.py read-item --page item
```

进入聊天并读取当前会话：

```powershell
python scripts/goofish_web.py open-chat --page item
python scripts/goofish_web.py read-chat --page chat
```

安全切换到指定卖家：

```powershell
python scripts/goofish_web.py switch-conversation --page chat --name "seller-name" --exact
```

检查某条消息是否看起来已经发出：

```powershell
python scripts/goofish_web.py check-send --page chat --expect-contact "seller-name" --message "hello"
```

## 安全模型

这个脚本的策略偏保守。

- 它把右侧聊天顶栏当作当前联系人的真相源。
- 它不会只根据聊天 URL 判断当前会话。
- 它会组合多个信号来判断消息是否真的发出。
- 它把自动回复识别视为启发式判断，而不是精确判断。
- 它默认左侧会话列表是虚拟滚动的，只直接操作当前可见的会话行。

## 为什么要做这个仓库

闲鱼网页端通过 CDP 可以操作，但页面细节足够多，临时写的自动化很容易出错：

- 切换会话后 URL 可能不变
- 未读状态用文本行判断比只看 CSS 颜色更稳
- 卖家的长模板回复很容易被误判成真人回复
- 直接点文字节点不如点整行会话容器稳定

这个仓库就是把这些踩坑经验整理成一个可复用的 Codex skill。
