import pandas as pd
import requests
from io import BytesIO
from datetime import datetime
import os

TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")

def tg_send(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def fetch_wgc():
    url = "https://www.gold.org/download-file?filename=gold-reserves.xlsx"
    df = pd.read_excel(BytesIO(requests.get(url).content))
    latest = df.iloc[-1]
    return f"WGC 央行储备最新（月度）\n{latest.to_string()}"

def fetch_gld():
    url = "https://www.spdrgoldshares.com/assets/daily-holdings/USD/fund-holdings-usd.csv"
    df = pd.read_csv(url, skiprows=2)
    last = df.iloc[-1]
    return f"GLD 最新持仓: {last['Tonnes']} 吨"

def fetch_iau():
    url = "https://www.ishares.com/us/products/239561/ishares-gold-trust-fund/1467271812596.ajax?fileType=csv&fileName=IAU_holdings&dataType=fund"
    df = pd.read_csv(url)
    total = df['Total Ounces'].sum() / 32150  # 转换为吨
    return f"IAU 总持仓: {total:.2f} 吨"

def run():
    msg = f"📊 黄金宏观数据库更新 ({datetime.now():%Y-%m-%d})\n\n"
    msg += fetch_wgc() + "\n\n"
    msg += fetch_gld() + "\n"
    msg += fetch_iau() + "\n"
    tg_send(msg)

if __name__ == "__main__":
    run()
