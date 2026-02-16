# gamma_active_events.py
# 使用 Gamma Events API 获取 Polymarket 当前活跃事件
# 每个事件下包含 market 的 question、clobTokenIds、outcomePrices 等
# 支持过滤活跃、未关闭事件，按交易量或时间排序

import httpx
import time
import json
from typing import List, Dict, Any

# ===================== 配置参数（可自行修改） =====================
MAX_EVENTS_TO_SHOW = 5           # 最多显示多少个事件
MIN_VOLUME_USD = 5000             # 最小事件交易量过滤（美元，如果有）
REQUEST_TIMEOUT = 10              # 请求超时秒数
PER_PAGE_LIMIT = 20               # 每页事件数量
PAGES_TO_FETCH = 3                # 分页次数
SORT_BY = "volume"                # 排序字段："volume" 或 "startTime"
SORT_DIR = "desc"                 # "desc"（降序）或 "asc"（升序）

# ===================== 函数：获取一页活跃事件 =====================
def fetch_active_events(page: int = 1) -> List[Dict[str, Any]]:
    url = "https://gamma-api.polymarket.com/events?active=true&closed=false&limit=5"
    # params = {
    #     "limit": str(PER_PAGE_LIMIT),
    #     "offset": str((page - 1) * PER_PAGE_LIMIT),
    #     "order_by": SORT_BY,
    #     "order_dir": SORT_DIR
    # }

    try:
        print(f"正在请求第 {page} 页事件...")
        resp = httpx.get(url,  timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        events = resp.json()  # 直接返回 list of events

        print(f"第 {page} 页：原始 {len(events)} 个事件")

        # 可选过滤：如果事件有 volume 属性（有些事件聚合了子 market 的 volume）
        # filtered = [e for e in events if float(e.get("volume", 0)) >= MIN_VOLUME_USD]
        # 这里先不严格过滤，因为 volume 可能在 market 里
        return events

    except httpx.HTTPStatusError as e:
        print(f"HTTP 错误 {e.response.status_code}: {e.response.text[:200]}...")
        return []
    except Exception as e:
        print(f"请求失败: {str(e)}")
        return []


# ===================== 主函数 =====================
def main():
    print("=" * 100)
    print("Polymarket 活跃事件查询（使用官方 Gamma /events API）")
    print(f"过滤：active=true, closed=false | 排序：{SORT_BY} {SORT_DIR}")
    print(f"显示前 {MAX_EVENTS_TO_SHOW} 个事件")
    print("=" * 100)
    print()

    all_events: List[Dict[str, Any]] = []

    for page in range(1, PAGES_TO_FETCH + 1):
        page_events = fetch_active_events(page)
        all_events.extend(page_events)
        time.sleep(1.5)  # 防限速

        if len(page_events) < PER_PAGE_LIMIT:
            print("本页返回数量少于 limit，结束分页")
            break

    if not all_events:
        print("没有找到活跃事件")
        print("可能原因：网络问题、API 临时不可用、或当前无活跃事件")
        return

    print(f"\n最终找到 {len(all_events)} 个活跃事件")
    print("-" * 100)

    for idx, event in enumerate(all_events[:MAX_EVENTS_TO_SHOW], 1):
        event_id = event.get("id", "未知ID")
        event_title = event.get("title", event.get("slug", "无事件标题"))
        event_slug = event.get("slug", "未知slug")
        active = event.get("active", "未知")
        closed = event.get("closed", "未知")
        event_tags = event.get("tags", "未知标签")

        print(f"{idx:2d}. 事件标题: {event_title}")
        print(f"   事件 ID/Slug: {event_id} / {event_slug}")
        print(f"   状态: active={active} | closed={closed}")
        print(f"   状态: tags={event_tags}")

        # 展开该事件下的 markets（通常 1 个，但可能多个）
        markets = event.get("markets", [])
        if not markets:
            print("   无市场数据")
            print("-" * 100)
            continue

        for m_idx, market in enumerate(markets, 1):
            question = market.get("question", "无问题标题")
            outcome_prices = market.get("outcomePrices", "无价格数据")
            # 这里polymarket可能为了兼容旧版本,clob_ids为字符串形式
            clob_ids = market.get("clobTokenIds", [])
            if isinstance(clob_ids, str):
                import ast
                try:
                    clob_ids = ast.literal_eval(clob_ids)  # 安全解析字符串为列表
                except (ValueError, SyntaxError):
                    clob_ids = []  # 解析失败，返回空列表
            else:
                clob_ids = clob_ids if isinstance(clob_ids, list) else []


            print("clob_ids : ", clob_ids)

            yes_id = clob_ids[0] if len(clob_ids) > 0 else "未知YES"
            no_id  = clob_ids[1] if len(clob_ids) > 1 else "未知NO"

            print(f"   子市场 {m_idx}: {question}")
            print(f"      YES token : {yes_id}")
            print(f"      NO  token : {no_id}")
            print(f"      当前价格参考: {outcome_prices}")

        print("-" * 100)


if __name__ == "__main__":
    main()