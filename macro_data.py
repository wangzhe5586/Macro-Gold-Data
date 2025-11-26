import os
import re
import time
from datetime import datetime
from io import BytesIO

import requests
import pandas as pd
from bs4 import BeautifulSoup


# =========================
# Telegram 基础函数
# =========================

TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")


def tg_send(text):
    if not TOKEN or not CHAT_ID:
        print("【未配置 TG】:\n", text)
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})


# =========================
# 1. WGC（HTML解析，不依赖 lxml）
# =========================

def fetch_wgc():
    url = "https://www.gold.org/goldhub/data/gold-reserves-by-country"

    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # 找所有table
        tables = soup.find_all("table")
        if not tables:
            return "📒【央行储备】未找到数据表格（结构变动）"

        # 优先找包含“Country”的表头
        target_df = None
        for table in tables:
            df = pd.read_html(str(table))[0]
            cols = [str(c).lower() for c in df.columns]
            if any("country" in c for c in cols):
                target_df = df
                break

        if target_df is None:
            return "📒【央行储备】未找到国家数据表（结构变动）"

        df = target_df.copy()

        # 数值列处理
        for col in df.columns[1:]:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(",", "")
                .str.replace("–", "-")
                .str.replace("—", "-")
                .str.replace("\u2212", "-")
            )
            df[col] = pd.to_numeric(df[col], errors="ignore")

        # 找出可以计算月度变化的数值列
        num_cols = [c for c in df.columns[1:] if pd.to_numeric(df[c], errors="coerce").notna().sum() > 5]

        if len(num_cols) < 2:
            return "📒【央行储备】表结构正常，但不足两列可对比"

        prev_col, cur_col = num_cols[-2], num_cols[-1]
        df["Change"] = pd.to_numeric(df[cur_col], errors="coerce") - pd.to_numeric(df[prev_col], errors="coerce")
        df["abs"] = df["Change"].abs()
        top5 = df.sort_values("abs", ascending=False).head(5)

        lines = [
            "📒【央行储备（月度TOP5）】",
            f"- 对比列：{prev_col} → {cur_col}",
        ]

        for _, row in top5.iterrows():
            lines.append(f"- {row[df.columns[0]]}: {row['Change']:+.1f} 吨")

        return "\n".join(lines)

    except Exception as e:
        return f"📒【央行储备】抓取失败：{e}"


# =========================
# GLD（正常）
# =========================

def fetch_gld():
    try:
        url = "https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv"
        df = pd.read_csv(url)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date")

        t_col = [c for c in df.columns if "Tonne" in c][0]

        last5 = df.tail(5)
        today = last5.iloc[-1]
        prev = last5.iloc[-2]
        first = last5.iloc[0]

        today_t = today[t_col]
        prev_t = prev[t_col]
        first_t = first[t_col]

        day_change = today_t - prev_t
        five_change = today_t - first_t

        return (
            "📊【GLD ETF 持仓】全球最大黄金 ETF\n"
            f"- 最新日期：{today['Date'].strftime('%Y-%m-%d')}\n"
            f"- 当前持仓：{today_t:.2f} 吨\n"
            f"- 日变动：{day_change:+.2f} 吨\n"
            f"- 近5日：{five_change:+.2f} 吨"
        )

    except Exception as e:
        return f"📊【GLD】失败：{e}"


# =========================
# IAU（正常）
# =========================

def fetch_iau():
    try:
        url = "https://stooq.com/q/d/l/?s=iau.us&i=d"
        df = pd.read_csv(url)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date")

        last5 = df.tail(5)
        today = last5.iloc[-1]
        prev = last5.iloc[-2]
        first = last5.iloc[0]

        today_p = today["Close"]
        prev_p = prev["Close"]
        first_p = first["Close"]

        day = today_p - prev_p
        day_pct = day / prev_p * 100

        five = today_p - first_p
        five_pct = five / first_p * 100

        return (
            "📈【IAU ETF 价格】美国第二大黄金ETF\n"
            f"- 最新日期：{today['Date'].strftime('%Y-%m-%d')}\n"
            f"- 收盘价：{today_p:.2f}\n"
            f"- 日变动：{day:+.2f} ({day_pct:+.2f}%)\n"
            f"- 近5日：{five:+.2f} ({five_pct:+.2f}%)"
        )

    except Exception as e:
        return f"📈【IAU】失败：{e}"


# =========================
# 4. CFTC COT（兼容不同列名）
# =========================

def fetch_cot():
    url = "https://www.cftc.gov/dea/newcot/f_disagg.txt"

    try:
        df = pd.read_csv(url)

        # 动态识别合约名列
        name_col = None
        for c in df.columns:
            if "Market" in c and "Exchange" in c:
                name_col = c
                break

        if not name_col:
            return "📑【CFTC COT】文件解析成功，但未识别到合约名列（结构变动）"

        gold_df = df[df[name_col].astype(str).str.contains("GOLD", case=False, na=False)]
        if gold_df.empty:
            return "📑【CFTC COT】无黄金合约行（结构变动）"

        row = gold_df.iloc[-1]

        # 日期解析
        d = str(row.get("As_of_Date_In_Form_YYMMDD", ""))
        try:
            d_int = int(float(d))
            date = datetime.strptime(str(d_int), "%y%m%d").strftime("%Y-%m-%d")
        except:
            date = d

        # 动态识别 Managed Money 列
        long = None
        for c in df.columns:
            if "M_Money_Long" in c or "Money_Mgt_Long" in c:
                try:
                    long = float(row[c])
                    break
                except:
                    pass

        short = None
        for c in df.columns:
            if "M_Money_Short" in c or "Money_Mgt_Short" in c:
                try:
                    short = float(row[c])
                    break
                except:
                    pass

        if long is None or short is None:
            return "📑【CFTC COT】无法解析多空头寸（字段名变动）"

        net = long - short

        return (
            "📑【CFTC COT（黄金期货）】\n"
            f"- 报告周：{date}\n"
            f"- Managed Money 净多头：{net:,.0f} 手"
        )

    except Exception as e:
        return f"📑【CFTC COT】抓取失败：{e}"


# =========================
# Run
# =========================

def run():
    today = datetime.utcnow().strftime("%Y-%m-%d")

    msg = (
        f"🕒 黄金宏观数据库自动更新（UTC：{today})\n\n"
        f"{fetch_wgc()}\n\n"
        f"{fetch_gld()}\n\n"
        f"{fetch_iau()}\n\n"
        f"{fetch_cot()}"
    )

    print(msg)
    tg_send(msg)


if __name__ == "__main__":
    run()
