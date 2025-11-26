import os
import requests
import pandas as pd
from io import BytesIO
from datetime import datetime
import re
import time


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
# 1. WGC 央行黄金储备
# ======================

def fetch_wgc() -> str:
    """
    先打开 gold.org 的“各国黄金储备”页面，
    在 HTML 里自动搜索第一个 .xlsx 链接，再去下载。
    这样比死写一个固定 Excel 地址更稳。
    """
    base = "https://www.gold.org"
    page_url = base + "/goldhub/data/gold-reserves-by-country"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        page = requests.get(page_url, headers=headers, timeout=30)
        page.raise_for_status()
        html = page.text

        # 找出页面中的所有 xlsx 链接
        matches = re.findall(r'href="([^"]+\\.xlsx)"', html)
        if not matches:
            return "⚠️ WGC 央行黄金储备抓取失败，页面中未找到 xlsx 链接。"

        xurl = matches[0]
        if xurl.startswith("/"):
            xurl = base + xurl

        r = requests.get(xurl, headers=headers, timeout=30)
        r.raise_for_status()

        df = pd.read_excel(BytesIO(r.content), engine="openpyxl")

        # 取最后一行作为“最新数据”，转置方便阅读
        latest = df.tail(1).T
        text = "📒 WGC 央行黄金储备（最新一行原始数据）\\n"
        text += latest.to_string(header=False)
        return text

    except Exception as e:
        return f"⚠️ WGC 央行黄金储备抓取失败，已跳过。\\n原因：{e}"


# ======================
# 2. GLD ETF 历史数据（官方 CSV）
# ======================

def fetch_gld() -> str:
    """
    使用 SPDR 官方提供的历史数据 CSV：
    https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv
    """
    url = "https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv"
    try:
        df = pd.read_csv(url)
        last = df.tail(1)
        text = "📊 GLD ETF 历史数据（最后 1 行）\\n"
        text += last.to_string(index=False)
        return text
    except Exception as e:
        return f"⚠️ GLD 数据抓取失败，已跳过。\\n原因：{e}"


# ======================
# 3. IAU ETF 日线价格（Yahoo Finance）
# ======================

def fetch_iau() -> str:
    """
    暂时用 Yahoo Finance 提供的 IAU 日线价格和成交量：
    https://query1.finance.yahoo.com/v7/finance/download/IAU
    这里取最近 30 天数据中的最后一条（最新交易日）。
    """
    end = int(time.time())
    start = end - 30 * 24 * 3600

    url = (
        "https://query1.finance.yahoo.com/v7/finance/download/IAU"
        f"?period1={start}&period2={end}&interval=1d&events=history&includeAdjustedClose=true"
    )

    try:
        df = pd.read_csv(url)
        last = df.iloc[-1]
        close = last["Close"]
        volume = int(last["Volume"])
        date = last["Date"]

        text = (
            "📈 IAU ETF 价格（最近 1 日）\\n"
            f"日期: {date}, 收盘价: {close}, 成交量: {volume}"
        )
        return text
    except Exception as e:
        return f"⚠️ IAU 数据抓取失败，已跳过。\\n原因：{e}"


# ======================
# 主执行函数
# ======================

def run() -> None:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    parts = [f"🕒 黄金宏观数据库自动更新（UTC 日期：{today}）\\n"]

    parts.append(fetch_wgc())
    parts.append("")  # 空行
    parts.append(fetch_gld())
    parts.append("")
    parts.append(fetch_iau())

    msg = "\\n".join(parts)
    print(msg)
    tg_send(msg)


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        err_msg = f"❌ 宏观数据脚本出现未处理错误：{e}"
        print(err_msg)
        tg_send(err_msg)
