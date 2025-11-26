import os
import time
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
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})


# ======================
# 1. WGC 央行储备 —— 先只做状态提示
# ======================

def fetch_wgc() -> str:
    """只检测 WGC 页面是否可访问，不再强行解析结构。"""
    url = "https://www.gold.org/goldhub/data/gold-reserves-by-country"
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return "📒【央行储备】WGC 页面可访问，后续可在浏览器中手动查看最新央行购金趋势（脚本暂不做细致统计）。"
    except Exception as e:
        return f"📒【央行储备】WGC 页面当前访问异常，暂不使用该信号。\n原因：{e}"


# ======================
# 2. GLD ETF 持仓：当前 + 日变动 + 近5日
# ======================

def fetch_gld() -> str:
    """
    使用 SPDR 官方历史数据：
    https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv

    输出：
    - 最新持仓（吨）
    - 日变动
    - 近 5 日累积变动
    """
    url = "https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv"

    try:
        df = pd.read_csv(url)

        if "Date" not in df.columns:
            raise ValueError("GLD CSV 中不含 Date 列")

        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date")

        # 找 Tonnes 列并转成数值
        tonne_cols = [c for c in df.columns if "Tonne" in c or "Tonnes" in c]
        if not tonne_cols:
            raise ValueError(f"未找到 Tonnes 列，现有列：{list(df.columns)}")
        t_col = tonne_cols[0]
        df[t_col] = pd.to_numeric(df[t_col], errors="coerce")

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

        lines = [
            "📊【GLD ETF 持仓】全球最大黄金 ETF",
            f"- 最新日期：{today_date}",
            f"- 当前持仓：{today_tonnes:.2f} 吨",
            f"- 日变动：{day_change:+.2f} 吨",
            f"- 近 5 日累积：{five_change:+.2f} 吨",
        ]
        return "\n".join(lines)

    except Exception as e:
        return f"📊【GLD ETF 持仓】数据抓取失败，已跳过。\n原因：{e}"


# ======================
# 3. IAU ETF：价格 + 日变动 + 近5日价格趋势
# ======================

def fetch_iau() -> str:
    """
    使用 Stooq 免费日线数据：
    https://stooq.com/q/d/l/?s=iau.us&i=d

    输出：
    - 最新收盘价
    - 日价格变动（点数 + 百分比）
    - 近 5 日累积价格变动
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

        lines = [
            "📈【IAU ETF 价格】美国第二大黄金 ETF（价格参考）",
            f"- 最新日期：{today_date}",
            f"- 收盘价：{today_close:.2f} 美元",
            f"- 日变动：{day_change:+.2f} 美元（{day_pct:+.2f}%）",
            f"- 近 5 日：{five_change:+.2f} 美元（{five_pct:+.2f}%）",
        ]
        return "\n".join(lines)

    except Exception as e:
        return f"📈【IAU ETF 价格】数据抓取失败，已跳过。\n原因：{e}"


# ======================
# 4. CFTC COT：先只做状态提示
# ======================

def fetch_cot() -> str:
    """
    目前 CFTC 报告结构经常变动，这里只检测官网文件是否能访问，
    真正的净多头解析以后单独做 V2，不影响主报告稳定性。
    """
    url = "https://www.cftc.gov/dea/newcot/f_disagg.txt"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return "📑【CFTC COT】最新 disaggregated 报告可访问，黄金期货资金方向可在官网手动查看（脚本暂不解析，避免结构变动导致报错）。"
    except Exception as e:
        return f"📑【CFTC COT】报告暂时无法访问，暂不使用该信号。\n原因：{e}"


# ======================
# 主执行函数
# ======================

def run() -> None:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    parts = [f"🕒 黄金宏观数据库自动更新（UTC 日期：{today})", ""]

    parts.append(fetch_wgc())
    parts.append("")
    parts.append(fetch_gld())
    parts.append("")
    parts.append(fetch_iau())
    parts.append("")
    parts.append(fetch_cot())

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
