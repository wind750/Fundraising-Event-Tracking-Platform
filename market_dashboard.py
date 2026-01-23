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
# 📖 說明手冊
# ==========================================
with st.expander("📖 查看：操盤判讀邏輯 & 交易心法", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        ### 🔍 數據判讀 (🔴多 | 🟢空):
        1. **AI 資金雷達**：監控 AI 巨頭平均離差。
        2. **台股戰略**：領先指標亮紅燈 = 多方控盤。
        3. **風險雷達**：日圓跌破季線(60MA) = **平倉警報**。
        4. **Z-Score**：衡量數據擁擠度，超過 ±1.5 即為極端。
        """)
    with c2:
        st.markdown("""
        ### 🛡️ 交易心法:
        * **動態汰弱留強**：千金股名單會隨股價波動自動增減，確保只看「最強勢」的指標。
        * **部位控管**：流動性風險升溫時（日圓強升），持倉應果斷降至 3~5 成。
        """)

# ==========================================
# 2. 核心運算引擎 (Period="5y" 確保 Z-Score 正確)
# ==========================================

@st.cache_data(ttl=3600)
def fetch_data_cached(tickers, period="5y"):
    try:
        data = yf.download(tickers, period=period, progress=False)
        return data
    except:
        return pd.DataFrame()

name_map = {
    "NVDA": "輝達", "GOOGL": "Google", "MSFT": "微軟", "AAPL": "蘋果", "AMZN": "亞馬遜", "META": "Meta", "TSLA": "特斯拉", "AVGO": "博通",
    "^IXIC": "納斯達克", "SMH": "半導體ETF", "^SOX": "費半指數", "^TWII": "台灣加權", "^TWO": "櫃買指數",
    "SOXX": "費半 ETF", "00733.TW": "富邦中小", "DX-Y.NYB": "美元指數", "^TNX": "美債10年",
    "JPY=X": "美元/日圓", "ZQ=F": "聯邦利率期貨", "SPY": "標普 500", "2330.TW": "台積電", "^VIX": "VIX 恐慌",
    "BTC-USD": "比特幣", "GC=F": "黃金", "HG=F": "期貨銅", "CL=F": "原油"
}

# 擴大後的 24 檔高價股原始追蹤名單
high_price_track_list = [
    "5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "5269.TWO", 
    "3443.TW", "2454.TW", "2059.TW", "3533.TW", "3131.TWO", "3653.TW", 
    "3293.TWO", "6409.TW", "8454.TW", "6643.TW", "6415.TW", "8299.TWO", 
    "8464.TW", "1590.TW", "2327.TW", "2330.TW", "3034.TW", "4966.TWO"
]

all_tickers = list(set(list(name_map.keys()) + high_price_track_list + ["ZQ=F", "SPY"]))
cached_data = fetch_data_cached(all_tickers)

# 強化版數據處理：區分成功、過濾、失敗
def get_audit_df(ticker_list, cached_df, threshold=800):
    processed = []
    failed = []
    filtered = []
    
    data = cached_df['Close'] if 'Close' in cached_df.columns else cached_df
    
    for ticker in ticker_list:
        if ticker not in data.columns or data[ticker].dropna().empty:
            failed.append(ticker)
            continue
            
        series = data[ticker].fillna(method='ffill').dropna()
        price = series.iloc[-1]
        
        # 價格過濾邏輯
        if price < threshold:
            filtered.append({"代號": ticker, "現價": round(price, 2), "原因": f"低於 {threshold} 元"})
            continue
            
        # Z-Score 計算
        ma20 = series.rolling(20).mean().iloc[-1]
        bias = (price - ma20) / ma20 * 100
        lookback = min(len(series), 504)
        z = (price - series.tail(lookback).mean()) / series.tail(lookback).std() if series.tail(lookback).std() != 0 else 0
        
        processed.append({
            "代號": ticker, "資產名稱": name_map.get(ticker, ticker), 
            "趨勢": "🔴強勢" if bias > 0 else "🟢弱勢", 
            "現價": round(price, 2), "乖離率": round(bias, 2), "Z-Score": round(z, 2)
        })
        
    return pd.DataFrame(processed), pd.DataFrame(filtered), failed

# ==========================================
# 3. 分頁邏輯
# ==========================================
tabs = st.tabs(["💀 AI 資金", "🇹🇼 台股戰略", "🚀 風險雷達", "💎 半導體", "📈 趨勢圖", "⚖️ 法人估值"])
tab_ai, tab_tw, tab_risk, tab_semi, tab_chart, tab_valuation = tabs

with tab_ai:
    df_ai, _, _ = get_audit_df(["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "^IXIC", "SMH"], cached_data, threshold=0)
    if not df_ai.empty:
        c1, c2 = st.columns([1, 2])
        with c1:
            avg_bias = df_ai['乖離率'].mean()
            if avg_bias > 0: st.error(f"### 🔴 資金湧入\n平均離差: {round(avg_bias, 2)}%")
            else: st.success(f"### 🟢 資金退潮\n平均離差: {round(avg_bias, 2)}%")
            st.metric("整體擁擠度 (Z-Score)", round(df_ai['Z-Score'].mean(), 2))
        with c2:
            st.dataframe(df_ai[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("乖離率", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 2: 台股戰略 (數據稽核版) ---
with tab_tw:
    st.subheader("🇹🇼 台股戰略指標")
    df_lead, _, _ = get_audit_df(["SOXX", "00733.TW", "DX-Y.NYB", "^TNX"], cached_data, threshold=0)
    if not df_lead.empty:
        m1, m2, m3, m4 = st.columns(4)
        def show_m(col, ticker, name, inverse=False):
            r = df_lead[df_lead['代號']==ticker]
            if not r.empty: col.metric(name, f"{r['現價'].values[0]}", f"{r['乖離率'].values[0]}%", delta_color="normal" if not inverse else "inverse")
        show_m(m1, "SOXX", "費半 ETF")
        show_m(m2, "00733.TW", "富邦中小")
        show_m(m3, "DX-Y.NYB", "美元指數", inverse=True)
        show_m(m4, "^TNX", "美債10Y", inverse=True)

    st.divider()
    st.subheader("👑 千金與高價股動態觀察")
    
    # 執行稽核獲取數據
    df_king, df_filtered, failed_list = get_audit_df(high_price_track_list, cached_data, threshold=800)
    
    # 恢復統計卡片
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("當前達標檔數", f"{len(df_king)} 檔")
    s2.metric("強勢家數 (🔴)", f"{len(df_king[df_king['乖離率']>0])} 檔")
    s3.metric("低於門檻 (濾除)", f"{len(df_filtered)} 檔")
    s4.metric("族群平均 Z-Score", round(df_king['Z-Score'].mean(), 2) if not df_king.empty else 0)

    # --- 關鍵：稽核診斷中心 ---
    with st.expander("🔍 數據稽核中心：為什麼是這幾檔？(點擊查看消失的名單)"):
        ac1, ac2 = st.columns(2)
        with ac1:
            st.write("**🛡️ 已濾除 (現價 < 800 元)**")
            st.dataframe(df_filtered, hide_index=True)
        with ac2:
            st.write("**❌ 抓取失敗 (Yahoo API 缺漏)**")
            st.write(failed_list if failed_list else "無失敗項，數據完整。")

    st.dataframe(df_king[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("現價", ascending=False), hide_index=True, use_container_width=True)

# --- 其餘分頁 (風險、半導體、趨勢、估值) ---
with tab_risk:
    risk_raw = cached_data['Close'] if 'Close' in cached_data.columns else cached_data
    c1, c2 = st.columns(2)
    with c1:
        if 'JPY=X' in risk_raw.columns:
            jpy = risk_raw['JPY=X'].dropna()
            st.metric("日圓匯率 (JPY=X)", f"{round(jpy.iloc[-1], 2)}", "🔴 安全" if jpy.iloc[-1] > jpy.rolling(60).mean().iloc[-1] else "🟢 警戒", delta_color="normal" if jpy.iloc[-1] > jpy.rolling(60).mean().iloc[-1] else "inverse")
    with c2:
        if 'ZQ=F' in risk_raw.columns:
            rate = round(100 - risk_raw['ZQ=F'].dropna().iloc[-1], 2)
            st.metric("短端利率 (ZQ=F)", f"{rate}%", "🔴 穩定" if rate < 5.2 else "🟢 緊繃", delta_color="normal" if rate < 5.2 else "inverse")
    st.divider()
    df_risk_z, _, _ = get_audit_df(["^VIX", "BTC-USD", "GC=F", "HG=F", "CL=F", "DX-Y.NYB"], cached_data, threshold=0)
    st.dataframe(df_risk_z[["資產名稱", "Z-Score", "趨勢", "現價"]], hide_index=True, use_container_width=True)

with tab_semi:
    st.subheader("💎 巨頭與半導體強度 (vs SPY)")
    if 'SPY' in risk_raw.columns:
        bench_ret = (risk_raw['SPY'].iloc[-1] - risk_raw['SPY'].iloc[-60]) / risk_raw['SPY'].iloc[-60]
        semi_list = ["SOXX", "2330.TW", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AVGO"]
        res = []
        for t in semi_list:
            if t in risk_raw.columns:
                tgt = risk_raw[t].dropna()
                rs = (1 + (tgt.iloc[-1]-tgt.iloc[-60])/tgt.iloc[-60]) / (1+bench_ret)
                clr = "background-color: rgba(255, 50, 50, 0.15)" if rs > 1 else "background-color: rgba(50, 255, 50, 0.15)"
                res.append({"名稱": name_map.get(t,t), "強度(RS)": round(rs,4), "_c": clr})
        st.dataframe(pd.DataFrame(res).sort_values("強度(RS)", ascending=False).style.apply(lambda x: [x['_c']]*len(x), axis=1), column_config={"_c":None}, hide_index=True, use_container_width=True)

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
