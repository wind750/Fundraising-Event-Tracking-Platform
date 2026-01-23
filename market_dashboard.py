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
# 📖 新手指南 (整合 2026 核心理論)
# ==========================================
with st.expander("📖 2026 操盤判讀與實驗理論 (點擊展開)"):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        ### 🔍 數據判讀 (🔴多/強 | 🟢空/弱):
        1. **AI 資金雷達**：監控 Mag 7 資金池。平均離差 < 0 且亮綠燈，代表資金退潮。
        2. **台股戰略**：4 燈全紅 = 強力買點；千金股集體轉弱(綠)，代表大戶先行。
        3. **日圓 Carry Trade**：日圓跌破 **60MA (季線)** 即觸發平倉預警 (顯綠)。
        4. **資金擁擠度**：透過 **Z-Score** 判斷當前持倉是否過度擁擠 (> +1.5) 或悲觀 (< -1.5)。
        """)
    with c2:
        st.markdown("""
        ### 🏦 2026 核心實驗：SRF 與流動性
        * **SRF 機制實測**：當銀行缺錢時會向 Fed 尋求 SRF。我們透過 **ZQ=F (利率期貨)** 的 Z-Score 監控短端資金是否「異常緊繃」。
        * **槓鈴策略**：在融漲 (Melt-up) 末端，保留 20% 黃金與現金，防範海嘯級回撤。
        * **部位控管**：日圓與利率雙指標亮綠燈時，部位嚴格限制在 **3 成以下**。
        """)

# ==========================================
# 2. 核心運算引擎
# ==========================================

@st.cache_data(ttl=3600)
def fetch_data_cached(tickers, period="2y"): # 抓取 2 年以計算 Z-Score
    try:
        data = yf.download(tickers, period=period, progress=False)
        return data
    except:
        return pd.DataFrame()

# 中英文對照表
name_map = {
    "NVDA": "輝達", "GOOG": "Google", "MSFT": "微軟", "AAPL": "蘋果", "AMZN": "亞馬遜", "META": "Meta", "TSLA": "特斯拉", "AVGO": "博通",
    "^IXIC": "納斯達克", "SMH": "半導體ETF", "^SOX": "費半指數", "^TWII": "台灣加權", "^TWO": "櫃買指數",
    "SOXX": "費半 ETF", "00733.TW": "富邦中小", "DX-Y.NYB": "美元指數", "^TNX": "美債10年",
    "JPY=X": "美元/日圓", "ZQ=F": "聯邦利率期貨", "SPY": "S&P500", "2330.TW": "台積電", "^VIX": "VIX 恐慌"
}

all_tickers = list(name_map.keys()) + [
    "5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "5269.TWO", "2454.TW"
]
cached_data = fetch_data_cached(all_tickers)

# Z-Score 計算函數
def calculate_zscore(series, window=504): # 504 天約等於兩年交易日
    if len(series) < 30: return 0
    mean = series.rolling(window=window).mean().iloc[-1]
    std = series.rolling(window=window).std().iloc[-1]
    if std == 0: return 0
    return (series.iloc[-1] - mean) / std

def get_data_from_cache(ticker_list, cached_df):
    results = []
    data = cached_df['Close'] if 'Close' in cached_df.columns else cached_df
    for ticker in ticker_list:
        try:
            if ticker in data.columns:
                series = data[ticker].dropna()
                if not series.empty:
                    price = series.iloc[-1]
                    ma20 = series.rolling(20).mean().iloc[-1]
                    bias = (price - ma20) / ma20 * 100
                    trend = "🔴強勢" if bias > 0 else "🟢弱勢"
                    z = calculate_zscore(series)
                    results.append({"代號": ticker, "資產名稱": name_map.get(ticker, ticker), "趨勢": trend, "現價": round(price, 2), "乖離率": bias, "Z-Score": round(z, 2)})
        except: pass
    return pd.DataFrame(results)

# ==========================================
# 3. 分頁邏輯
# ==========================================
tabs = st.tabs(["💀 AI 資金雷達", "🇹🇼 台股戰略", "🚀 風險雷達 (流動性)", "💎 半導體", "📈 趨勢圖", "⚖️ 法人估值"])
tab_ai, tab_tw, tab_risk, tab_semi, tab_chart, tab_valuation = tabs

# --- Tab 1: AI 資金雷達 ---
with tab_ai:
    st.subheader("💀 AI 資金掃描雷達")
    ai_list = ["NVDA", "GOOG", "MSFT", "AAPL", "AMZN", "META", "TSLA", "AVGO", "^IXIC", "SMH"]
    df_ai = get_data_from_cache(ai_list, cached_data)
    if not df_ai.empty:
        avg_bias = df_ai['乖離率'].mean()
        c1, c2 = st.columns([1, 2])
        with c1:
            if avg_bias > 0: st.error(f"### 🔴 多頭支撐\n平均離差: {round(avg_bias, 2)}%")
            else: st.success(f"### 🟢 資金退潮\n平均離差: {round(avg_bias, 2)}%")
            st.metric("資金擁擠度 (Z-Score)", df_ai['Z-Score'].mean())
        with c2:
            st.dataframe(df_ai[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("乖離率", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 2: 台股戰略 ---
with tab_tw:
    df_tw = get_data_from_cache(["SOXX", "00733.TW", "DX-Y.NYB", "^TNX"], cached_data)
    if not df_tw.empty:
        c1, c2, c3, c4 = st.columns(4)
        for i, row in df_tw.iterrows():
            st.metric(row['資產名稱'], f"{row['現價']}", f"{round(row['乖離率'],2)}%")
    st.divider()
    st.subheader("👑 千金股信心溫度計")
    high_p_list = ["5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "2454.TW", "2330.TW"]
    df_high = get_data_from_cache(high_p_list, cached_data)
    st.dataframe(df_high[df_high['現價']>=1000][["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("乖離率", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 3: 風險雷達 (2026 升級版) ---
with tab_risk:
    st.subheader("🚀 市場風險雷達 (流動性與擁擠度)")
    risk_raw = cached_data['Close'] if 'Close' in cached_data.columns else cached_data
    
    # A. 日圓 Carry Trade 斷路器
    if 'JPY=X' in risk_raw.columns:
        jpy_series = risk_raw['JPY=X'].dropna()
        p_jpy, ma60_jpy = jpy_series.iloc[-1], jpy_series.rolling(60).mean().iloc[-1]
        
        # B. 短端利率成本 (SRF 替代觀測)
        rate_series = (100 - risk_raw['ZQ=F']).dropna() if 'ZQ=F' in risk_raw.columns else pd.Series()
        z_rate = calculate_zscore(rate_series) if not rate_series.empty else 0
        
        c1, c2 = st.columns(2)
        with c1:
            st.metric("1. 日圓套利指標 (JPY=X)", f"{round(p_jpy, 2)}", 
                      "🔴 安全 (套利中)" if p_jpy > ma60_jpy else "🟢 警戒 (平倉潮)", 
                      delta_color="normal" if p_jpy > ma60_jpy else "inverse")
            st.caption(f"季線 (60MA): {round(ma60_jpy, 2)} | 目前匯率低於季線即觸發全球拋售預警")
        
        with c2:
            st.metric("2. 資金成本 Z-Score (SRF 壓力)", f"{round(z_rate, 2)}", 
                      "🔴 穩定" if z_rate < 1.5 else "🟢 緊繃 (SRF 需求升)", 
                      delta_color="normal" if z_rate < 1.5 else "inverse")
            st.caption("Z-Score > +1.5 代表短端資金成本進入兩年來極端高點，系統風險大增。")

    st.divider()
    
    # C. 持倉擁擠度 Z-Score 掃描
    st.markdown("##### 🔍 關鍵資產擁擠度掃描 (Z-Score 兩年回測)")
    crowd_list = ["SPY", "DX-Y.NYB", "BTC-USD", "GC=F", "^VIX", "HYG"]
    df_crowd = get_data_from_cache(crowd_list, cached_data)
    
    # 視覺化判讀
    def color_z(val):
        color = 'red' if val > 1.5 else ('green' if val < -1.5 else 'white')
        return f'color: {color}'
    
    st.dataframe(df_crowd[["資產名稱", "Z-Score", "趨勢"]].style.applymap(color_z, subset=['Z-Score']), hide_index=True, use_container_width=True)
    st.info("💡 判讀：Z-Score > +1.5 為過度擁擠 (易回檔)；< -1.5 為過度悲觀 (易反彈)。")

# --- Tab 4: 半導體相對強度 ---
with tab_semi:
    st.subheader("💎 半導體相對強度 (vs SPY)")
    bench = risk_raw['SPY'].dropna()
    if not bench.empty:
        bench_ret = (bench.iloc[-1] - bench.iloc[-60]) / bench.iloc[-60]
        semi_list = ["SOXX", "2330.TW", "NVDA", "AVGO"]
        res = []
        for t in semi_list:
            if t in risk_raw.columns:
                tgt = risk_raw[t].dropna()
                ret = (tgt.iloc[-1]-tgt.iloc[-60])/tgt.iloc[-60]
                rs = (1 + ret) / (1 + bench_ret)
                clr = "background-color: rgba(255, 50, 50, 0.15)" if rs > 1 else "background-color: rgba(50, 255, 50, 0.15)"
                res.append({"名稱": name_map.get(t,t), "強度(RS)": round(rs,4), "_c": clr})
        st.dataframe(pd.DataFrame(res).sort_values("強度(RS)", ascending=False).style.apply(lambda x: [x['_c']]*len(x), axis=1), 
                     column_config={"_c":None}, hide_index=True, use_container_width=True)

# --- Tab 5: 趨勢圖 ---
with tab_chart:
    st.subheader("📈 全球資產趨勢檢視")
    sel = st.selectbox("選擇監控商品：", all_tickers, format_func=lambda x: f"{name_map.get(x,x)} ({x})")
    if sel:
        st.line_chart(risk_raw[sel].dropna())

# --- Tab 6: 法人估值模型 ---
with tab_valuation:
    st.subheader("⚖️ 法人估值模型 (2026 修正版)")
    v_ticker = st.text_input("輸入股票代號 (如 2330.TW, NVDA)", value="2330.TW").upper()
    if v_ticker:
        try:
            stock = yf.Ticker(v_ticker)
            info = stock.info
            eps, pe, price = info.get('trailingEps', 0), info.get('trailingPE', 0), info.get('currentPrice', 0)
            st.write(f"### {info.get('longName', v_ticker)} | 現價: ${price}")
            
            # 加入日圓壓力測試邏輯
            p_jpy = risk_raw['JPY=X'].dropna().iloc[-1]
            ma60_jpy = risk_raw['JPY=X'].dropna().rolling(60).mean().iloc[-1]
            stress_buffer = 0.8 if p_jpy < ma60_jpy else 1.0 # 日圓破季線，估值打 8 折
            
            user_g = st.slider("預估未來成長率 (%)", 1, 50, 15)
            c1, c2 = st.columns(2)
            with c1:
                peg = pe / user_g if user_g else 0
                st.metric("PEG 估值", round(peg, 2), "🟢 低估" if peg < 1 else "🔴 高估", delta_color="inverse")
            with c2:
                discount = 0.12 # 考慮 2026 利率風險，稍微調高折現率
                intrinsic = sum([(eps * (1 + user_g/100)**i) / (1 + discount)**i for i in range(1, 6)])
                adjusted_intrinsic = intrinsic * stress_buffer
                st.metric("調整後內在價值 (DCF)", f"${round(adjusted_intrinsic, 2)}", 
                          "🔴 低估" if adjusted_intrinsic > price else "🟢 高估")
                if stress_buffer < 1.0: st.warning("⚠️ 已套用日圓升值流動性壓力測試 (估值打 8 折)")
        except: st.error("目前無法取得該股票的基本面數據")
