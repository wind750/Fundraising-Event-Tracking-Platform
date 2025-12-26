import streamlit as st
import yfinance as yf
import pandas as pd
import pytz
import requests
import io
from datetime import datetime

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
with st.expander("📖 新手指南：數據判讀 & 交易心法 (點擊展開)"):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        ### 🔍 數據判讀 (🔴多/強 | 🟢空/弱):
        1. **AI 資金雷達**：監控 AI 七巨頭。平均離差 < 0 且亮綠燈，代表資金退潮。
        2. **台股戰略**：4 燈全紅 = 強力買點；千金股集體轉弱(綠)，內資主力撤退。
        3. **風險雷達**：日圓跌破季線(60MA) = **Carry Trade 平倉警報** (顯綠)。
        4. **央行水龍頭**：Fed 買債減少或資產下降(顯綠) = **縮表(QT)**。
        """)
    with c2:
        st.markdown("""
        ### 🛡️ 交易心法 (槓鈴策略):
        * **部位控管**：當風險雷達顯示「綠燈警戒」時，持倉水位應降至 **3~5 成**。
        * **拒絕 FOMO**：暴漲往往是機構在倒貨，觀察「成交量」而非單看價格。
        * **事件風險**：避開聯準會講話、CPI 發布前後的豪賭。
        """)

# ==========================================
# 2. 核心函數
# ==========================================

# 強化版 FRED 抓取函數
def fetch_fred_data(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    # 模擬完整的瀏覽器請求頭，防止被 FRED 封鎖
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text), index_col='DATE', parse_dates=True)
            return df
        else:
            st.warning(f"⚠️ FRED 請求失敗 (HTTP {response.status_code}): {series_id}")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ 無法連線至 FRED ({series_id}): {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_data_cached(tickers, period="1y"):
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
    "JPY=X": "美元/日圓", "ZQ=F": "聯邦利率期貨", "SPY": "S&P500", "2330.TW": "台積電"
}

all_tickers = list(name_map.keys()) + ["5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "5269.TWO", "3443.TW", "2454.TW", "2059.TW", "3533.TW"]
cached_data = fetch_data_cached(all_tickers)

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
                    results.append({"代號": ticker, "資產名稱": name_map.get(ticker, ticker), "趨勢(月線)": trend, "現價": round(price, 2), "乖離率": bias})
        except: pass
    return pd.DataFrame(results)

# ==========================================
# 3. 分頁顯示
# ==========================================
tabs = st.tabs(["💀 AI資金雷達", "🇹🇼 台股戰略", "🚀 風險雷達", "🏦 央行水龍頭", "💎 半導體", "📈 趨勢圖", "⚖️ 法人估值"])
tab_ai, tab_tw, tab_risk, tab_fed, tab_semi, tab_chart, tab_valuation = tabs

# --- Tab 1: AI 資金 ---
with tab_ai:
    ai_list = ["NVDA", "GOOG", "MSFT", "AAPL", "AMZN", "META", "TSLA", "AVGO", "^IXIC", "SMH"]
    df_ai_res = get_data_from_cache(ai_list, cached_data)
    if not df_ai_res.empty:
        avg_bias = df_ai_res['乖離率'].mean()
        c1, c2 = st.columns([1, 2])
        with c1:
            if avg_bias > 0: st.error(f"### 🔴 多頭支撐\n平均離差: {round(avg_bias, 2)}%")
            else: st.success(f"### 🟢 資金退潮\n平均離差: {round(avg_bias, 2)}%")
        with c2:
            st.dataframe(df_ai_res[["資產名稱", "趨勢(月線)", "乖離率", "現價"]].sort_values("乖離率", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 2: 台股 ---
with tab_tw:
    df_tw = get_data_from_cache(["SOXX", "00733.TW", "DX-Y.NYB", "^TNX"], cached_data)
    if not df_tw.empty:
        c1, c2, c3, c4 = st.columns(4)
        for i, row in df_tw.iterrows():
            st.metric(row['資產名稱'], f"{row['現價']}", f"{round(row['乖離率'],2)}%")

# --- Tab 3: 風險雷達 ---
with tab_risk:
    risk_raw = cached_data['Close'] if 'Close' in cached_data.columns else cached_data
    if 'JPY=X' in risk_raw.columns:
        jpy = risk_raw['JPY=X'].dropna()
        p, ma60 = jpy.iloc[-1], jpy.rolling(60).mean().iloc[-1]
        c1, c2 = st.columns(2)
        with c1: st.metric("日圓匯率 (JPY=X)", f"{round(p, 2)}", "🔴 安全" if p > ma60 else "🟢 警戒", delta_color="normal" if p > ma60 else "inverse")
        with c2:
            if 'ZQ=F' in risk_raw.columns:
                rate = round(100 - risk_raw['ZQ=F'].dropna().iloc[-1], 2)
                st.metric("短端利率 (期貨反推)", f"{rate}%", "🔴 穩定" if rate < 5.2 else "🟢 緊俏", delta_color="normal" if rate < 5.2 else "inverse")
    st.line_chart(100 - risk_raw['ZQ=F'].dropna() if 'ZQ=F' in risk_raw.columns else None, color="#FF4B4B")

# --- Tab 4: 央行水龍頭 (修正區) ---
with tab_fed:
    st.subheader("🏦 Fed 聯運用資金監控 (縮擴表趨勢)")
    
    # 手動刷新按鈕
    if st.button("🔄 重新載入 Fed 數據"):
        st.cache_data.clear()

    # 開始載入
    with st.spinner("⏳ 正在連線美國聯準會資料庫... (約需 5-10 秒)"):
        # WALCL: 總資產 | UST1TO5: 1-5年債 | USTGT10: >10年債
        df_total = fetch_fred_data("WALCL")
        df_short = fetch_fred_data("UST1TO5")
        df_long = fetch_fred_data("USTGT10")
    
    # 檢查是否至少總資產抓得到
    if not df_total.empty:
        m1, m2, m3 = st.columns(3)
        try:
            total_latest = df_total.iloc[-1].item()
            total_prev = df_total.iloc[-2].item()
            total_diff = total_latest - total_prev
            
            with m1:
                st.metric("Fed 總資產規模", 
                          f"{round(total_latest/1000000, 2)} 兆", 
                          f"{round(total_diff/1000, 1)} B (週變動)",
                          delta_color="normal" if total_diff > 0 else "inverse")
            
            if not df_short.empty:
                with m2:
                    st.metric("短期持債 (1-5Y)", f"{int(df_short.iloc[-1].item()/1000)} B", delta=None)
            
            if not df_long.empty:
                with m3:
                    st.metric("長期持債 (>10Y)", f"{int(df_long.iloc[-1].item()/1000)} B", delta=None)
            
            st.divider()
            st.markdown("##### 📊 Fed 資產趨勢走勢 (兆美元)")
            # 整合繪圖
            plot_df = pd.DataFrame({"總資產": df_total['WALCL']/1000000}).ffill().tail(52)
            st.line_chart(plot_df)
            st.caption("資料來源：Federal Reserve Bank of St. Louis (FRED)")
            
        except Exception as e:
            st.error(f"數據解析錯誤: {e}")
    else:
        st.error("❌ 目前無法取得 Fed 資料。這可能是因為連線至 FRED 伺服器超時或被暫時擋掉。")
        st.info("💡 建議：請檢查您的網路連線，或於幾分鐘後點擊上方的「重新載入」按鈕。")

# --- 其餘分頁 (半導體、趨勢、估值) ---
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
    sel = st.selectbox("選擇監控商品：", all_tickers, format_func=lambda x: f"{name_map.get(x,x)} ({x})")
    if sel: st.line_chart(risk_raw[sel].dropna())

with tab_valuation:
    v_ticker = st.text_input("輸入股票代號 (如 NVDA)", value="2330.TW").upper()
    if v_ticker:
        try:
            info = yf.Ticker(v_ticker).info
            eps, pe, price = info.get('trailingEps', 0), info.get('trailingPE', 0), info.get('currentPrice', 0)
            st.write(f"### {info.get('longName', v_ticker)} | 現價: ${price}")
            g = st.slider("預估成長率 (%)", 1, 50, 15)
            st.write(f"**PEG 估值**: {round(pe/g, 2) if g else 0} ({'🔴高估' if pe/g > 1.2 else '🔴低估'})")
        except: st.error("代號無效")
