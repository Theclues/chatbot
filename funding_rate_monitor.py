# 加密货币期费率交易监测系统
import streamlit as st
import pandas as pd
import time
import requests
import json
import os
from datetime import datetime, timedelta, timezone
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 页面配置
st.set_page_config(
    page_title="加密货币费率监控系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"  # 默认折叠侧边栏
)

# 初始化会话状态
if 'symbol' not in st.session_state:
    st.session_state.symbol = "BTCUSDT"
if 'timestamps' not in st.session_state:
    st.session_state.timestamps = []
    st.session_state.spot_prices = []
    st.session_state.futures_prices = []
    st.session_state.premiums = []
    st.session_state.funding_rates = []
    st.session_state.open_interest = []
    st.session_state.last_funding_rate = None
    st.session_state.running = False
    st.session_state.charts = [None, None, None]
    st.session_state.historical_data_loaded = False
    st.session_state.stats_data = None
    st.session_state.last_stats_update = None

# 常量
UPDATE_INTERVAL = 10  # 数据更新间隔（秒）
MAX_DATA_POINTS = 240  # 最大数据点数量 (4小时 = 240分钟)
HOURS_TO_DISPLAY = 4  # 显示过去多少小时的数据
STATS_FILE = "funding_rates_stats.json"  # 统计数据文件


# 读取统计数据
def load_stats_data():
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'r') as f:
                data = json.load(f)
                st.session_state.stats_data = data
                st.session_state.last_stats_update = datetime.now()
                return data
        return None
    except Exception as e:
        st.error(f"读取统计数据出错: {e}")
        return None


# 获取现货价格
def get_spot_price(symbol):
    try:
        url = "https://api.binance.com/api/v3/ticker/price"
        params = {"symbol": symbol}
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if "price" in data:
            return float(data["price"])
        else:
            st.error(f"无法获取现货价格: {data}")
            return None
    except Exception as e:
        st.error(f"获取现货价格时出错: {e}")
        return None


# 获取期货价格
def get_futures_price(symbol):
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/price"
        params = {"symbol": symbol}
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if "price" in data:
            return float(data["price"])
        else:
            st.error(f"无法获取期货价格: {data}")
            return None
    except Exception as e:
        st.error(f"获取期货价格时出错: {e}")
        return None


# 获取资金费率
def get_funding_rate(symbol):
    try:
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        params = {"symbol": symbol}
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if "lastFundingRate" in data:
            return float(data["lastFundingRate"])
        else:
            st.error(f"无法获取资金费率: {data}")
            return None
    except Exception as e:
        st.error(f"获取资金费率时出错: {e}")
        return None


# 获取持仓量
def get_open_interest(symbol):
    try:
        url = "https://fapi.binance.com/fapi/v1/openInterest"
        params = {"symbol": symbol}
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if "openInterest" in data:
            return float(data["openInterest"])
        else:
            st.error(f"无法获取持仓量: {data}")
            return None
    except Exception as e:
        st.error(f"获取持仓量时出错: {e}")
        return None


# 获取历史K线数据
def get_historical_klines(symbol, interval, limit):
    try:
        # 计算结束时间（当前时间）和开始时间（4小时前）
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = int((datetime.now(timezone.utc) - timedelta(hours=HOURS_TO_DISPLAY)).timestamp() * 1000)

        # 获取现货历史数据
        spot_url = "https://api.binance.com/api/v3/klines"
        spot_params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }
        spot_response = requests.get(spot_url, params=spot_params)
        spot_response.raise_for_status()
        spot_data = spot_response.json()

        # 获取期货历史数据
        futures_url = "https://fapi.binance.com/fapi/v1/klines"
        futures_params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }
        futures_response = requests.get(futures_url, params=futures_params)
        futures_response.raise_for_status()
        futures_data = futures_response.json()

        # 处理数据
        historical_timestamps = []
        historical_spot_prices = []
        historical_futures_prices = []
        historical_premiums = []

        # 确保两个数据集长度相同
        min_length = min(len(spot_data), len(futures_data))

        for i in range(min_length):
            timestamp = datetime.fromtimestamp(spot_data[i][0] / 1000, tz=timezone.utc)
            spot_close = float(spot_data[i][4])
            futures_close = float(futures_data[i][4])
            premium = (futures_close - spot_close) / spot_close * 100

            historical_timestamps.append(timestamp)
            historical_spot_prices.append(spot_close)
            historical_futures_prices.append(futures_close)
            historical_premiums.append(premium)

        return historical_timestamps, historical_spot_prices, historical_futures_prices, historical_premiums
    except Exception as e:
        st.error(f"获取历史K线数据时出错: {e}")
        return [], [], [], []


# 获取历史资金费率数据
def get_historical_funding_rates(symbol, limit=MAX_DATA_POINTS):
    try:
        # 计算结束时间（当前时间）和开始时间（4小时前）
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = int((datetime.now(timezone.utc) - timedelta(hours=HOURS_TO_DISPLAY)).timestamp() * 1000)

        url = "https://fapi.binance.com/fapi/v1/fundingRate"
        params = {
            "symbol": symbol,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }

        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        timestamps = []
        funding_rates = []

        for item in data:
            timestamps.append(datetime.fromtimestamp(item["fundingTime"] / 1000, tz=timezone.utc))
            funding_rates.append(float(item["fundingRate"]) * 100)  # 转换为百分比

        return timestamps, funding_rates
    except Exception as e:
        st.error(f"获取历史资金费率数据时出错: {e}")
        return [], []


# 获取历史持仓量数据
def get_historical_open_interest(symbol, period="5m", limit=MAX_DATA_POINTS):
    try:
        # 计算结束时间（当前时间）和开始时间（4小时前）
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = int((datetime.now(timezone.utc) - timedelta(hours=HOURS_TO_DISPLAY)).timestamp() * 1000)

        url = "https://fapi.binance.com/futures/data/openInterestHist"
        params = {
            "symbol": symbol,
            "period": period,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }

        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        timestamps = []
        open_interests = []

        for item in data:
            timestamps.append(datetime.fromtimestamp(item["timestamp"] / 1000, tz=timezone.utc))
            open_interests.append(float(item["sumOpenInterest"]))

        return timestamps, open_interests
    except Exception as e:
        st.error(f"获取历史持仓量数据时出错: {e}")
        return [], []


# 更新数据
def update_data(symbol):
    # 获取当前时间
    now = datetime.now(timezone.utc)

    # 获取价格、资金费率和持仓量
    spot_price = get_spot_price(symbol)
    futures_price = get_futures_price(symbol)
    funding_rate = get_funding_rate(symbol)
    open_interest = get_open_interest(symbol)

    # 如果价格数据可用，则更新数据
    if spot_price is not None and futures_price is not None:
        # 计算溢价率
        premium = (futures_price - spot_price) / spot_price * 100

        # 添加数据到列表
        st.session_state.timestamps.append(now)
        st.session_state.spot_prices.append(spot_price)
        st.session_state.futures_prices.append(futures_price)
        st.session_state.premiums.append(premium)

        # 如果资金费率可用，则更新
        if funding_rate is not None:
            st.session_state.funding_rates.append(funding_rate * 100)  # 转换为百分比
            st.session_state.last_funding_rate = funding_rate
        elif st.session_state.funding_rates:  # 如果有历史数据，则使用最后一个值
            st.session_state.funding_rates.append(st.session_state.funding_rates[-1])
        else:
            st.session_state.funding_rates.append(0)

        # 如果持仓量可用，则更新
        if open_interest is not None:
            st.session_state.open_interest.append(open_interest)
        elif st.session_state.open_interest:  # 如果有历史数据，则使用最后一个值
            st.session_state.open_interest.append(st.session_state.open_interest[-1])
        else:
            st.session_state.open_interest.append(0)

        # 清理过期数据 - 只保留过去4小时的数据
        # 但确保不会因为历史数据不足而导致数据减少
        if len(st.session_state.timestamps) > 1:  # 确保至少有数据
            cutoff_time = now - timedelta(hours=HOURS_TO_DISPLAY)

            # 检查最早的时间戳是否已经在4小时内
            # 如果是，则不需要清理，让数据自然累积到4小时
            if st.session_state.timestamps[0] < cutoff_time:
                # 找到第一个不小于cutoff_time的时间戳的索引
                valid_indices = [i for i, ts in enumerate(st.session_state.timestamps) if ts >= cutoff_time]
                if valid_indices:
                    start_idx = valid_indices[0]
                    st.session_state.timestamps = st.session_state.timestamps[start_idx:]
                    st.session_state.spot_prices = st.session_state.spot_prices[start_idx:]
                    st.session_state.futures_prices = st.session_state.futures_prices[start_idx:]
                    st.session_state.premiums = st.session_state.premiums[start_idx:]
                    st.session_state.funding_rates = st.session_state.funding_rates[start_idx:]
                    st.session_state.open_interest = st.session_state.open_interest[start_idx:]

        return spot_price, futures_price, premium, funding_rate, open_interest

    return None, None, None, funding_rate, open_interest


# 创建溢价率图表
def create_premium_chart():
    if not st.session_state.timestamps:
        return None

    fig = go.Figure()

    # 添加溢价率线
    fig.add_trace(
        go.Scatter(
            x=st.session_state.timestamps,
            y=st.session_state.premiums,
            mode='lines',
            name='期现溢价率 (%)',
            line=dict(color='green')
        )
    )

    # 更新布局
    fig.update_layout(
        height=300,
        title_text=f"{st.session_state.symbol} 期现溢价率 (%)",
        margin=dict(l=40, r=40, t=50, b=30),
        xaxis_title="时间 (UTC)",
        yaxis_title="期现溢价率 (%)",
        xaxis=dict(
            range=[
                datetime.now(timezone.utc) - timedelta(hours=HOURS_TO_DISPLAY),
                datetime.now(timezone.utc)
            ]
        )
    )

    # 添加零线
    fig.add_hline(y=0, line_dash="dot", line_color="gray")

    return fig


# 创建资金费率图表
def create_funding_rate_chart():
    if not st.session_state.timestamps:
        return None

    fig = go.Figure()

    # 添加资金费率线
    fig.add_trace(
        go.Scatter(
            x=st.session_state.timestamps,
            y=st.session_state.funding_rates,
            mode='lines',
            name='资金费率 (%)',
            line=dict(color='red')
        )
    )

    # 更新布局
    fig.update_layout(
        height=300,
        title_text=f"{st.session_state.symbol} 资金费率 (%)",
        margin=dict(l=40, r=40, t=50, b=30),
        xaxis_title="时间 (UTC)",
        yaxis_title="资金费率 (%)",
        xaxis=dict(
            range=[
                datetime.now(timezone.utc) - timedelta(hours=HOURS_TO_DISPLAY),
                datetime.now(timezone.utc)
            ]
        )
    )

    # 添加零线
    fig.add_hline(y=0, line_dash="dot", line_color="gray")

    return fig


# 创建持仓量图表
def create_open_interest_chart():
    if not st.session_state.timestamps:
        return None

    fig = go.Figure()

    # 添加持仓量线
    fig.add_trace(
        go.Scatter(
            x=st.session_state.timestamps,
            y=st.session_state.open_interest,
            mode='lines',
            name='持仓量',
            line=dict(color='blue')
        )
    )

    # 更新布局
    fig.update_layout(
        height=300,
        title_text=f"{st.session_state.symbol} 持仓量",
        margin=dict(l=40, r=40, t=50, b=30),
        xaxis_title="时间 (UTC)",
        yaxis_title="持仓量",
        xaxis=dict(
            range=[
                datetime.now(timezone.utc) - timedelta(hours=HOURS_TO_DISPLAY),
                datetime.now(timezone.utc)
            ]
        )
    )

    return fig


# 加载历史数据
def load_historical_data(symbol):
    if not st.session_state.historical_data_loaded:
        with st.spinner("正在加载历史数据..."):
            # 获取过去4小时的1分钟K线数据
            timestamps, spot_prices, futures_prices, premiums = get_historical_klines(
                symbol, "1m", MAX_DATA_POINTS
            )

            # 获取历史资金费率数据
            funding_timestamps, funding_rates = get_historical_funding_rates(symbol)

            # 获取历史持仓量数据
            oi_timestamps, open_interests = get_historical_open_interest(symbol)

            if timestamps:
                st.session_state.timestamps = timestamps
                st.session_state.spot_prices = spot_prices
                st.session_state.futures_prices = futures_prices
                st.session_state.premiums = premiums

                # 初始化资金费率列表
                if funding_rates:
                    # 将资金费率数据映射到时间戳上
                    mapped_funding_rates = []
                    for ts in timestamps:
                        # 找到最接近的资金费率时间戳
                        closest_idx = 0
                        min_diff = float('inf')
                        for i, fts in enumerate(funding_timestamps):
                            diff = abs((ts - fts).total_seconds())
                            if diff < min_diff:
                                min_diff = diff
                                closest_idx = i

                        # 使用最接近时间的资金费率
                        if closest_idx < len(funding_rates):
                            mapped_funding_rates.append(funding_rates[closest_idx])
                        else:
                            mapped_funding_rates.append(0)

                    st.session_state.funding_rates = mapped_funding_rates
                else:
                    st.session_state.funding_rates = [0] * len(timestamps)

                # 初始化持仓量列表
                if open_interests:
                    # 将持仓量数据映射到时间戳上
                    mapped_open_interests = []
                    for ts in timestamps:
                        # 找到最接近的持仓量时间戳
                        closest_idx = 0
                        min_diff = float('inf')
                        for i, ots in enumerate(oi_timestamps):
                            diff = abs((ts - ots).total_seconds())
                            if diff < min_diff:
                                min_diff = diff
                                closest_idx = i

                        # 使用最接近时间的持仓量
                        if closest_idx < len(open_interests):
                            mapped_open_interests.append(open_interests[closest_idx])
                        else:
                            mapped_open_interests.append(0)

                    st.session_state.open_interest = mapped_open_interests
                else:
                    st.session_state.open_interest = [0] * len(timestamps)

                # 获取当前资金费率和持仓量
                funding_rate = get_funding_rate(symbol)
                open_interest = get_open_interest(symbol)

                if funding_rate is not None:
                    st.session_state.last_funding_rate = funding_rate
                    if st.session_state.funding_rates:
                        st.session_state.funding_rates[-1] = funding_rate * 100

                if open_interest is not None and st.session_state.open_interest:
                    st.session_state.open_interest[-1] = open_interest

                st.session_state.historical_data_loaded = True
                return True

            return False
    return True


def display_stats_data():
    # 检查是否需要更新数据（每分钟更新一次）
    if (st.session_state.last_stats_update is None or
            (datetime.now() - st.session_state.last_stats_update).total_seconds() > 60):
        load_stats_data()

    # 创建一个容器来包含所有统计数据
    container = st.container()

    with container:
        if st.session_state.stats_data:
            data = st.session_state.stats_data
            timestamp = data.get("timestamp", "未知")

            # 创建四列布局
            col1, col2, col3, col4 = st.columns(4)

            # 1. 费率最高的交易对
            with col1:
                st.subheader("费率最高的交易对")
                if "highest_rates" in data and data["highest_rates"]:
                    df_highest = pd.DataFrame([
                        {"交易对": item.get("symbol", ""),
                         "费率": f"{item.get('rate', 0) * 100:.2f}%"}
                        for item in data["highest_rates"]
                    ])
                    st.dataframe(df_highest, hide_index=True)
                else:
                    st.write("暂无数据")

            # 2. 费率最低的交易对
            with col2:
                st.subheader("费率最低的交易对")
                if "lowest_rates" in data and data["lowest_rates"]:
                    df_lowest = pd.DataFrame([
                        {"交易对": item.get("symbol", ""),
                         "费率": f"{item.get('rate', 0) * 100:.2f}%"}
                        for item in data["lowest_rates"]
                    ])
                    st.dataframe(df_lowest, hide_index=True)
                else:
                    st.write("暂无数据")

            # 3. 费率增长最大的交易对
            with col3:
                st.subheader("费率上升最快")
                if "biggest_increases" in data and data["biggest_increases"]:
                    df_increases = pd.DataFrame([
                        {"交易对": item.get("symbol", ""),
                         "变化": f"{item.get('change', 0) * 100:.4f}%"}
                        for item in data["biggest_increases"]
                    ])
                    st.dataframe(df_increases, hide_index=True)
                else:
                    st.write("暂无数据")

            # 4. 费率下降最大的交易对
            with col4:
                st.subheader("费率下降最快")
                if "biggest_decreases" in data and data["biggest_decreases"]:
                    df_decreases = pd.DataFrame([
                        {"交易对": item.get("symbol", ""),
                         "变化": f"{item.get('change', 0) * 100:.4f}%"}
                        for item in data["biggest_decreases"]
                    ])
                    st.dataframe(df_decreases, hide_index=True)
                else:
                    st.write("暂无数据")

            # 显示更新时间
            st.caption(f"更新时间: {timestamp}")
        else:
            st.error("未能加载数据，请检查API连接")

    return container  # 返回容器对象


# 侧边栏控件
with st.sidebar:
    st.title("监控设置")

    new_symbol = st.text_input(
        "输入交易对",
        value=st.session_state.symbol,
        placeholder="例如: BTCUSDT, ETHUSDT"
    )

    if new_symbol != st.session_state.symbol:
        st.session_state.symbol = new_symbol
        # 重置数据
        st.session_state.timestamps = []
        st.session_state.spot_prices = []
        st.session_state.futures_prices = []
        st.session_state.premiums = []
        st.session_state.funding_rates = []
        st.session_state.open_interest = []
        st.session_state.last_funding_rate = None
        st.session_state.historical_data_loaded = False
        st.session_state.charts = [None, None, None]
        if st.session_state.running:
            st.session_state.running = False
        st.rerun()

    col1, col2 = st.columns(2)

    with col1:
        start_stop = st.button('开始监控' if not st.session_state.running else '停止监控', use_container_width=True)
        if start_stop:
            st.session_state.running = not st.session_state.running
            if st.session_state.running:
                # 加载历史数据
                success = load_historical_data(st.session_state.symbol)
                if not success:
                    st.error("无法加载历史数据，请检查交易对是否正确")
                    st.session_state.running = False
                st.rerun()

    with col2:
        if st.button('清除数据', use_container_width=True):
            st.session_state.timestamps = []
            st.session_state.spot_prices = []
            st.session_state.futures_prices = []
            st.session_state.premiums = []
            st.session_state.funding_rates = []
            st.session_state.open_interest = []
            st.session_state.last_funding_rate = None
            st.session_state.historical_data_loaded = False
            st.session_state.charts = [None, None, None]
            st.rerun()

# 主页面标题
st.title("加密货币期现溢价监控")

# 创建统计数据占位符
stats_placeholder = st.empty()
with stats_placeholder:
    display_stats_data()  # 初始显示统计数据

# 创建固定容器 - 只用于显示最新数据
metrics_placeholder = st.empty()

# 创建三列布局用于图表
chart_col1, chart_col2, chart_col3 = st.columns(3)

# 主循环
if st.session_state.running:
    # 创建一个进度条占位符
    progress_placeholder = st.empty()

    # 如果历史数据未加载，先加载历史数据
    if not st.session_state.historical_data_loaded:
        success = load_historical_data(st.session_state.symbol)
        if not success:
            st.error("无法加载历史数据，请检查交易对是否正确")
            st.session_state.running = False
            st.rerun()

    # 创建图表占位符（只创建一次）
    if st.session_state.charts[0] is None:
        with chart_col1:
            st.session_state.charts[0] = st.empty()
    if st.session_state.charts[1] is None:
        with chart_col2:
            st.session_state.charts[1] = st.empty()
    if st.session_state.charts[2] is None:
        with chart_col3:
            st.session_state.charts[2] = st.empty()

    # 记录上次统计数据更新时间
    last_stats_refresh = time.time()

    while st.session_state.running:
        # 更新数据
        spot_price, futures_price, premium, funding_rate, open_interest = update_data(st.session_state.symbol)

        # 检查是否需要更新统计数据（每60秒更新一次）
        current_time = time.time()
        if current_time - last_stats_refresh > 60:
            with stats_placeholder:
                display_stats_data()  # 更新统计数据
            last_stats_refresh = current_time

        # 使用单个占位符显示最新指标
        if spot_price is not None and futures_price is not None:
            # 获取UTC时间并格式化
            current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            metrics_placeholder.markdown(f"""
            ### 当前数据 - {st.session_state.symbol} ({current_time})
            | 现货价格 | 期货价格 | 期现溢价 | 资金费率 | 持仓量 |
            | --- | --- | --- | --- | --- |
            | {spot_price:.6f} | {futures_price:.6f} | {premium:.4f}% | {funding_rate * 100:.6f}% | {open_interest:.2f} |
            """)

        # 更新图表
        premium_fig = create_premium_chart()
        funding_fig = create_funding_rate_chart()
        open_interest_fig = create_open_interest_chart()

        if premium_fig and st.session_state.charts[0] is not None:
            st.session_state.charts[0].plotly_chart(premium_fig, use_container_width=True)
        if funding_fig and st.session_state.charts[1] is not None:
            st.session_state.charts[1].plotly_chart(funding_fig, use_container_width=True)
        if open_interest_fig and st.session_state.charts[2] is not None:
            st.session_state.charts[2].plotly_chart(open_interest_fig, use_container_width=True)

        # 添加倒计时进度条
        for i in range(UPDATE_INTERVAL, 0, -1):
            progress_placeholder.progress(1 - i / UPDATE_INTERVAL, text=f"下次更新倒计时: {i}秒")
            time.sleep(1)
