import os
import re
import time
from io import BytesIO
from datetime import datetime

import pandas as pd
import requests


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
# 1. WGC 央行黄金储备（只做简单状态提示）
# ======================

def fetch_wgc() -> str:
    """
    只负责确认 WGC 最新 Excel 是否能下载成功，
    不在推送里展开一大堆原始行，避免刷屏。
    """
    base = "https://www.gold.org"
    page_url = base + "/goldhub/data/gold-reserves-by-country"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        page = requests.get(page_url, headers=headers, timeout=30)
        page.raise_for_status()
        html = page.text

        matches = re.findall(r'href="([^"]+\\.xlsx)"', html)
        if not matches:
            return "📒【央行储备】WGC 页面可访问，但未找到 Excel 下载链接，结构可能变动。"

        xurl = matches[0]
        if xurl.startswith("/"):
            xurl = base + xurl

        r = requests.get(xurl, headers=headers, timeout=30)
        r.raise_for_status()

        df = pd.read_excel(BytesIO(r.content), engine="openpyxl")
        rows = len(df)

        return f"📒【央行储备】WGC 最新 Excel 下载成功（约 {rows} 行数据，后续可在本地进一步分析）。"

    except Exception as e:
        return f"📒【央行储备】WGC 数据抓取失败，已跳过。\n原因：{e}"


# ======================
# 2. GLD ETF 持仓：日变动 + 近 5 日趋势
# ======================

def fetch_gld() -> str:
    """
    使用 SPDR 官方历史数据 CSV：
    https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv

    计算：
    - 最新持仓（吨）
    - 昨日 -> 今日 日变动
    - 近 5 交易日累积变动
    """
    url = "https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv"

    try:
        df = pd.read_csv(url)

        # 处理日期
        if "Date" not in df.columns:
            raise ValueError("GLD CSV 中不含 Date 列")

        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date")

        # 找“Tonnes”列
        tonne_cols = [c for c in df.columns if "Tonne" in c or "Tonnes" in c]
        if not tonne_cols:
            raise ValueError(f"未找到 Tonnes 列，现有列：{list(df.columns)}")
        t_col = tonne_cols[0]

        # 保证至少有 5 行
        if len(df) < 5:
            raise ValueError("GLD 历史数据不足 5 行")

        last5 = df.tail(5).copy()
        today_row = last5.iloc[-1]
        prev_row = last5.iloc[-2]
        first_row = last5.iloc[0]

        today_date = today_row["Date"].strftime("%Y-%m-%d")
        today_tonnes = float(today_row[t_col])
        prev_tonnes = float(prev_row[t_col])
        first_tonnes = float(first_row[t_col])

        day_change = today_tonnes - prev_tonnes
        five_change = today_tonnes - first_tonnes

        text_lines = [
            "📊【GLD ETF 持仓】全球最大黄金 ETF",
            f"- 最新日期：{today_date}",
            f"- 当前持仓：{today_tonnes:.2f} 吨",
            f"- 日变动：{day_change:+.2f} 吨",
            f"- 近 5 日累积：{five_change:+.2f} 吨",
        ]
        return "\n".join(text_lines)

    except Exception as e:
        return f"📊【GLD ETF 持仓】数据抓取失败，已跳过。\n原因：{e}"


# ======================
# 3. IAU ETF：价格 + 日变动 + 近 5 日价格趋势
# ======================

def fetch_iau() -> str:
    """
    使用 Stooq 免费日线数据：
    https://stooq.com/q/d/l/?s=iau.us&i=d

    计算：
    - 最新收盘价
    - 日价格变动
    - 近 5 日累计价格变动
    这里只是价格微观情绪参考，不是持仓吨数。
    """
    url = "https://stooq.com/q/d/l/?s=iau.us&i=d"

    try:
        df = pd.read_csv(url)
        if len(df) < 5:
            raise ValueError("IAU 历史数据不足 5 行")

        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date")

        last5 = df.tail(5).copy()
        today = last5.iloc[-1]
        prev = last5.iloc[-2]
        first = last5.iloc[0]

        today_date = today["Date"].strftime("%Y-%m-%d")
        today_close = float(today["Close"])
        prev_close = float(prev["Close"])
        first_close = float(first["Close"])

        day_change = today_close - prev_close
        day_pct = day_change / prev_close * 100 if prev_close != 0 else 0.0

        five_change = today_close - first_close
        five_pct = five_change / first_close * 100 if first_close != 0 else 0.0

        text_lines = [
            "📈【IAU ETF 价格】美国第二大黄金 ETF（价格参考）",
            f"- 最新日期：{today_date}",
            f"- 收盘价：{today_close:.2f} 美元",
            f"- 日变动：{day_change:+.2f} 美元（{day_pct:+.2f}%）",
            f"- 近 5 日：{five_change:+.2f} 美元（{five_pct:+.2f}%）",
        ]
        return "\n".join(text_lines)

    except Exception as e:
        return f"📈【IAU ETF 价格】数据抓取失败，已跳过。\n原因：{e}"


# ======================
# 主执行函数
# ======================

def run() -> None:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    parts = [f"🕒 黄金宏观数据库自动更新（UTC 日期：{today})", ""]

    # 央行储备（简单状态）
    parts.append(fetch_wgc())
    parts.append("")

    # GLD：持仓 + 日变动 + 近 5 日
    parts.append(fetch_gld())
    parts.append("")

    # IAU：价格 + 日变动 + 近 5 日
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
