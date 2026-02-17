# market_test.py - 修复版：正确处理 get_price 返回的字典
from py_clob_client.client import ClobClient
from decimal import Decimal
import asyncio

async def main():
    client = ClobClient("https://clob.polymarket.com", chain_id=137)

    # 从 gamma_active_events.py 复制的真实 token_id
    yes_token_id = "97449340182256366014320155718265676486703217567849039806162053075113517266910"
    no_token_id  = "59259495934562596318644973716893809974860301509869285036503555129962149752635"

    yes_best_ask = None
    yes_best_bid = None
    no_best_ask  = None
    no_best_bid  = None

    print("查询 YES...")
    try:
        # 获取最佳卖价 (ask)
        yes_ask_resp = client.get_price(yes_token_id, side="sell")
        yes_best_ask = Decimal(yes_ask_resp['price']) if 'price' in yes_ask_resp else None
        print(f"YES best_ask (最低卖价): {yes_best_ask}")

        # 获取最佳买价 (bid)
        yes_bid_resp = client.get_price(yes_token_id, side="buy")
        yes_best_bid = Decimal(yes_bid_resp['price']) if 'price' in yes_bid_resp else None
        print(f"YES best_bid (最高买价): {yes_best_bid}")
    except Exception as e:
        print(f"YES 查询失败: {str(e)}")

    print("\n查询 NO...")
    try:
        no_ask_resp = client.get_price(no_token_id, side="sell")
        no_best_ask = Decimal(no_ask_resp['price']) if 'price' in no_ask_resp else None
        print(f"NO  best_ask (最低卖价): {no_best_ask}")

        no_bid_resp = client.get_price(no_token_id, side="buy")
        no_best_bid = Decimal(no_bid_resp['price']) if 'price' in no_bid_resp else None
        print(f"NO  best_bid (最高买价): {no_best_bid}")
    except Exception as e:
        print(f"NO 查询失败: {str(e)}")

    # 计算 spread（使用 best_ask）
    if yes_best_ask is not None and no_best_ask is not None:
        combined_ask = yes_best_ask + no_best_ask
        spread = Decimal('1') - combined_ask
        print("\n" + "=" * 60)
        print(f"YES best_ask: {yes_best_ask}")
        print(f"NO  best_ask: {no_best_ask}")
        print(f"Combined Ask (买入 YES+NO 成本): {combined_ask}")
        print(f"Spread (潜在套利): {spread} ({spread*100:.4f}%)")
        if spread > 0:
            print("!!! 发现潜在套利机会（理论上） !!!")
            print("  说明：买入 YES+NO 总成本 < 1，结算必得 1")
        else:
            print("当前无套利空间（市场正常或报价合理）")
    else:
        print("\n无法计算 spread（至少一个 best_ask 为空）")
        print("建议：")
        print("1. 确认 token_id 来自活跃市场（active=True, closed=False）")
        print("2. 换一个交易量/流动性更大的市场再试（volume > 10k）")
        print("3. 检查网络或 API 是否临时异常")

if __name__ == "__main__":
    asyncio.run(main())