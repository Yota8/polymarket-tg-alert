# 使用 Gamma API 获取 Polymarket 当前活跃且未关闭的市场列表
# 按交易量降序，支持过滤 volume 和 liquidity
# 自动处理 clobTokenIds 的各种可能格式（字符串 / 列表 / 带引号等）

import httpx
import time
import re
from typing import List, Dict, Any

# ===================== 配置参数（可自行修改） =====================
MAX_MARKETS_TO_SHOW = 10          # 最多显示多少个市场
MIN_VOLUME_USD = 5000             # 最小交易量过滤（美元）
MIN_LIQUIDITY_USD = 2000          # 最小流动性过滤（美元）
REQUEST_TIMEOUT = 10              # 每个请求超时秒数
PAGES_TO_FETCH = 2                # 分页次数（每页约 20-50 条）
PER_PAGE_LIMIT = 50               # 每页请求数量
SLEEP_BETWEEN_PAGES = 1.0         # 分页间隔（防限速）

# ===================== 函数：获取一页市场 =====================
def fetch_page(page: int = 1) -> List[Dict[str, Any]]:
    url = "https://gamma-api.polymarket.com/markets"
    params = {
        "active": "true",
        "closed": "false",
        "limit": str(PER_PAGE_LIMIT),
        "offset": str((page - 1) * PER_PAGE_LIMIT),
        "order_by": "volume",
        "order_dir": "desc"
    }

    try:
        print(f"正在请求第 {page} 页...")
        resp = httpx.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        data = resp.json()

        # Gamma API 通常直接返回 list，有时包裹在 {"data": [...]}
        if isinstance(data, list):
            markets = data
        elif isinstance(data, dict) and "data" in data:
            markets = data["data"]
        else:
            print("警告：未知响应格式")
            return []

        # 过滤低量/低流动性市场
        filtered = [
            m for m in markets
            if float(m.get("volume", 0)) >= MIN_VOLUME_USD
            and float(m.get("liquidity", 0)) >= MIN_LIQUIDITY_USD
        ]

        print(f"第 {page} 页：原始 {len(markets)} 条 → 过滤后 {len(filtered)} 条")
        return filtered

    except httpx.HTTPStatusError as e:
        print(f"HTTP 错误 {e.response.status_code}: {e.response.text[:200]}...")
        return []
    except Exception as e:
        print(f"请求失败: {str(e)}")
        return []


# ===================== 主函数 =====================
def main():
    print("=" * 90)
    print("Polymarket 活跃市场查询（Gamma API）")
    print(f"过滤：volume ≥ ${MIN_VOLUME_USD:,} | liquidity ≥ ${MIN_LIQUIDITY_USD:,}")
    print(f"显示前 {MAX_MARKETS_TO_SHOW} 个")
    print("=" * 90)
    print()

    all_markets: List[Dict[str, Any]] = []

    for page in range(1, PAGES_TO_FETCH + 1):
        page_markets = fetch_page(page)
        all_markets.extend(page_markets)
        time.sleep(SLEEP_BETWEEN_PAGES)

        # 如果返回少于 limit，说明可能没更多了
        if len(page_markets) < PER_PAGE_LIMIT:
            print("本页返回数量少于 limit，结束分页")
            break

    if not all_markets:
        print("没有找到符合条件的活跃市场")
        print("可能原因：")
        print("1. 当前时间没有活跃市场")
        print("2. 网络问题或 API 临时不可用")
        print("3. 过滤条件太严格（可降低 MIN_VOLUME_USD）")
        return

    print(f"\n最终找到 {len(all_markets)} 个符合条件的活跃市场")
    print("-" * 90)

    for idx, market in enumerate(all_markets[:MAX_MARKETS_TO_SHOW], 1):
        question = market.get("question", market.get("title", "无标题"))
        active = market.get("active", "未知")
        closed = market.get("closed", "未知")
        accepting = market.get("accepting_orders", "未知")
        volume = float(market.get("volume", 0))
        liquidity = float(market.get("liquidity", 0))

        # 鲁棒处理 clobTokenIds
        clob_raw = market.get("clobTokenIds")
        clob_ids = []

        if clob_raw is not None:
            if isinstance(clob_raw, list):
                clob_ids = [str(x) for x in clob_raw]
            elif isinstance(clob_raw, str):
                # 清理可能的 JSON 字符串格式，如 ["id1","id2"] 或 "id1,id2"
                cleaned = re.sub(r'[\[\]"\']', '', clob_raw)
                clob_ids = [tid.strip() for tid in cleaned.split(',') if tid.strip()]
            elif isinstance(clob_raw, (int, float, str)):
                clob_ids = [str(clob_raw)]

        yes_id = clob_ids[0] if len(clob_ids) > 0 else "未知YES"
        no_id  = clob_ids[1] if len(clob_ids) > 1 else "未知NO"

        print(f"{idx:2d}. {question}")
        print(f"   状态     : active={active} | closed={closed} | accepting_orders={accepting}")
        print(f"   交易量    : ${volume:,.0f}")
        print(f"   流动性    : ${liquidity:,.0f}")
        print(f"   YES token : {yes_id}")
        print(f"   NO  token : {no_id}")
        print("-" * 90)


if __name__ == "__main__":
    main()