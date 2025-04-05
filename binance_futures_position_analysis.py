# 币安期货持仓分析系统
import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import time
from openai import OpenAI
import logging
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import threading
from typing import List, Dict

# 设置页面配置
st.set_page_config(
    page_title="币安期货持仓分析系统",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 添加自定义CSS样式
st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
    }
    div.stButton > button {
        width: 100%;
        background-color: #FF4B4B;
        color: white;
        border-radius: 10px;
        padding: 0.8rem 1rem;
        font-size: 16px;
        font-weight: bold;
        border: none;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }
    .metric-container {
        background-color: #1E2130;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
    .report-container {
        background-color: #1E2130;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
    </style>
    """, unsafe_allow_html=True)

# OpenAI配置
OPENAI_API_KEY = ""
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://api.tu-zi.com/v1"
)


class RateLimiter:
    def __init__(self, max_requests: int, time_window: float):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = Queue()
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            current_time = time.time()
            while not self.requests.empty():
                request_time = self.requests.queue[0]
                if current_time - request_time > self.time_window:
                    self.requests.get()
                else:
                    break
            if self.requests.qsize() >= self.max_requests:
                oldest_request = self.requests.queue[0]
                sleep_time = oldest_request + self.time_window - current_time
                if sleep_time > 0:
                    time.sleep(sleep_time)
            self.requests.put(current_time)


class BinanceFuturesAnalyzer:
    def __init__(self):
        self.base_url = "https://fapi.binance.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.rate_limiter = RateLimiter(max_requests=5, time_window=1.0)

    def make_request(self, url: str, params: dict = None) -> dict:
        self.rate_limiter.acquire()
        response = requests.get(url, params=params, headers=self.headers)
        return response.json()

    def get_usdt_symbols(self) -> List[str]:
        try:
            data = self.make_request(f"{self.base_url}/fapi/v1/exchangeInfo")
            symbols = [item['symbol'] for item in data['symbols']
                       if item['symbol'].endswith('USDT') and item['status'] == 'TRADING']
            return symbols
        except Exception as e:
            st.error(f"获取交易对时发生错误: {e}")
            return []

    def get_position_data(self, symbol: str, historical_timestamp: int) -> Dict:
        try:
            current_data = self.make_request(
                f"{self.base_url}/fapi/v1/openInterest",
                {'symbol': symbol}
            )
            current_oi = float(current_data['openInterest'])

            historical_data = self.make_request(
                f"{self.base_url}/futures/data/openInterestHist",
                {
                    'symbol': symbol,
                    'period': '1h',
                    'limit': 1,
                    'endTime': historical_timestamp
                }
            )
            historical_oi = float(historical_data[0]['sumOpenInterest']) if historical_data else 0

            change = current_oi - historical_oi
            change_percentage = (change / historical_oi * 100) if historical_oi != 0 else 0

            return {
                'symbol': symbol,
                'current_oi': current_oi,
                'historical_oi': historical_oi,
                'change': change,
                'change_percentage': change_percentage
            }
        except Exception as e:
            return {
                'symbol': symbol,
                'current_oi': 0,
                'historical_oi': 0,
                'change': 0,
                'change_percentage': 0
            }

    def analyze_positions(self):
        symbols = self.get_usdt_symbols()
        historical_timestamp = int((datetime.now() - timedelta(hours=4)).timestamp() * 1000)
        results = []

        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_symbol = {
                executor.submit(self.get_position_data, symbol, historical_timestamp): symbol
                for symbol in symbols
            }

            for future in future_to_symbol:
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    st.error(f"处理结果时发生错误: {e}")

        return pd.DataFrame(results)


def get_ai_analysis(df: pd.DataFrame):
    """获取AI分析结果"""
    try:
        increased = len(df[df['change'] > 0])
        decreased = len(df[df['change'] < 0])

        top_increase = df[df['change'] > 0].sort_values('change_percentage', ascending=False).head(10)
        top_decrease = df[df['change'] < 0].sort_values('change_percentage', ascending=True).head(10)

        prompt = f"""
        作为一位专业的期货交易分析师，请基于以下持仓数据变化提供详细的市场分析报告：

        市场概况：
        - 总交易对数量：{len(df)}
        - 持仓增加数量：{increased}
        - 持仓减少数量：{decreased}

        持仓增加最显著的前10个交易对：
        {top_increase.to_string()}

        持仓减少最显著的前10个交易对：
        {top_decrease.to_string()}

        请提供以下分析（使用markdown格式）：

        ## 市场情绪分析
        [分析整体市场情绪]

        ## 主要变动解读
        - 大额持仓增加分析：
        - 大额持仓减少分析：
        - 潜在市场方向：

        ## 交易机会分析
        - 高关注度品种：
        - 潜在趋势机会：
        - 风险提示：

        请从专业交易员的角度进行分析，注重实用性和操作性。
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 分析生成失败: {str(e)}"
