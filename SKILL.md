# SKILL.md — 社交平台评论自动回复通用技能

本文件描述了将此自动回复系统迁移到其他社交平台的通用方法。

---

## 核心架构（平台无关）

```
定时任务（launchd / cron）
  └── Python 脚本
        ├── Playwright → 控制本地浏览器
        │     ├── 打开通知/评论页面
        │     ├── 抓取新增评论列表
        │     └── 逐条填入回复并发送
        ├── 垃圾评论过滤器（关键词 + 规则）
        ├── AI API → 生成专业回复（DeepSeek / OpenAI 兼容）
        ├── 已处理记录（JSON 本地去重）
        └── 通知推送（Telegram Bot）
```

---

## 迁移到其他平台

### 需要替换的部分

| 变量 | 小红书 | 微博 | 抖音 |
|------|--------|------|------|
| 通知页 URL | `xiaohongshu.com/notification?type=comment` | `weibo.com/u/xxx/notification` | `douyin.com/notification` |
| 评论 Tab 选择器 | `.reds-tab-item` 含"评论和@" | 对应 Tab 文字 | 对应 Tab 文字 |
| 评论列表容器 | `.tabs-content-container` | 对应容器 class | 对应容器 class |
| 回复按钮文字 | "回复" | "回复" | "回复" |
| 输入框选择器 | `textarea.comment-input` | 对应 textarea | 对应 textarea |
| 发送按钮文字 | "发送" | "发布" | "发布" |

### 迁移步骤

1. **找到通知页 URL** — 手动打开平台的评论通知页，复制 URL
2. **定位 CSS 选择器** — 用 DevTools 找评论容器、回复按钮、输入框
3. **更新 `xhs_reply.py` 中的 `page.evaluate` 代码块** — 替换选择器
4. **调整账号定位 `ACCOUNT_PROFILE`** — 根据新平台账号风格修改
5. **重新运行 `login_once.py`** — 用新平台 URL 登录保存 Cookie
6. **更新 plist 中的脚本路径** — 指向新的脚本文件

---

## 关键设计原则

### 安全性
- 使用本地真实 Chrome Profile，不使用无头浏览器
- 随机启动延迟（0~15分钟）避免固定时间被识别
- 每条回复间隔 8~25 秒模拟真人节奏
- 每次最多回复 10 条（可配置）

### 去重机制
- 本地 `replied_ids.json` 记录已处理的评论 hash
- 基于评论内容前100字符生成 ID，防止重复回复

### AI 回复质量
- `ACCOUNT_PROFILE` 定义账号人设和风格
- `KNOWN_NOTES` 映射笔记主题，提升回复相关性
- 限制 60~120 字，最多1个 emoji，不做投资建议

---

## 环境变量

| 变量名 | 说明 |
|--------|------|
| `API_KEY` | DeepSeek / OpenAI 兼容 API Key |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID（数字） |

通过 plist 的 `EnvironmentVariables` 注入，不硬编码在代码中。

---

## 常用调试命令

```bash
# 查看实时日志
tail -f ~/xhs_auto_reply/logs/xhs_reply.log

# 手动触发执行（跳过随机延迟）
python3 -c "import asyncio, xhs_reply; asyncio.run(xhs_reply.run())"

# 检查定时任务状态
launchctl list | grep xhs

# 重载定时任务配置
launchctl unload ~/Library/LaunchAgents/com.xhs.autoreply.plist
launchctl load ~/Library/LaunchAgents/com.xhs.autoreply.plist

# Cookie 失效时重新登录
python3 login_once.py
```
