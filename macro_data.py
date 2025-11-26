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
# 1. WGC 央行黄金储备（月度变动 TOP5）
# ======================

def fetch_wgc() -> str:
    """
    从 WGC 网页读取 HTML 表格，自动找包含国家 + 多列数值的表，
    用最后两列数值作为“近两个月储备”，计算差值，输出 TOP5 变化国家。
    """
    base = "https://www.gold.org"
    page_url = base + "/goldhub/data/gold-reserves-by-country"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        page = requests.get(page_url, headers=headers, timeout=30)
        page.raise_for_status()
        html = page.text

        # 解析页面中的所有表格
        tables = pd.read_html(html)
        if not tables:
            return "📒【央行储备】WGC 页面无可用表格。"

        target = None
        for t in tables:
            cols_lower = [str(c).lower() for c in t.columns]
            if any("country" in c for c in cols_lower):
                target = t
                break

        if target is None:
            return "📒【央行储备】未找到包含国家列的表格，可能是页面结构变动。"

        df = target.copy()

        # 第一列视为国家/地区
        country_col = df.columns[0]

        # 后续列尝试转为数值，选出数值列
        df_num = df.copy()
        for col in df_num.columns[1:]:
            df_num[col] = (
                df_num[col]
                .astype(str)
                .str.replace(",", "")
                .str.replace("\u2212", "-")  # 负号
                .str.replace("–", "")
                .str.replace("—", "")
            )
            df_num[col] = pd.to_numeric(df_num[col], errors="coerce")

        num_cols = [
            c for c in df_num.columns[1:]
            if df_num[c].notna().sum() > 10  # 至少有一些有效数字
        ]
        if len(num_cols) < 2:
            return "📒【央行储备】未找到足够的数值列用于计算月度变化。"

        # 取最后两列作为“上月 / 本月”
        prev_col = num_cols[-2]
        cur_col = num_cols[-1]

        df_num["Change"] = df_num[cur_col] - df_num[prev_col]
        tmp = df_num[[country_col, "Change"]].dropna().copy()
        tmp["abs_change"] = tmp["Change"].abs()
        top5 = tmp.sort_values("abs_change", ascending=False).head(5)

        lines = [
            "📒【央行储备（月度变动 TOP5）】",
            f"- 对比列：{prev_col} → {cur_col}（单位大致为吨）",
        ]
        for _, row in top5.iterrows():
            name = str(row[country_col])
            change = row["Change"]
            lines.append(f"- {name}: {change:+.1f} 吨")

        return "\n".join(lines)

    except Exception as e:
        return f"📒【央行储备】WGC 数据暂时无法解析月度变化，已跳过。\n原因：{e}"


# ======================
# 2. GLD ETF 持仓：日变动 + 近 5 日趋势
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

        tonne_cols = [c for c in df.columns if "Tonne" in c or "Tonnes" in c]
        if not tonne_cols:
            raise ValueError(f"未找到 Tonnes 列，现有列：{list(df.columns)}")
        t_col = tonne_cols[0]

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
# 4. CFTC COT：黄金期货 Managed Money 净多头
# ======================

def fetch_cot() -> str:
    """
    使用 CFTC disaggregated futures-only 周度数据：
    https://www.cftc.gov/dea/newcot/f_disagg.txt

    目标：
    - 找到黄金合约行（包含 'GOLD' 的市场名称）
    - 读取 Managed Money Long / Short，计算净多头
    - 尝试读取本周变化（如果字段存在）
    """
    url = "https://www.cftc.gov/dea/newcot/f_disagg.txt"

    try:
        df = pd.read_csv(url)

        if "Market_and_Exchange_Names" not in df.columns:
            raise ValueError("COT 文件中不含 Market_and_Exchange_Names 列")

        gold_df = df[
            df["Market_and_Exchange_Names"].str.contains("GOLD", case=False, na=False)
        ]
        if gold_df.empty:
            return "📑【CFTC COT】未在最新 disaggregated 报告中找到黄金合约，已跳过。"

        last = gold_df.iloc[-1]

        # 报告日期
        date_val = str(last.get("As_of_Date_In_Form_YYMMDD", ""))
        try:
            date_val_int = int(float(date_val))
            report_date = datetime.strptime(str(date_val_int), "%y%m%d").strftime(
                "%Y-%m-%d"
            )
        except Exception:
            report_date = date_val

        def get_float(series, name_list):
            """尝试从若干候选列名中取出第一个能成功转成 float 的值"""
            for name in name_list:
                if name in series.index:
                    try:
                        return float(series[name])
                    except Exception:
                        continue
            return None

        mm_long = get_float(
            last,
            [
                "M_Money_Long_All",
                "M_Money_Long_All_Combin",
                "Money_Mgt_Long_All",
            ],
        )
        mm_short = get_float(
            last,
            [
                "M_Money_Short_All",
                "M_Money_Short_All_Combin",
                "Money_Mgt_Short_All",
            ],
        )

        mm_long_chg = get_float(
            last,
            [
                "M_Money_Long_All_Change",
                "M_Money_Long_All_Chg",
                "Money_Mgt_Long_All_Change",
            ],
        )
        mm_short_chg = get_float(
            last,
            [
                "M_Money_Short_All_Change",
                "M_Money_Short_All_Chg",
                "Money_Mgt_Short_All_Change",
            ],
        )

        if mm_long is None or mm_short is None:
            return "📑【CFTC COT】成功获取文件，但未能解析 Managed Money 多空头寸。"

        mm_net = mm_long - mm_short
        lines = [
            "📑【CFTC COT（黄金期货）】",
            f"- 报告周：{report_date}",
            f"- Managed Money 净多头：{mm_net:,.0f} 手",
        ]

        if mm_long_chg is not None and mm_short_chg is not None:
            mm_net_chg = mm_long_chg - mm_short_chg
            lines.append(f"- 本周变化：{mm_net_chg:+,.0f} 手")

        return "\n".join(lines)

    except Exception as e:
        return f"📑【CFTC COT】数据抓取失败，已跳过。\n原因：{e}"


# ======================
# 主执行函数
# ======================

def run() -> None:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    parts = [f"🕒 黄金宏观数据库自动更新（UTC 日期：{today})", ""]

    # 央行储备（月度 TOP5）
    parts.append(fetch_wgc())
    parts.append("")

    # GLD：持仓 + 日变动 + 近 5 日
    parts.append(fetch_gld())
    parts.append("")

    # IAU：价格 + 日变动 + 近 5 日
    parts.append(fetch_iau())
    parts.append("")

    # CFTC COT：黄金期货 Managed Money
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
