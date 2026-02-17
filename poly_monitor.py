# 每隔一段时间扫描活跃市场，计算 spread，发现机会时警报

import httpx
import time
import asyncio
from py_clob_client.client import ClobClient
from decimal import Decimal
from typing import List, Dict, Any

# ===================== 配置（可自行修改） =====================
SCAN_INTERVAL_SECONDS = 30        # 扫描间隔（秒）
ALERT_THRESHOLD = Decimal('0.005')  # spread > 0.5% 才警报
MAX_EVENTS_PER_SCAN = 20          # 每轮最多检查多少个事件（防太多导致超时）
REQUEST_TIMEOUT = 10              # API 请求超时
RETRY_ATTEMPTS = 3                # 失败重试次数
RETRY_DELAY = 5                   # 重试间隔秒

# Gamma API 配置
GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"
GAMMA_PARAMS = {
    "active": "true",
    "closed": "false",
    "limit": "50",                # 每页最多50
    "order_by": "volume",
    "order_dir": "desc"
}

# CLOB 客户端（用于 get_price）
clob_client = ClobClient("https://clob.polymarket.com", chain_id=137)


# ===================== 函数：获取活跃事件列表 =====================
def fetch_active_events() -> List[Dict[str, Any]]:
    events = []
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = httpx.get(GAMMA_EVENTS_URL, params=GAMMA_PARAMS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            events = resp.json()
            print(f"获取到 {len(events)} 个活跃事件")
            return events
        except Exception as e:
            print(f"获取事件失败 (尝试 {attempt+1}/{RETRY_ATTEMPTS}): {str(e)}")
            if attempt < RETRY_ATTEMPTS - 1:
                time.sleep(RETRY_DELAY)
    return []


# ===================== 函数：计算单个市场的 spread =====================
def calculate_spread(yes_token_id: str, no_token_id: str) -> Decimal:
    try:
        # 获取 YES best_ask
        yes_resp = clob_client.get_price(yes_token_id, side="sell")
        yes_ask = Decimal(yes_resp['price']) if 'price' in yes_resp else None

        # 获取 NO best_ask
        no_resp = clob_client.get_price(no_token_id, side="sell")
        no_ask = Decimal(no_resp['price']) if 'price' in no_resp else None

        if yes_ask is None or no_ask is None:
            return Decimal('0')  # 无法计算，返回 0

        combined_ask = yes_ask + no_ask
        spread = Decimal('1') - combined_ask
        return spread

    except Exception as e:
        print(f"计算 spread 失败: {str(e)}")
        return Decimal('0')


# ===================== 主循环 =====================
async def monitor_loop():
    print("=" * 80)
    print("Polymarket 套利监控机器人 已启动")
    print(f"扫描间隔: {SCAN_INTERVAL_SECONDS} 秒 | 警报阈值: {ALERT_THRESHOLD*100:.2f}%")
    print("按 Ctrl+C 停止")
    print("=" * 80)
    print()

    while True:
        try:
            events = fetch_active_events()
            if not events:
                print("暂无活跃事件，继续等待...")
                time.sleep(SCAN_INTERVAL_SECONDS)
                continue

            alert_found = False

            for event in events[:MAX_EVENTS_PER_SCAN]:
                event_title = event.get("title", event.get("slug", "无标题"))
                markets = event.get("markets", [])

                for market in markets:
                    question = market.get("question", "无问题")
                    clob_ids = market.get("clobTokenIds", [])

                    # 处理 clobTokenIds（兼容字符串/列表）
                    if isinstance(clob_ids, str):
                        import ast
                        try:
                            clob_ids = ast.literal_eval(clob_ids)
                        except:
                            clob_ids = []
                    else:
                        clob_ids = clob_ids if isinstance(clob_ids, list) else []

                    if len(clob_ids) < 2:
                        continue  # 跳过无效市场

                    yes_id = clob_ids[0]
                    no_id  = clob_ids[1]

                    spread = calculate_spread(yes_id, no_id)

                    if spread > ALERT_THRESHOLD:
                        alert_found = True
                        print("\n" + "!" * 60)
                        print(f"!!! 发现套利机会 !!! Spread: {spread*100:.4f}%")
                        print(f"事件标题: {event_title}")
                        print(f"市场问题: {question}")
                        print(f"YES token: {yes_id}")
                        print(f"NO  token: {no_id}")
                        print("!" * 60)

            if not alert_found:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 本轮扫描无机会，继续监控...")

            time.sleep(SCAN_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\n用户停止监控，退出")
            break
        except Exception as e:
            print(f"主循环异常: {str(e)}")
            time.sleep(30)  # 异常后等待更长时间再重试


if __name__ == "__main__":
    print("启动监控机器人...")
    asyncio.run(monitor_loop())