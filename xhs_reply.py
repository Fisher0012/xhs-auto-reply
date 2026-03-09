#!/usr/bin/env python3
"""
小红书评论智能自动回复系统
- 每天定时运行，抓取当天新增评论通知
- 自动过滤引流/违规/无意义评论
- 调用 AI API 生成专业匹配的回复
- Telegram 推送每日执行报告

作者：阿信学财经
GitHub：https://github.com/Fisher0012/xhs-auto-reply
"""

import asyncio
import random
import json
import time
import os
import logging
from datetime import datetime
from pathlib import Path
from openai import OpenAI
import httpx

# ──────────────────────────────────────────────────────
# 1. 配置区 — 修改这里
# ──────────────────────────────────────────────────────

CONFIG = {
    # AI API（默认 DeepSeek，兼容 OpenAI 接口）
    "api_key": os.getenv("API_KEY", "your_deepseek_api_key_here"),
    "api_base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",

    # Telegram
    "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", "your_bot_token_here"),
    "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", "your_chat_id_here"),

    # 小红书
    "xhs_notification_url": "https://www.xiaohongshu.com/notification?type=comment",

    # 行为控制（影响账号安全，谨慎修改）
    "reply_delay_min": 8,
    "reply_delay_max": 25,
    "max_replies_per_run": 10,
    "start_delay_range": 900,

    # 日志
    "log_file": Path(__file__).parent / "logs" / "xhs_reply.log",
}

# ──────────────────────────────────────────────────────
# 2. 账号定位 — 修改为你自己的账号描述
# ──────────────────────────────────────────────────────

ACCOUNT_PROFILE = """
你是「阿信学财经」小红书账号，专注 A股/港股/美股/ETF 投资分析。
擅长宏观经济（美联储/央行政策、利率周期）、AI产业链、新能源、人形机器人供应链等主题。
账号风格：专业但不晦涩，适合普通投资者，分享财经认知提升。
"""

# ──────────────────────────────────────────────────────
# 3. 笔记上下文映射 — 逐步完善，提升回复质量
# ──────────────────────────────────────────────────────

KNOWN_NOTES = {
    # 格式: "封面图hash前16位": "笔记主题详细描述"
    "1040g34o31tcair6o": "六大新兴支柱+六大未来产业，战略新兴产业投资机会",
    "1040g0k031kfdoqep": "每天学点经济学系列，经济学基础知识科普",
    "1040g3k031ppe2tlv": "黄金白银投资逻辑分析，贵金属配置价值",
    "1040g3k831telpj4i": "AI产业链相关分析笔记",
    "1040g3k031pblqbbu": "投资理财综合类笔记",
}

# ──────────────────────────────────────────────────────
# 4. 垃圾评论过滤关键词
# ──────────────────────────────────────────────────────

SPAM_KEYWORDS = [
    "带", "交流群", "私信", "加我", "找我", "联系我", "合作", "推广",
    "引流", "涨粉", "互换", "换粉", "互关", "可带", "信则来",
    "情趣", "单身", "交友", "相亲",
    "交易所", "usdt", "USDT", "合约", "搬砖",
    "111", "666", "哈哈哈哈哈", "啊啊啊啊",
    "代理", "兼职", "日入", "月入", "躺赚",
]


# ──────────────────────────────────────────────────────
# 以下为核心逻辑
# ──────────────────────────────────────────────────────

CONFIG["log_file"].parent.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(CONFIG["log_file"], encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

REPLIED_FILE = Path(__file__).parent / "replied_ids.json"


def load_replied():
    if REPLIED_FILE.exists():
        return set(json.loads(REPLIED_FILE.read_text(encoding="utf-8")))
    return set()


def save_replied(ids):
    REPLIED_FILE.write_text(json.dumps(list(ids), ensure_ascii=False, indent=2), encoding="utf-8")


def is_spam(text):
    if len(text.strip()) <= 3: return True
    if text.strip().isdigit(): return True
    if "该评论已删除" in text: return True
    if text.count("换") >= 1 and len(text) <= 10: return True
    if any(kw in text for kw in SPAM_KEYWORDS): return True
    return False


def infer_note_context(note_hash):
    if note_hash:
        for prefix, context in KNOWN_NOTES.items():
            if note_hash.startswith(prefix[:16]):
                return context
    return "财经投资分析类笔记，涵盖A股、宏观经济、AI产业链、行业分析等主题"


def generate_reply(comment, note_context, client):
    msg = client.chat.completions.create(
        model=CONFIG["model"],
        max_tokens=300,
        messages=[{"role": "user", "content": f"""
{ACCOUNT_PROFILE}

【笔记主题】{note_context}
【用户评论】{comment}

请生成一条回复：
- 友好谦虚谨慎，针对评论给出专业有价值的回应
- 60~120字，自然口语，最多1个emoji
- 不推荐具体买卖操作，不承诺收益
只输出回复正文。
"""}],
    )
    return msg.choices[0].message.content.strip()


async def send_telegram(msg):
    url = f"https://api.telegram.org/bot{CONFIG['telegram_bot_token']}/sendMessage"
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json={"chat_id": int(CONFIG["telegram_chat_id"]), "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        log.warning(f"Telegram失败: {e}")


async def run():
    log.info("=" * 50)
    log.info(f"开始执行 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    replied_ids = load_replied()
    ai_client = OpenAI(api_key=CONFIG["api_key"], base_url=CONFIG["api_base_url"])
    stats = {"replied": 0, "skipped_spam": 0, "skipped_replied": 0, "errors": 0}
    reply_log = []

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(Path.home() / "xhs_chrome_profile"),
            headless=False,
            args=["--no-first-run", "--no-default-browser-check"],
            viewport={"width": 1280, "height": 800},
        )
        page = await browser.new_page()
        await page.goto(CONFIG["xhs_notification_url"], wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(random.randint(2000, 3500))

        await page.evaluate("""
            const tabs = document.querySelectorAll('.reds-tab-item.tab-item');
            const t = Array.from(tabs).find(t => t.textContent.includes('评论和@'));
            if (t) t.click();
        """)
        await page.wait_for_timeout(2000)

        items_data = await page.evaluate("""
            () => {
                const container = document.querySelector('.tabs-content-container');
                if (!container) return [];
                return Array.from(container.children).map((item, idx) => {
                    const text = item.innerText ? item.innerText.trim() : '';
                    const noteImg = item.querySelector('img[src*="notes"], img[src*="spectrum"]');
                    return { idx, text, noteImgHash: noteImg ? noteImg.src.split('/').slice(-1)[0].split('?')[0] : null };
                }).filter(i => i.text.length > 5);
            }
        """)

        log.info(f"共抓取 {len(items_data)} 条通知")

        reply_queue = []
        for item in items_data:
            item_id = str(hash(item["text"][:100]))
            text = item["text"]
            if item_id in replied_ids:
                stats["skipped_replied"] += 1
                continue
            if "回复了你的评论" in text and "作者" in text:
                continue
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if len(lines) < 3:
                stats["skipped_spam"] += 1
                continue
            username = lines[0]
            comment_body = "\n".join(lines[2:]).replace("回复", "").strip()
            if is_spam(comment_body):
                log.info(f"[过滤] {username}: {comment_body[:40]}")
                stats["skipped_spam"] += 1
                replied_ids.add(item_id)
                continue
            reply_queue.append({"idx": item["idx"], "id": item_id, "username": username, "comment": comment_body, "note_hash": item["noteImgHash"]})
            if len(reply_queue) >= CONFIG["max_replies_per_run"]:
                break

        log.info(f"待回复: {len(reply_queue)} 条")

        for entry in reply_queue:
            try:
                note_context = infer_note_context(entry["note_hash"])
                reply_text = generate_reply(entry["comment"], note_context, ai_client)
                log.info(f"回复 @{entry['username']}: {reply_text[:60]}")

                clicked = await page.evaluate(f"""
                    () => {{
                        const container = document.querySelector('.tabs-content-container');
                        const item = container.children[{entry['idx']}];
                        if (!item) return false;
                        const btn = Array.from(item.querySelectorAll('*')).find(e => e.textContent && e.textContent.trim() === '回复' && e.children.length === 0);
                        if (btn) {{ btn.click(); return true; }}
                        return false;
                    }}
                """)
                if not clicked:
                    stats["errors"] += 1
                    continue

                await page.wait_for_timeout(random.randint(1200, 2000))

                filled = await page.evaluate("""
                    (replyText) => {
                        const ta = document.querySelector('textarea.comment-input');
                        if (!ta) return false;
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                        setter.call(ta, replyText);
                        ta.dispatchEvent(new Event('input', { bubbles: true }));
                        return true;
                    }
                """, reply_text)
                if not filled:
                    stats["errors"] += 1
                    continue

                await page.wait_for_timeout(random.randint(800, 1500))

                sent = await page.evaluate("""
                    () => {
                        const btn = Array.from(document.querySelectorAll('*')).find(e => e.textContent && e.textContent.trim() === '发送' && e.children.length === 0 && e.offsetParent !== null);
                        if (btn) { btn.click(); return true; }
                        return false;
                    }
                """)

                if sent:
                    stats["replied"] += 1
                    replied_ids.add(entry["id"])
                    reply_log.append(f"✅ @{entry['username']}: {reply_text[:50]}...")
                else:
                    stats["errors"] += 1

                delay = random.randint(CONFIG["reply_delay_min"], CONFIG["reply_delay_max"])
                await page.wait_for_timeout(delay * 1000)

            except Exception as e:
                log.error(f"处理 {entry.get('username', '?')} 出错: {e}")
                stats["errors"] += 1

        await browser.close()

    save_replied(replied_ids)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    report_lines = [
        "📱 <b>小红书评论自动回复</b>",
        f"🕘 {now}",
        f"✅ 成功回复：{stats['replied']} 条",
        f"🚫 过滤垃圾：{stats['skipped_spam']} 条",
        f"⏭ 已处理过：{stats['skipped_replied']} 条",
        f"❌ 错误：{stats['errors']} 条",
    ]
    if reply_log:
        report_lines.append("\n<b>回复详情：</b>")
        report_lines.extend(reply_log[:5])

    report = "\n".join(report_lines)
    log.info(report)
    await send_telegram(report)
    log.info("执行完成")


if __name__ == "__main__":
    delay = random.randint(0, CONFIG["start_delay_range"])
    log.info(f"随机延迟 {delay // 60} 分 {delay % 60} 秒后启动...")
    time.sleep(delay)
    asyncio.run(run())
