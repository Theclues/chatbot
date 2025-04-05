# 使用deepseek分析资金流向
import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import concurrent.futures
import json

# Binance API 端点
SPOT_BASE_URL = "https://api.binance.com/api/v3"
FUTURES_BASE_URL = "https://fapi.binance.com/fapi/v1"

# DeepSeek API 配置（假设使用官方API，需替换为你的API Key）
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_API_KEY = "请替换为实际的API"  # 请替换为实际的API Key

# 稳定币列表（美元稳定币和欧元稳定币）
STABLECOINS = {'USDC', 'TUSD', 'BUSD', 'DAI', 'USDP', 'EUR', 'GYEN'}

def get_all_usdt_symbols(is_futures=False):
    """获取所有以USDT结尾的交易对，剔除稳定币对"""
    base_url = FUTURES_BASE_URL if is_futures else SPOT_BASE_URL
    endpoint = "/exchangeInfo"

    response = requests.get(f"{base_url}{endpoint}")
    data = response.json()

    symbols = []
    if is_futures:
        for item in data['symbols']:
            symbol = item['symbol']
            base_asset = item['baseAsset']
            if (item['status'] == 'TRADING' and
                item['quoteAsset'] == 'USDT' and
                base_asset not in STABLECOINS):
                symbols.append(symbol)
    else:
        for item in data['symbols']:
            symbol = item['symbol']
            base_asset = item['baseAsset']
            if (item['status'] == 'TRADING' and
                item['quoteAsset'] == 'USDT' and
                base_asset not in STABLECOINS):
                symbols.append(symbol)
    return symbols

def format_number(value):
    """将数值格式化为K/M表示，保留两位小数"""
    if abs(value) >= 1000000:
        return f"{value / 1000000:.2f}M"
    elif abs(value) >= 1000:
        return f"{value / 1000:.2f}K"
    else:
        return f"{value:.2f}"

def get_klines_parallel(symbols, is_futures=False, max_workers=20):
    """使用线程池并行获取多个交易对的K线数据（使用倒数第二根已完成的日线蜡烛图）"""
    results = []

    def fetch_kline(symbol):
        try:
            base_url = FUTURES_BASE_URL if is_futures else SPOT_BASE_URL
            endpoint = "/klines"

            now = datetime.utcnow()
            today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
            end_time = int(today_start.timestamp() * 1000)
            start_time = int((today_start - timedelta(days=2)).timestamp() * 1000)

            params = {
                'symbol': symbol,
                'interval': '4h',
                'startTime': start_time,
                'endTime': end_time,
                'limit': 2
            }

            response = requests.get(f"{base_url}{endpoint}", params=params)
            data = response.json()

            if not data or len(data) < 2:
                print(f"Insufficient data for {symbol}: {len(data)} candles returned")
                return None

            k = data[1]  # 使用倒数第一根已完成K线
            open_time = datetime.fromtimestamp(k[0] / 1000).strftime('%Y-%m-%d %H:%M:%S')
            close_time = datetime.fromtimestamp(k[6] / 1000).strftime('%Y-%m-%d %H:%M:%S')

            return {
                'symbol': symbol,
                'open_time': open_time,
                'close_time': close_time,
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5]),
                'quote_volume': float(k[7]),
                'trades': int(k[8]),
                'taker_buy_base_volume': float(k[9]),
                'taker_buy_quote_volume': float(k[10]),
                'net_inflow': 2 * float(k[10]) - float(k[7])
            }
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_kline, symbol): symbol for symbol in symbols}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    return results

def send_to_deepseek(data):
    """将数据发送给DeepSeek API并获取解读"""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = (
        "以下是Binance现货和期货市场中USDT交易对的资金流入流出数据（基于前一天的已完成日线数据），请分析：\n"
        "1. 期货和现货市场中出现的相同交易对及其流入流出情况。\n"
        "2. 从资金流角度解读这些数据，可能的市场趋势或交易信号。\n"
        "3. 提供专业的资金分析视角，例如大资金动向、潜在的市场操纵迹象等。\n"
        "数据如下：\n" + json.dumps(data, indent=2, ensure_ascii=False) +
        "\n请以中文回复，尽量简洁但专业。"
    )

    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000,
        "temperature": 0.7
    }

    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except Exception as e:
        print(f"DeepSeek API error: {e}")
        return "无法获取DeepSeek分析结果"

def main_optimized():
    # 获取所有USDT交易对（剔除稳定币）
    spot_symbols = get_all_usdt_symbols(is_futures=False)
    futures_symbols = get_all_usdt_symbols(is_futures=True)

    print(f"获取到 {len(spot_symbols)} 个现货交易对和 {len(futures_symbols)} 个期货交易对")

    # 使用线程池并行获取数据
    print("使用线程池并行获取数据...")
    spot_data = get_klines_parallel(spot_symbols, is_futures=False, max_workers=20)
    futures_data = get_klines_parallel(futures_symbols, is_futures=True, max_workers=20)

    # 转换为DataFrame并排序
    spot_df = pd.DataFrame(spot_data)
    futures_df = pd.DataFrame(futures_data)

    # 提取Top 20数据
    spot_inflow_top20 = spot_df.sort_values(by='net_inflow', ascending=False).head(20)
    futures_inflow_top20 = futures_df.sort_values(by='net_inflow', ascending=False).head(20)
    spot_outflow_top20 = spot_df.sort_values(by='net_inflow', ascending=True).head(20)
    futures_outflow_top20 = futures_df.sort_values(by='net_inflow', ascending=True).head(20)

    # 打印结果
    print("\n现货交易对净流入TOP20:")
    for _, row in spot_inflow_top20.iterrows():
        print(f"{row['symbol']}: 净流入 {format_number(row['net_inflow'])} USDT, 成交额 {format_number(row['quote_volume'])} USDT")

    print("\n期货交易对净流入TOP20:")
    for _, row in futures_inflow_top20.iterrows():
        print(f"{row['symbol']}: 净流入 {format_number(row['net_inflow'])} USDT, 成交额 {format_number(row['quote_volume'])} USDT")

    print("\n现货交易对净流出TOP20:")
    for _, row in spot_outflow_top20.iterrows():
        print(f"{row['symbol']}: 净流入 {format_number(row['net_inflow'])} USDT, 成交额 {format_number(row['quote_volume'])} USDT")

    print("\n期货交易对净流出TOP20:")
    for _, row in futures_outflow_top20.iterrows():
        print(f"{row['symbol']}: 净流入 {format_number(row['net_inflow'])} USDT, 成交额 {format_number(row['quote_volume'])} USDT")

    # 准备发送给DeepSeek的数据
    deepseek_data = {
        "spot_inflow_top20": spot_inflow_top20[['symbol', 'net_inflow', 'quote_volume']].to_dict('records'),
        "futures_inflow_top20": futures_inflow_top20[['symbol', 'net_inflow', 'quote_volume']].to_dict('records'),
        "spot_outflow_top20": spot_outflow_top20[['symbol', 'net_inflow', 'quote_volume']].to_dict('records'),
        "futures_outflow_top20": futures_outflow_top20[['symbol', 'net_inflow', 'quote_volume']].to_dict('records')
    }

    # 发送给DeepSeek并获取分析
    print("\n正在请求DeepSeek API进行数据解读...")
    analysis = send_to_deepseek(deepseek_data)
    print("\nDeepSeek分析结果：")
    print(analysis)

if __name__ == "__main__":
    main_optimized()
