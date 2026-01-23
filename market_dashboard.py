import streamlit as st
import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime
import numpy as np

# ==========================================
# 1. 系統設定
# ==========================================
st.set_page_config(page_title="全球金融戰情室 (AI旗艦版)", layout="wide")
st.title("🌐 全球金融戰情室 (AI旗艦版)")

# 顯示台灣時間
tw_tz = pytz.timezone('Asia/Taipei')
current_time = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"🕒 最後更新時間 (台灣): {current_time}")

# ==========================================
# 2. 核心資產名單定義 (確保下載與顯示同步)
# ==========================================

# A. Mag 7 巨頭與 AI 核心
mag_7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "AVGO"]

# B. 台股高價/千金股觀察池 (擴大版)
high_price_tw = [
    "5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "5269.TWO", 
    "3443.TW", "2454.TW", "2059.TW", "3533.TW", "3131.TWO", "3653.TW", 
    "3293.TWO", "6409.TW", "8454.TW", "6643.TW", "6415.TW", "8299.TWO", 
    "8464.TW", "1590.TW", "2327.TW", "2330.TW", "3034.TW", "4966.TWO",
    "6641.TW", "6805.TW", "9910.TW", "2059.TW", "3680.TW", "6679.TW"
]

# C. 風險指標與商品期貨
risk_assets = ["^VIX", "BTC-USD", "GC=F", "HG=F", "CL=F", "JPY=X", "DX-Y.NYB", "^TNX", "ZQ=F"]

# D. 市場與產業基準
market_indices = ["^IXIC", "SMH", "SOXX", "^SOX", "^TWII", "^TWO", "00733.TW", "SPY"]

# 合併所有需要下載的代號
all_needed_tickers = list(set(mag_7 + high_price_tw + risk_assets + market_indices))

# 中英文名稱映射表
name_map = {
    "NVDA": "輝達", "GOOGL": "Google", "MSFT": "微軟", "AAPL": "蘋果", "AMZN": "亞馬遜", "META": "Meta", "TSLA": "特斯拉", "AVGO": "博通",
    "^IXIC": "納斯達克", "SMH": "半導體ETF", "^SOX": "費半指數", "^TWII": "台灣加權", "^TWO": "櫃買指數",
    "SOXX": "費半 ETF", "00733.TW": "富邦中小", "DX-Y.NYB": "美元指數", "^TNX": "美債10年",
    "JPY=X": "美元/日圓", "ZQ=F": "聯邦利率期貨", "SPY": "標普 500", "2330.TW": "台積電", "^VIX": "VIX 恐慌",
    "BTC-USD": "比特幣", "GC=F": "黃金", "HG=F": "期貨銅", "CL=F": "原油"
}

# ==========================================
# 3. 核心運算引擎
# ==========================================

@st.cache_data(ttl=3600)
def fetch_data_cached(tickers, period="5y"):
    try:
        data = yf.download(tickers, period=period, progress=False)
        return data
    except:
        return pd.DataFrame()

cached_data = fetch_data_cached(all_needed_tickers)

def get_processed_df(ticker_list, cached_df):
    results = []
    data = cached_df['Close'] if 'Close' in cached_df.columns else cached_df
    for ticker in ticker_list:
        try:
            if ticker in data.columns:
                series = data[ticker].fillna(method='ffill').dropna()
                if len(series) > 30: # 至少有基本數據
                    price = series.iloc[-1]
                    ma20 = series.rolling(20).mean().iloc[-1]
                    bias = (price - ma20) / ma20 * 100
                    trend = "🔴強勢" if bias > 0 else "🟢弱勢"
                    
                    # Z-Score 計算 (抓兩年 504 根 K 線)
                    if len(series) >= 504:
                        mean_2y = series.tail(504).mean()
                        std_2y = series.tail(504).std()
                        z_score = (price - mean_2y) / std_2y if std_2y != 0 else 0
                    else:
                        z_score = 0 # 數據不足不計算
                    
                    results.append({
                        "代號": ticker, 
                        "資產名稱": name_map.get(ticker, ticker), 
                        "趨勢": trend, 
                        "現價": round(price, 2), 
                        "乖離率": round(bias, 2), 
                        "Z-Score": round(z_score, 2)
                    })
        except: pass
    return pd.DataFrame(results)

# ==========================================
# 4. 介面分頁邏輯
# ==========================================
tabs = st.tabs(["💀 AI 資金雷達", "🇹🇼 台股戰略", "🚀 風險雷達", "💎 半導體", "📈 趨勢圖", "⚖️ 法人估值"])
tab_ai, tab_tw, tab_risk, tab_semi, tab_chart, tab_valuation = tabs

# --- Tab 1: AI 資金雷達 ---
with tab_ai:
    st.subheader("💀 AI 資金掃描雷達")
    df_ai = get_processed_df(mag_7 + ["^IXIC", "SMH"], cached_data)
    if not df_ai.empty:
        avg_bias = df_ai['乖離率'].mean()
        avg_z = df_ai['Z-Score'].mean()
        c1, c2 = st.columns([1, 2])
        with c1:
            if avg_bias > 0: st.error(f"### 🔴 資金湧入\n平均離差: {round(avg_bias, 2)}%")
            else: st.success(f"### 🟢 資金退潮\n平均離差: {round(avg_bias, 2)}%")
            st.metric("資金擁擠度 (Z-Score)", round(avg_z, 2))
        with c2:
            st.dataframe(df_ai[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("乖離率", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 2: 台股戰略 (排版修正) ---
with tab_tw:
    st.subheader("🇹🇼 台股戰略指標")
    df_tw_lead = get_processed_df(["SOXX", "00733.TW", "DX-Y.NYB", "^TNX"], cached_data)
    if not df_tw_lead.empty:
        m1, m2, m3, m4 = st.columns(4)
        def show_metric(col, ticker, name, inverse=False):
            row = df_tw_lead[df_tw_lead['代號']==ticker]
            if not row.empty:
                col.metric(name, f"{row['現價'].values[0]}", f"{row['乖離率'].values[0]}%", 
                           delta_color="normal" if not inverse else "inverse")
        show_metric(m1, "SOXX", "費半 ETF")
        show_metric(m2, "00733.TW", "富邦中小")
        show_metric(m3, "DX-Y.NYB", "美元指數", inverse=True)
        show_metric(m4, "^TNX", "美債10Y", inverse=True)

    st.divider()
    st.subheader("👑 千金股與高價股觀察池")
    df_high = get_processed_df(high_price_tw, cached_data)
    if not df_high.empty:
        # 動能過濾：現價 > 800
        df_king = df_high[df_high['現價'] >= 800].copy()
        k1, k2, k3 = st.columns(3)
        k1.metric("高價監控檔數", f"{len(df_king)} 檔")
        k2.metric("平均 Z-Score", round(df_king['Z-Score'].mean(), 2))
        k3.metric("紅燈佔比", f"{len(df_king[df_king['乖離率']>0])} 檔")
        st.dataframe(df_king[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("現價", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 3: 風險雷達 (品項全補完) ---
with tab_risk:
    st.subheader("🚀 市場風險雷達 (流動性與商品)")
    risk_raw = cached_data['Close'] if 'Close' in cached_data.columns else cached_data
    
    # 頂部流動性指標
    c1, c2 = st.columns(2)
    with c1:
        if 'JPY=X' in risk_raw.columns:
            jpy = risk_raw['JPY=X'].dropna()
            p, ma60 = jpy.iloc[-1], jpy.rolling(60).mean().iloc[-1]
            st.metric("日圓匯率 (JPY=X)", f"{round(p, 2)}", "🔴 安全" if p > ma60 else "🟢 警戒", delta_color="normal" if p > ma60 else "inverse")
    with c2:
        if 'ZQ=F' in risk_raw.columns:
            rate = round(100 - risk_raw['ZQ=F'].dropna().iloc[-1], 2)
            st.metric("短端利率 (ZQ=F)", f"{rate}%", "🔴 穩定" if rate < 5.2 else "🟢 緊繃", delta_color="normal" if rate < 5.2 else "inverse")
    
    st.divider()
    # 修正：補全所有風險資產 Z-Score
    st.markdown("##### 🔍 全球風險資產 Z-Score 掃描")
    full_risk_list = ["^VIX", "BTC-USD", "GC=F", "HG=F", "CL=F", "DX-Y.NYB"]
    df_risk_z = get_processed_df(full_risk_list, cached_data)
    st.dataframe(df_risk_z[["資產名稱", "Z-Score", "趨勢", "現價"]], hide_index=True, use_container_width=True)

# --- Tab 4: 半導體相對強度 (巨頭全歸隊) ---
with tab_semi:
    st.subheader("💎 半導體與科技巨頭相對強度 (vs SPY)")
    if 'SPY' in risk_raw.columns:
        bench = risk_raw['SPY'].dropna()
        bench_ret = (bench.iloc[-1] - bench.iloc[-60]) / bench.iloc[-60]
        # 修正：名單包含 Mag 7 + 核心半導體
        compare_list = ["SOXX", "2330.TW"] + mag_7
        res = []
        for t in compare_list:
            if t in risk_raw.columns:
                tgt = risk_raw[t].dropna()
                if len(tgt) > 60:
                    ret = (tgt.iloc[-1]-tgt.iloc[-60])/tgt.iloc[-60]
                    rs = (1 + ret) / (1 + bench_ret)
                    clr = "background-color: rgba(255, 50, 50, 0.15)" if rs > 1 else "background-color: rgba(50, 255, 50, 0.15)"
                    res.append({"名稱": name_map.get(t,t), "強度(RS)": round(rs,4), "_c": clr})
        df_s = pd.DataFrame(res).sort_values("強度(RS)", ascending=False)
        st.dataframe(df_s.style.apply(lambda x: [x['_c']]*len(x), axis=1), column_config={"_c":None}, hide_index=True, use_container_width=True)

# --- 其餘分頁 (趨勢、估值) ---
with tab_chart:
    sel = st.selectbox("選擇監控商品：", all_needed_tickers, format_func=lambda x: f"{name_map.get(x,x)} ({x})")
    if sel: st.line_chart(risk_raw[sel].dropna())

with tab_valuation:
    v_ticker = st.text_input("輸入股票代號 (如 NVDA)", value="2330.TW").upper()
    if v_ticker:
        try:
            info = yf.Ticker(v_ticker).info
            eps, pe, price = info.get('trailingEps', 0), info.get('trailingPE', 0), info.get('currentPrice', 0)
            st.write(f"### {info.get('longName', v_ticker)} | 現價: ${price}")
            g = st.slider("預估成長率 (%)", 1, 50, 15)
            peg = pe/g if g else 0
            st.metric("PEG 估值", round(peg, 2), "🟢 低估" if peg < 1.2 else "🔴 高估", delta_color="inverse")
        except: st.error("代號無效或基本面數據不足")
