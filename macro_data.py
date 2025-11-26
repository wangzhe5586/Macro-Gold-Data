import os
import requests
import pandas as pd
from io import BytesIO
from datetime import datetime


# ======================
# 0. Telegram 发送函数
# ======================
TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")


def tg_send(text: str):
    """发送文本到 Telegram，如果环境变量没配置就只打印"""
    if not TOKEN or not CHAT_ID:
        print("Telegram 配置缺失，消息内容如下：")
        print(text)
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    resp = requests.post(url, data={"chat_id": CHAT_ID, "text": text})
    try:
        resp.raise_for_status()
    except Exception as e:
        print("发送 Telegram 失败：", e)
        print("响应内容：", resp.text)


# ======================
# 1. WGC 央行黄金储备
# ======================
def fetch_wgc() -> str:
    """
    抓取世界黄金协会 WGC 央行储备数据
    如果无法识别为 Excel，就返回错误提示，不让脚本崩溃
    """
    url = "https://www.gold.org/download-file?filename=gold-reserves.xlsx"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()

        # 指定 engine，避免 pandas 抱怨无法识别格式
        df = pd.read_excel(BytesIO(r.content), engine="openpyxl")

        # 取最后一行作为最新数据（不同年份结构可能略有差异，这里只做简要展示）
        latest = df.tail(1).T  # 转置便于阅读
        text = "📒 WGC 央行黄金储备（最新一行原始数据）\n"
        text += latest.to_string(header=False)
        return text

    except Exception as e:
        return f"⚠️ WGC 央行黄金储备抓取失败，已跳过。\n原因：{e}"


# ======================
# 2. GLD ETF 持仓
# ======================
def fetch_gld() -> str:
    """
    抓取 GLD 官方 CSV，简单展示最后几行原始数据
    不强行依赖某个字段名，主要防崩溃
    """
    url = "https://www.spdrgoldshares.com/assets/daily-holdings/USD/fund-holdings-usd.csv"
    try:
        df = pd.read_csv(url, skiprows=2)  # 官方文件前两行是说明
        tail = df.tail(3)
        text = "📊 GLD ETF 持仓（末尾 3 行原始数据）\n"
        text += tail.to_string(index=False)
        return text
    except Exception as e:
        return f"⚠️ GLD 数据抓取失败，已跳过。\n原因：{e}"


# ======================
# 3. IAU ETF 持仓
# ======================
def fetch_iau() -> str:
    """
    抓取 IAU 官方 CSV，同样只展示末尾几行
    """
    url = (
        "https://www.ishares.com/us/products/239561/ishares-gold-trust-fund/"
        "1467271812596.ajax?fileType=csv&fileName=IAU_holdings&dataType=fund"
    )
    try:
        df = pd.read_csv(url)
        tail = df.tail(3)
        text = "📊 IAU ETF 持仓（末尾 3 行原始数据）\n"
        text += tail.to_string(index=False)
        return text
    except Exception as e:
        return f"⚠️ IAU 数据抓取失败，已跳过。\n原因：{e}"


# ======================
# 4. 主执行函数
# ======================
def run():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    msg_parts = [f"🕒 黄金宏观数据库自动更新（UTC 日期：{today}）\n"]

    # 各模块独立 try/except，任何一个挂掉都不影响整体
    msg_parts.append(fetch_wgc())
    msg_parts.append("")  # 空行
    msg_parts.append(fetch_gld())
    msg_parts.append("")
    msg_parts.append(fetch_iau())

    final_msg = "\n".join(msg_parts)
    print(final_msg)
    tg_send(final_msg)


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        # 兜底：绝不让脚本因为未捕获异常而直接崩溃
        err_msg = f"❌ 宏观数据脚本出现未处理错误：{e}"
        print(err_m_
