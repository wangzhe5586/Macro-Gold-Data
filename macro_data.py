import os
import requests
import pandas as pd
from io import BytesIO
from datetime import datetime


# ======================
# Telegram 发送函数
# ======================

TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")


def tg_send(text: str) -> None:
    """发送文本到 Telegram，如果没配置环境变量就只打印"""
    if not TOKEN or not CHAT_ID:
        print("【未配置 Telegram，以下为消息内容】")
        print(text)
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    resp = requests.post(url, data={"chat_id": CHAT_ID, "text": text})
    try:
        resp.raise_for_status()
    except Exception as e:
        print("发送 Telegram 失败：", e)
        print("响应：", resp.text)


# ======================
# WGC 央行黄金储备
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

        # 指定 engine，避免 pandas 提示无法识别格式
        df = pd.read_excel(BytesIO(r.content), engine="openpyxl")

        latest = df.tail(1).T  # 取最后一行并转置，方便阅读
        text = "📒 WGC 央行黄金储备（最新一行原始数据）\n"
        text += latest.to_string(header=False)
        return text

    except Exception as e:
        return f"⚠️ WGC 央行黄金储备抓取失败，已跳过。\n原因：{e}"


# ======================
# GLD ETF 持仓
# ======================

def fetch_gld() -> str:
    """
    抓取 GLD 官方 CSV，展示末尾几行原始数据
    """
    url = "https://www.spdrgoldshares.com/assets/daily-holdings/USD/fund-holdings-usd.csv"
    try:
        df = pd.read_csv(url, skiprows=2)  # 前两行是说明
        tail = df.tail(3)
        text = "📊 GLD ETF 持仓（末尾 3 行原始数据）\n"
        text += tail.to_string(index=False)
        return text
    except Exception as e:
        return f"⚠️ GLD 数据抓取失败，已跳过。\n原因：{e}"


# ======================
# IAU ETF 持仓
# ======================

def fetch_iau() -> str:
    """
    抓取 IAU 官方 CSV，展示末尾几行原始数据
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
# 主执行函数
# ======================

def run() -> None:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    parts = [f"🕒 黄金宏观数据库自动更新（UTC 日期：{today}）\n"]

    parts.append(fetch_wgc())
    parts.append("")  # 空行
    parts.append(fetch_gld())
    parts.append("")
    parts.append(fetch_iau())

    msg = "\n".join(parts)
    print(msg)
    tg_send(msg)


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        err_msg = f"❌ 宏观数据脚本出现未处理错误：{e}"
        print(err_msg)
        tg_send(err_msg)
