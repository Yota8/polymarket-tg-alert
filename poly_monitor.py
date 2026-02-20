import httpx
import time
import asyncio
from py_clob_client.client import ClobClient
from decimal import Decimal
from typing import List, Dict, Any
import ast
import json
import re

# ===================== 配置 =====================
SCAN_INTERVAL_SECONDS = 30
MAX_EVENTS_PER_SCAN = 200
ALERT_THRESHOLD = Decimal('0.0001')

# 分页设置
PER_PAGE_LIMIT = 50
MAX_PAGES = 3  # 总事件数 = MAX_PAGES × PER_PAGE_LIMIT
MAX_MARKETS_TOTAL_PER_SCAN = 200  # 每轮最多检查的市场数

# Gamma API 配置 - 改用时间排序
GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"
GAMMA_PARAMS = {
    "active": "true",
    "closed": "false",
    "limit": str(PER_PAGE_LIMIT),
    "order_by": "startDate",  # 改成按开始时间排序（最新开的市场排前面）
    "order_dir": "desc"  # desc = 最新开始的先（最近新开的优先）
}

clob_client = ClobClient("https://clob.polymarket.com", chain_id=137)


def fetch_active_events() -> List[Dict[str, Any]]:
    all_events = []
    for page in range(MAX_PAGES):
        offset = page * PER_PAGE_LIMIT
        params = GAMMA_PARAMS.copy()
        params["offset"] = str(offset)

        # 可选：加随机偏移，让每次翻页位置不同（更“新鲜”）
        # random_offset = random.randint(0, 50)
        # params["offset"] = str(offset + random_offset)

        for attempt in range(3):
            try:
                resp = httpx.get(GAMMA_EVENTS_URL, params=params, timeout=10)
                resp.raise_for_status()
                page_events = resp.json()
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 第 {page + 1} 页 获取到 {len(page_events)} 个事件")
                all_events.extend(page_events)
                break
            except Exception as e:
                print(f"第 {page + 1} 页 获取失败: {str(e)}")
                time.sleep(3)

    print(f"总共获取到 {len(all_events)} 个活跃事件（按开始时间最新排序）")
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
    print("Polymarket 套利监控机器人 - 时间排序版 已启动")
    print(f"扫描间隔: {SCAN_INTERVAL_SECONDS}s | 阈值: {ALERT_THRESHOLD * 100:.2f}%")
    print(f"每轮翻页: {MAX_PAGES} 页（总 {MAX_PAGES * PER_PAGE_LIMIT} 个事件）")
    print("按开始时间最新排序 - 每次都能看到最近新开的市场")
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

                    if question in seen_questions:
                        continue
                    seen_questions.add(question)

                    clob_ids_raw = market.get("clobTokenIds", [])
                    clob_ids = parse_string_list(clob_ids_raw)
                    if len(clob_ids) < 2:
                        continue

                    outcome_prices_raw = market.get("outcomePrices", [])
                    outcome_prices = parse_string_list(outcome_prices_raw)
                    # 恢复过滤（可注释调试）
                    if not outcome_prices or all(float(p or '0') == 0 for p in outcome_prices):
                        continue

                    checked_count += 1
                    spread = calculate_spread(clob_ids[0], clob_ids[1])

                    if spread > ALERT_THRESHOLD:
                        alert_found = True
                        print("\n" + "!" * 70)
                        print(f"!!! 发现套利机会 !!! Spread: {spread * 100:.4f}%")
                        print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"事件: {title}")
                        print(f"市场: {question}")
                        print(f"YES: {clob_ids[0][:20]}...")
                        print(f"NO : {clob_ids[1][:20]}...")
                        print("!" * 70)
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