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

tw_tz = pytz.timezone('Asia/Taipei')
current_time = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"🕒 最後更新時間 (台灣): {current_time}")

# ==========================================
# 📖 說明手冊：操盤判讀邏輯 & 交易心法
# ==========================================
with st.expander("📖 查看：操盤判讀邏輯 & 交易心法 (點擊展開)", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        ### 🔍 數據判讀 (🔴多/強 | 🟢空/弱):
        1. **AI 資金雷達**：監控 AI 巨頭。平均離差 < 0 且亮綠燈代表資金退潮。
        2. **台股戰略**：費半與中小指標皆亮紅燈代表內外資同步做多。
        3. **風險雷達**：日圓跌破季線(60MA) = **Carry Trade 平倉警報**。
        4. **Z-Score**：> +1.5 代表過度擁擠；< -1.5 代表過度悲觀。
        """)
    with c2:
        st.markdown("""
        ### 🛡️ 2026 交易心法:
        * **部位控管**：當流動性指標亮綠燈時，持倉水位應降至 **3~5 成**。
        * **拒絕 FOMO**：暴漲往往是機構倒貨，觀察「成交量」而非單看價格。
        * **千金股效應**：高價股是內資大戶的「信心溫度計」，通常領先反轉。
        """)

# ==========================================
# 2. 核心運算引擎 (Period="5y" 確保穩定性)
# ==========================================

@st.cache_data(ttl=3600)
def fetch_data_cached(tickers, period="5y"):
    try:
        data = yf.download(tickers, period=period, progress=False)
        return data
    except:
        return pd.DataFrame()

# 中英文名稱映射
name_map = {
    "NVDA": "輝達", "GOOGL": "Google", "MSFT": "微軟", "AAPL": "蘋果", "AMZN": "亞馬遜", "META": "Meta", "TSLA": "特斯拉", "AVGO": "博通",
    "^IXIC": "納斯達克", "SMH": "半導體ETF", "^SOX": "費半指數", "^TWII": "台灣加權", "^TWO": "櫃買指數",
    "SOXX": "費半 ETF", "00733.TW": "富邦中小", "DX-Y.NYB": "美元指數", "^TNX": "美債10年",
    "JPY=X": "美元/日圓", "ZQ=F": "聯邦利率期貨", "SPY": "標普 500", "2330.TW": "台積電", "^VIX": "VIX 恐慌",
    "BTC-USD": "比特幣", "GC=F": "黃金", "HG=F": "期貨銅", "CL=F": "原油"
}

high_price_tw = [
    "5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "5269.TWO", 
    "3443.TW", "2454.TW", "2059.TW", "3533.TW", "3131.TWO", "3653.TW", 
    "3293.TWO", "6409.TW", "8454.TW", "6643.TW", "6415.TW", "8299.TWO", 
    "8464.TW", "1590.TW", "2327.TW", "2330.TW", "3034.TW", "4966.TWO"
]

all_tickers = list(set(list(name_map.keys()) + high_price_tw + ["ZQ=F", "SPY"]))
cached_data = fetch_data_cached(all_tickers)

def get_processed_df(ticker_list, cached_df):
    results = []
    data = cached_df['Close'] if 'Close' in cached_df.columns else cached_df
    for ticker in ticker_list:
        try:
            if ticker in data.columns:
                series = data[ticker].fillna(method='ffill').dropna()
                if not series.empty:
                    price = series.iloc[-1]
                    ma20 = series.rolling(20).mean().iloc[-1]
                    bias = (price - ma20) / ma20 * 100
                    trend = "🔴強勢" if bias > 0 else "🟢弱勢"
                    
                    # 穩健版 Z-Score (若不足 504 天則用最大可用天數)
                    lookback = min(len(series), 504)
                    window_data = series.tail(lookback)
                    z_score = (price - window_data.mean()) / window_data.std() if window_data.std() != 0 else 0
                    
                    results.append({
                        "代號": ticker, "資產名稱": name_map.get(ticker, ticker), 
                        "趨勢": trend, "現價": round(price, 2), 
                        "乖離率": round(bias, 2), "Z-Score": round(z_score, 2)
                    })
        except: pass
    return pd.DataFrame(results)

# ==========================================
# 3. 分頁邏輯
# ==========================================
tabs = st.tabs(["💀 AI 資金", "🇹🇼 台股戰略", "🚀 風險雷達", "💎 半導體", "📈 趨勢圖", "⚖️ 法人估值"])
tab_ai, tab_tw, tab_risk, tab_semi, tab_chart, tab_valuation = tabs

# --- Tab 1: AI 資金 ---
with tab_ai:
    df_ai = get_processed_df(["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "^IXIC", "SMH"], cached_data)
    if not df_ai.empty:
        avg_bias = df_ai['乖離率'].mean()
        c1, c2 = st.columns([1, 2])
        with c1:
            if avg_bias > 0: st.error(f"### 🔴 資金湧入\n平均離差: {round(avg_bias, 2)}%")
            else: st.success(f"### 🟢 資金退潮\n平均離差: {round(avg_bias, 2)}%")
            st.metric("整體擁擠度 (Z-Score)", round(df_ai['Z-Score'].mean(), 2))
        with c2:
            st.dataframe(df_ai[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("乖離率", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 2: 台股戰略 (恢復整體數據彙整) ---
with tab_tw:
    st.subheader("🇹🇼 台股戰略指標")
    df_tw_lead = get_processed_df(["SOXX", "00733.TW", "DX-Y.NYB", "^TNX"], cached_data)
    if not df_tw_lead.empty:
        m1, m2, m3, m4 = st.columns(4)
        def show_metric(col, ticker, name, inverse=False):
            row = df_tw_lead[df_tw_lead['代號']==ticker]
            if not row.empty:
                col.metric(name, f"{row['現價'].values[0]}", f"{row['乖離率'].values[0]}%", delta_color="normal" if not inverse else "inverse")
        show_metric(m1, "SOXX", "費半 ETF")
        show_metric(m2, "00733.TW", "富邦中小")
        show_metric(m3, "DX-Y.NYB", "美元指數", inverse=True)
        show_metric(m4, "^TNX", "美債10Y", inverse=True)

    st.divider()
    st.subheader("👑 千金股與高價股觀察池")
    df_high = get_processed_df(high_price_tw, cached_data)
    if not df_high.empty:
        df_king = df_high[df_high['現價']>=800].copy()
        
        # --- 恢復整體統計數據 (Summary Metrics) ---
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("高價監控檔數", f"{len(df_king)} 檔")
        s2.metric("強勢家數 (🔴)", f"{len(df_king[df_king['乖離率']>0])} 檔")
        s3.metric("強勢佔比", f"{int(len(df_king[df_king['乖離率']>0])/len(df_king)*100)}%")
        s4.metric("族群平均 Z-Score", round(df_king['Z-Score'].mean(), 2))
        
        st.dataframe(df_king[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("現價", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 3: 風險雷達 ---
with tab_risk:
    risk_raw = cached_data['Close'] if 'Close' in cached_data.columns else cached_data
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
    st.markdown("##### 🔍 其他風險資產 Z-Score 掃描")
    df_risk_z = get_processed_df(["^VIX", "BTC-USD", "GC=F", "HG=F", "CL=F", "DX-Y.NYB"], cached_data)
    st.dataframe(df_risk_z[["資產名稱", "Z-Score", "趨勢", "現價"]], hide_index=True, use_container_width=True)

# --- Tab 4: 半導體相對強度 ---
with tab_semi:
    st.subheader("💎 巨頭與半導體強度 (vs SPY)")
    if 'SPY' in risk_raw.columns:
        bench = risk_raw['SPY'].dropna()
        bench_ret = (bench.iloc[-1] - bench.iloc[-60]) / bench.iloc[-60]
        semi_list = ["SOXX", "2330.TW", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AVGO"]
        res = []
        for t in semi_list:
            if t in risk_raw.columns:
                tgt = risk_raw[t].dropna()
                rs = (1 + (tgt.iloc[-1]-tgt.iloc[-60])/tgt.iloc[-60]) / (1+bench_ret)
                clr = "background-color: rgba(255, 50, 50, 0.15)" if rs > 1 else "background-color: rgba(50, 255, 50, 0.15)"
                res.append({"名稱": name_map.get(t,t), "強度(RS)": round(rs,4), "_c": clr})
        st.dataframe(pd.DataFrame(res).sort_values("強度(RS)", ascending=False).style.apply(lambda x: [x['_c']]*len(x), axis=1), column_config={"_c":None}, hide_index=True, use_container_width=True)

# --- 其餘分頁保持穩定 ---
with tab_chart:
    sel = st.selectbox("選擇監控商品：", all_tickers, format_func=lambda x: f"{name_map.get(x,x)} ({x})")
    if sel: st.line_chart(risk_raw[sel].dropna())

with tab_valuation:
    v_ticker = st.text_input("輸入股票代號", value="2330.TW").upper()
    if v_ticker:
        try:
            info = yf.Ticker(v_ticker).info
            st.write(f"### {info.get('longName', v_ticker)} | 現價: ${info.get('currentPrice')}")
            g = st.slider("預估成長率 (%)", 1, 50, 15)
            peg = info.get('trailingPE', 0)/g if g else 0
            st.metric("PEG 估值", round(peg, 2), "🟢 低估" if peg < 1.2 else "🔴 高估", delta_color="inverse")
        except: st.error("數據不足")
