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
# 📖 新手指南
# ==========================================
with st.expander("📖 查看：操盤判讀邏輯 & 交易心法 (點擊展開)"):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        ### 🔍 數據判讀 (🔴多/強 | 🟢空/弱):
        1. **AI 資金雷達**：監控 AI 七巨頭。平均離差 < 0 代表資金退潮。
        2. **台股戰略**：四大指標亮紅燈 = 多方控盤。
        3. **風險雷達**：日圓跌破季線(60MA) = **平倉警報**。
        4. **Z-Score**：> +1.5 過度擁擠；< -1.5 過度悲觀。
        """)
    with c2:
        st.markdown("""
        ### 🛡️ 交易心法:
        * **部位控管**：風險指標轉弱時，持倉降至 3~5 成。
        * **千金股效應**：高價股是內資大戶的「信心溫度計」，領先大盤反轉。
        """)

# ==========================================
# 2. 核心運算引擎 (關鍵修正：period="5y")
# ==========================================

@st.cache_data(ttl=3600)
def fetch_data_cached(tickers, period="5y"): # 抓取 5 年數據以確保 Z-Score 計算穩定
    try:
        data = yf.download(tickers, period=period, progress=False)
        return data
    except:
        return pd.DataFrame()

# 建立中英文對照表
name_map = {
    "NVDA": "輝達", "GOOG": "Google", "MSFT": "微軟", "AAPL": "蘋果", "AMZN": "亞馬遜", "META": "Meta", "TSLA": "特斯拉", "AVGO": "博通",
    "^IXIC": "納斯達克", "SMH": "半導體ETF", "^SOX": "費半指數", "^TWII": "台灣加權", "^TWO": "櫃買指數",
    "SOXX": "費半 ETF", "00733.TW": "富邦中小", "DX-Y.NYB": "美元指數", "^TNX": "美債10年",
    "JPY=X": "美元/日圓", "ZQ=F": "聯邦利率期貨", "SPY": "S&P500", "2330.TW": "台積電", "^VIX": "VIX 恐慌"
}

# 擴大後的千金股/高價股觀察名單 (涵蓋台股 800 元以上潛力股)
assets_high_price = [
    "5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "5269.TWO", 
    "3443.TW", "2454.TW", "2059.TW", "3533.TW", "3131.TWO", "3653.TW", 
    "3293.TWO", "6409.TW", "8454.TW", "6643.TW", "6415.TW", "8299.TWO", 
    "8464.TW", "1590.TW", "2327.TW", "2330.TW", "3034.TW", "4966.TWO",
    "6641.TW", "6805.TW", "9910.TW"
]

all_needed_tickers = list(set(
    list(name_map.keys()) + assets_high_price + ["ZQ=F", "^IRX"]
))

cached_data = fetch_data_cached(all_needed_tickers)

# 萬用數據提取與運算
def get_processed_df(ticker_list, cached_df):
    results = []
    data = cached_df['Close'] if 'Close' in cached_df.columns else cached_df
    for ticker in ticker_list:
        try:
            if ticker in data.columns:
                series = data[ticker].dropna()
                if len(series) > 504: # 確保有兩年以上數據
                    price = series.iloc[-1]
                    ma20 = series.rolling(20).mean().iloc[-1]
                    bias = (price - ma20) / ma20 * 100
                    trend = "🔴強勢" if bias > 0 else "🟢弱勢"
                    
                    # 計算 Z-Score (兩年回測)
                    mean_2y = series.tail(504).mean()
                    std_2y = series.tail(504).std()
                    z_score = (price - mean_2y) / std_2y if std_2y != 0 else 0
                    
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
# 3. 分頁邏輯
# ==========================================
tabs = st.tabs(["💀 AI 資金雷達", "🇹🇼 台股戰略", "🚀 風險雷達", "💎 半導體", "📈 趨勢圖", "⚖️ 法人估值"])
tab_ai, tab_tw, tab_risk, tab_semi, tab_chart, tab_valuation = tabs

# --- Tab 1: AI 資金雷達 (修正 Z-Score nan 問題) ---
with tab_ai:
    st.subheader("💀 AI 資金掃描雷達")
    ai_list = ["NVDA", "GOOG", "MSFT", "AAPL", "AMZN", "META", "TSLA", "AVGO", "^IXIC", "SMH"]
    df_ai = get_processed_df(ai_list, cached_data)
    
    if not df_ai.empty:
        avg_bias = df_ai['乖離率'].mean()
        avg_z = df_ai['Z-Score'].mean()
        
        c1, c2 = st.columns([1, 2])
        with c1:
            if avg_bias > 0: st.error(f"### 🔴 資金湧入\n平均離差: {round(avg_bias, 2)}%")
            else: st.success(f"### 🟢 資金退潮\n平均離差: {round(avg_bias, 2)}%")
            
            st.metric("資金擁擠度 (Z-Score)", round(avg_z, 2))
            if avg_z > 1.5: st.warning("⚠️ 籌碼過度擁擠，留意回檔風險")
            elif avg_z < -1.5: st.info("ℹ️ 籌碼過度悲觀，潛在反彈區")
            
        with c2:
            st.dataframe(df_ai[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("乖離率", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 2: 台股戰略 (排版與名單優化) ---
with tab_tw:
    st.subheader("🇹🇼 台股戰略指標")
    
    # 指標列排版
    df_tw_lead = get_processed_df(["SOXX", "00733.TW", "DX-Y.NYB", "^TNX"], cached_data)
    if not df_tw_lead.empty:
        # 使用封閉式卡片顯示四大指標
        m1, m2, m3, m4 = st.columns(4)
        def show_metric(col, ticker, name, inverse=False):
            row = df_tw_lead[df_tw_lead['代號']==ticker]
            if not row.empty:
                val = row['現價'].values[0]
                bias = row['乖離率'].values[0]
                col.metric(name, f"{val}", f"{bias}%", delta_color="normal" if not inverse else "inverse")

        show_metric(m1, "SOXX", "1. 費半 ETF")
        show_metric(m2, "00733.TW", "2. 富邦中小")
        show_metric(m3, "DX-Y.NYB", "3. 美元指數", inverse=True)
        show_metric(m4, "^TNX", "4. 美債10Y", inverse=True)

    st.divider()
    st.subheader("👑 千金股信心溫度計 (高價股群組)")
    
    df_high = get_processed_df(assets_high_price, cached_data)
    if not df_high.empty:
        # 只顯示現價 > 800 的股票，讓清單更精確
        df_king = df_high[df_high['現價'] >= 800].copy()
        
        k1, k2, k3 = st.columns(3)
        k1.metric("高價觀察檔數", f"{len(df_king)} 檔")
        k2.metric("強勢佔比", f"{len(df_king[df_king['乖離率']>0])} 檔", f"{int(len(df_king[df_king['乖離率']>0])/len(df_king)*100)}%")
        k3.metric("平均 Z-Score", round(df_king['Z-Score'].mean(), 2))
        
        st.dataframe(
            df_king[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("現價", ascending=False), 
            hide_index=True, 
            use_container_width=True
        )
    else:
        st.write("數據讀取中...")

# --- Tab 3: 風險雷達 (流動性監控) ---
with tab_risk:
    st.subheader("🚀 市場風險雷達 (流動性)")
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
            st.metric("短端利率期貨 (ZQ=F)", f"{rate}%", "🔴 穩定" if rate < 5.2 else "🟢 緊繃", delta_color="normal" if rate < 5.2 else "inverse")
    
    st.divider()
    st.markdown("##### 🔍 其他風險資產 Z-Score")
    df_risk_z = get_processed_df(["^VIX", "BTC-USD", "GC=F", "HG=F"], cached_data)
    st.dataframe(df_risk_z[["資產名稱", "Z-Score", "趨勢"]], hide_index=True, use_container_width=True)

# --- 其餘分頁保持穩定邏輯 ---
with tab_semi:
    st.subheader("💎 半導體相對強度 (vs SPY)")
    if 'SPY' in risk_raw.columns:
        bench = risk_raw['SPY'].dropna()
        bench_ret = (bench.iloc[-1] - bench.iloc[-60]) / bench.iloc[-60]
        semi_list = ["SOXX", "2330.TW", "NVDA", "AVGO"]
        res = []
        for t in semi_list:
            if t in risk_raw.columns:
                tgt = risk_raw[t].dropna()
                rs = (1 + (tgt.iloc[-1]-tgt.iloc[-60])/tgt.iloc[-60]) / (1+bench_ret)
                clr = "background-color: rgba(255, 50, 50, 0.15)" if rs > 1 else "background-color: rgba(50, 255, 50, 0.15)"
                res.append({"名稱": name_map.get(t,t), "強度(RS)": round(rs,4), "_c": clr})
        st.dataframe(pd.DataFrame(res).sort_values("強度(RS)", ascending=False).style.apply(lambda x: [x['_c']]*len(x), axis=1), column_config={"_c":None}, hide_index=True, use_container_width=True)

with tab_chart:
    all_keys = list(set(all_needed_tickers))
    sel = st.selectbox("選擇監控商品：", all_keys, format_func=lambda x: f"{name_map.get(x,x)} ({x})")
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
        except: st.error("代號無效")
