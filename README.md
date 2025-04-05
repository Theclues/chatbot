# chatbot
https://api.tu-zi.com/topup

不知道哪里获取Openai或者其他大模型的API，用这个网站！

开发测试的话，5元（RMB），足够了

运行需要使用命令行：

streamlit run http://app.py（更换为自己的py文件名）

在该项目中，我已经对文件名进行了替换
币安期货持仓分析系统 -> binance_futures_position_analysis.py
费率监测系统辅助程序 -> crypto_funding_tracker.py
使用deepseek分析资金流向 -> deepseek_fundflow_analysis.py
加密货币期费率交易监测系统 -> funding_rate_monitor.py

## 使用
默认已经在本地安装了 python 以及 pip
1. 安装依赖
```shell
pip3 install -r requirements.txt
```
2. 运行
```shell
# 币安期货持仓分析系统
streamlit run binance_futures_position_analysis.py
# 费率监测系统辅助程序
python3 crypto_funding_tracker.py
# 使用deepseek分析资金流向
python3 deepseek_fundflow_analysis.py
# 加密货币期费率交易监测系统
streamlit run funding_rate_monitor.py
```