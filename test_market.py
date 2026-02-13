# test_market.py
from py_clob_client.client import ClobClient
from decimal import Decimal
import asyncio

async def main():
    # 只读客户端（不需要私钥）
    client = ClobClient(
        host="https://clob.polymarket.com",
        chain_id=137  # Polygon 主网
    )

    # 替换成你想测试的 YES token_id（下面教怎么找）
    yes_token_id = "你的YES_TOKEN_ID"   # 示例：71321045679252212594626385532706912750332728571942532289631379312455583992563

    # 获取订单簿
    orderbook = client.get_order_book(yes_token_id)

    # 提取最佳 ask（最低卖价）
    yes_best_ask = orderbook.best_ask
    print(f"YES 最佳卖价: {yes_best_ask}")

    # 如果你已经有 NO 的 token_id，也可以一起取
    # no_best_ask = client.get_order_book(no_token_id).best_ask
    # combined = yes_best_ask + no_best_ask
    # print(f"Combined Ask: {combined}")
    # print(f"潜在 spread: {1 - combined:.4f}")

if __name__ == "__main__":
    asyncio.run(main())