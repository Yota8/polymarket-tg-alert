import random
import httpx
import time
import asyncio
from py_clob_client.client import ClobClient
from decimal import Decimal
from typing import List, Dict, Any
import ast
import json
import re

# ===================== Telegram 配置 =====================
import telegram_settings
TELEGRAM_TOKEN = telegram_settings.TELEGRAM_TOKEN      # 你的 Token（已填）
TELEGRAM_CHAT_ID = telegram_settings.TELEGRAM_CHAT_ID                                        # 你的 chat_id（已填）

# ===================== 其他配置 =====================
SCAN_INTERVAL_SECONDS = 30
MAX_EVENTS_PER_SCAN = 200
ALERT_THRESHOLD = Decimal('0.0001')
MIN_LIQUIDITY_USD = 5000.0

PER_PAGE_LIMIT = 50
MAX_PAGES = 3
MAX_MARKETS_TOTAL_PER_SCAN = 200

GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"
GAMMA_PARAMS = {
    "active": "true",
    "closed": "false",
    "limit": str(PER_PAGE_LIMIT),
    "order_by": "startDate",
    "order_dir": "desc"
}

clob_client = ClobClient("https://clob.polymarket.com", chain_id=137)


# ===================== Telegram 初始化 =====================
telegram_bot = None
if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
    try:
        from telegram import Bot
        telegram_bot = Bot(token=TELEGRAM_TOKEN)
        print("Telegram Bot 已连接成功")
    except ImportError:
        print("请先安装 python-telegram-bot: pip install python-telegram-bot --upgrade")
    except Exception as e:
        print(f"Telegram 初始化失败: {str(e)}")
else:
    print("Telegram 未配置，将只在控制台输出警报")


async def send_telegram_alert(alert_msg: str):
    if telegram_bot is None:
        print("Telegram 未配置，跳过发送")
        return
    try:
        await telegram_bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=alert_msg,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        print("Telegram 警报已发送")
    except Exception as e:
        print(f"Telegram 发送失败: {str(e)}")


def fetch_active_events() -> List[Dict[str, Any]]:
    all_events = []
    random_start = random.randint(0, 1000)
    print(f"本次随机起始偏移: {random_start}")
    for page in range(MAX_PAGES):
        offset = random_start + page * PER_PAGE_LIMIT
        params = GAMMA_PARAMS.copy()
        params["offset"] = str(offset)
        try:
            resp = httpx.get(GAMMA_EVENTS_URL, params=params, timeout=10)
            resp.raise_for_status()
            page_events = resp.json()
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 第 {page+1} 页 (偏移 {offset}) 获取到 {len(page_events)} 个事件")
            all_events.extend(page_events)
        except Exception as e:
            print(f"第 {page+1} 页 获取失败: {str(e)}")
    print(f"总共获取到 {len(all_events)} 个活跃事件（随机偏移 {random_start}）")
    return all_events


def parse_string_list(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if not isinstance(raw, str):
        return []
    raw = raw.strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except:
        pass
    try:
        parsed = ast.literal_eval(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except:
        pass
    cleaned = re.sub(r'[\[\]"\']', '', raw)
    return [x.strip() for x in cleaned.split(',') if x.strip()]


def get_best_ask_price(token_id: str) -> Decimal | None:
    try:
        resp = clob_client.get_price(token_id, side="sell")
        price_raw = resp.get('price')
        if price_raw is None:
            return None
        price_list = parse_string_list(price_raw)
        if price_list:
            try:
                return Decimal(price_list[0])
            except:
                return None
        return None
    except Exception:
        return None


def calculate_spread(yes_token_id: str, no_token_id: str) -> Decimal:
    yes_ask = get_best_ask_price(yes_token_id)
    no_ask = get_best_ask_price(no_token_id)
    if yes_ask is None or no_ask is None:
        return Decimal('0')
    combined = yes_ask + no_ask
    return Decimal('1') - combined


async def monitor_loop():
    print("=" * 80)
    print("Polymarket 套利监控机器人 - Telegram 版 已启动")
    print(f"扫描间隔: {SCAN_INTERVAL_SECONDS}s | 阈值: {ALERT_THRESHOLD * 100:.2f}%")
    print(f"最低流动性: ${MIN_LIQUIDITY_USD:,.2f}")
    print(f"Telegram: {'已启用' if telegram_bot else '未配置'}")
    print("=" * 80)

    while True:
        try:
            events = fetch_active_events()
            if not events:
                time.sleep(SCAN_INTERVAL_SECONDS)
                continue

            alert_found = False
            checked_count = 0
            seen_questions = set()
            market_limit_reached = False

            for event in events[:MAX_EVENTS_PER_SCAN]:
                if market_limit_reached:
                    break

                title = event.get("title", event.get("slug", "无标题"))
                markets = event.get("markets", [])

                for market in markets:
                    if checked_count >= MAX_MARKETS_TOTAL_PER_SCAN:
                        market_limit_reached = True
                        break

                    question = market.get("question", "无问题")
                    market_id = market.get("id", "未知ID")  # 提取 id

                    if question in seen_questions:
                        continue
                    seen_questions.add(question)

                    clob_ids_raw = market.get("clobTokenIds", [])
                    clob_ids = parse_string_list(clob_ids_raw)
                    if len(clob_ids) < 2:
                        continue

                    outcome_prices_raw = market.get("outcomePrices", [])
                    outcome_prices = parse_string_list(outcome_prices_raw)
                    if not outcome_prices or all(float(p or '0') == 0 for p in outcome_prices):
                        continue

                    # 流动性筛选
                    liquidity_num = market.get("liquidityNum", None)
                    if liquidity_num is None:
                        liquidity_str = market.get("liquidity", "0")
                        try:
                            liquidity_num = float(liquidity_str)
                        except:
                            liquidity_num = 0.0

                    if liquidity_num < MIN_LIQUIDITY_USD:
                        continue

                    checked_count += 1
                    spread = calculate_spread(clob_ids[0], clob_ids[1])

                    print(f"市场 ID: {market_id} | 问题: {question} | spread: {spread}")

                    if spread < ALERT_THRESHOLD:
                        alert_found = True
                        alert_msg_console = (
                            "\n" + "!" * 70 + "\n"
                            f"!!! 发现套利机会 !!! Spread: {spread * 100:.4f}%\n"
                            f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"事件: {title}\n"
                            f"市场: {question}\n"
                            f"流动性: ${liquidity_num:,.2f}\n"
                            f"YES: {clob_ids[0][:20]}...\n"
                            f"NO : {clob_ids[1][:20]}...\n"
                            + "!" * 70
                        )

                        alert_msg_tg = (
                            f"**!!! 发现套利机会 !!!**\n"
                            f"Spread: `{spread * 100:.4f}%`\n"
                            f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"事件: {title}\n"
                            f"市场: {question}\n"
                            f"流动性: ${liquidity_num:,.2f}\n"
                            f"YES: `{clob_ids[0][:20]}...`\n"
                            f"NO : `{clob_ids[1][:20]}...`"
                        )

                        print(alert_msg_console)

                        # 发送 Telegram
                        await send_telegram_alert(alert_msg_tg)

                        break

            status = f"本轮检查 {checked_count} 个有效市场"
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {status}，{'有警报' if alert_found else '无机会'}")

            time.sleep(SCAN_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\n停止监控")
            break
        except Exception as e:
            print(f"主循环异常: {str(e)}")
            time.sleep(30)


if __name__ == "__main__":
    print("启动监控机器人...")
    asyncio.run(monitor_loop())