import streamlit as st
import yfinance as yf
import pandas as pd
import pytz
import requests
import io
from datetime import datetime

# ==========================================
# 1. 系統設定與佈局
# ==========================================
st.set_page_config(page_title="全球金融戰情室 (AI旗艦版)", layout="wide")
st.title("🌐 全球金融戰情室 (AI旗艦版)")

# 顯示台灣時間
tw_tz = pytz.timezone('Asia/Taipei')
current_time = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"🕒 最後更新時間 (台灣): {current_time}")

# ==========================================
# 📖 新手指南：操盤手心法與判讀 (整合版)
# ==========================================
with st.expander("📖 查看：操盤判讀邏輯 & 交易心法 (點擊展開)"):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        ### 🔍 數據判讀 (亞洲色調：🔴多/強 | 🟢空/弱):
        1. **AI 資金雷達**：監控 AI 七巨頭。平均離差 < 0 且亮綠燈，代表資金退潮。
        2. **台股戰略**：4 燈全紅 = 強力買點；千金股集體轉弱(綠)，內資主力撤退。
        3. **風險雷達**：日圓跌破季線(60MA) = **Carry Trade 平倉警報** (顯綠)。
        4. **央行水龍頭**：Fed 買債減少或資產下降(顯綠) = **縮表(QT)**，市場流動性枯竭。
        """)
    with c2:
        st.markdown("""
        ### 🛡️ 交易心法 (槓鈴策略):
        * **部位控管**：當風險雷達顯示「綠燈警戒」時，持倉水位應降至 **3~5 成**。
        * **拒絕 FOMO**：暴漲往往是機構在倒貨，觀察「成交量」而非單看價格。
        * **事件風險**：避開聯準會講話、CPI 發布前後的豪賭。
        * **勿過度優化**：若估值模型算出來「貴」，那就是貴，不要調整參數騙自己。
        """)

# ==========================================
# 2. 核心運算引擎
# ==========================================

# 抓取 FRED 數據函數 (Fed 持債)
def fetch_fred_data(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text), index_col='DATE', parse_dates=True)
            return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# 快取下載函數 (Yahoo Finance)
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
    "SOXX": "費半 ETF", "^TWOII": "櫃買(舊)", "00733.TW": "富邦中小", "DX-Y.NYB": "美元指數", "^TNX": "美債10年",
    "JPY=X": "美元/日圓", "^VIX": "VIX恐慌", "BTC-USD": "比特幣", "GC=F": "黃金期貨", "HG=F": "銅期貨", "AUDJPY=X": "澳幣/日圓",
    "HYG": "高收益債", "LQD": "投資級債", "RSP": "S&P500等權重", "SPY": "S&P500", "2330.TW": "台積電", "ZQ=F": "聯邦利率期貨", "^IRX": "13週國庫券"
}

# 下載所有名單
all_tickers = [
    "NVDA", "GOOG", "MSFT", "AAPL", "AMZN", "META", "TSLA", "AVGO",
    "^IXIC", "SMH", "^SOX", "^TWII", "^TWO", "SOXX", "00733.TW", "DX-Y.NYB", "^TNX",
    "JPY=X", "^VIX", "BTC-USD", "GC=F", "HG=F", "AUDJPY=X", "HYG", "LQD", "RSP", "SPY", "2330.TW", "ZQ=F", "^IRX",
    "5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "5269.TWO", "3443.TW", "2454.TW", "2059.TW", "3533.TW", 
    "3131.TWO", "3653.TW", "3293.TWO", "6409.TW", "8454.TW", "6643.TW", "6415.TW", "8299.TWO", "8464.TW"
]

cached_data = fetch_data_cached(all_tickers)

# 通用計算函數
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
                    if len(series) > 60: q_mom = (price - series.iloc[-60]) / series.iloc[-60] * 100
                    else: q_mom = 0
                    results.append({"代號": ticker, "資產名稱": name_map.get(ticker, ticker), "趨勢(月線)": trend, "現價": round(price, 2), "乖離率": bias, "季動能": q_mom})
        except: pass
    return pd.DataFrame(results)

# ==========================================
# 3. 分頁邏輯
# ==========================================
tabs = st.tabs(["💀 AI資金雷達", "🇹🇼 台股戰略", "🚀 風險雷達", "🏦 央行水龍頭", "💎 半導體", "📈 趨勢圖", "⚖️ 法人估值"])
tab_ai, tab_tw, tab_risk, tab_fed, tab_semi, tab_chart, tab_valuation = tabs

# --- Tab 1: AI 資金雷達 ---
with tab_ai:
    st.subheader("💀 AI資金掃描雷達")
    ai_list = ["NVDA", "GOOG", "MSFT", "AAPL", "AMZN", "META", "TSLA", "AVGO", "^IXIC", "SMH"]
    df_ai_res = get_data_from_cache(ai_list, cached_data)
    if not df_ai_res.empty:
        avg_bias = df_ai_res['乖離率'].mean()
        c1, c2 = st.columns([1, 2])
        with c1:
            if avg_bias > 0: st.error(f"### 🔴 多頭支撐\n平均離差: {round(avg_bias, 2)}%")
            else: st.success(f"### 🟢 資金退潮\n平均離差: {round(avg_bias, 2)}%")
            st.metric("多空家數", f"{len(df_ai_res[df_ai_res['乖離率']>0])} 強 / {len(df_ai_res[df_ai_res['乖離率']<=0])} 弱")
        with c2:
            st.dataframe(df_ai_res[["資產名稱", "趨勢(月線)", "乖離率", "現價"]].sort_values("乖離率", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 2: 台股戰略 ---
with tab_tw:
    st.subheader("🇹🇼 台股戰略指標")
    tw_lead = ["SOXX", "00733.TW", "DX-Y.NYB", "^TNX"]
    df_tw = get_data_from_cache(tw_lead, cached_data)
    if not df_tw.empty:
        c1, c2, c3, c4 = st.columns(4)
        # 簡易 4 燈判讀
        st.metric("1. 費半 (SOXX)", f"{df_tw[df_tw['代號']=='SOXX']['現價'].values[0]}", f"{round(df_tw[df_tw['代號']=='SOXX']['乖離率'].values[0],2)}%", delta_color="normal")
        st.metric("2. 中小 (00733)", f"{df_tw[df_tw['代號']=='00733.TW']['現價'].values[0]}", f"{round(df_tw[df_tw['代號']=='00733.TW']['乖離率'].values[0],2)}%", delta_color="normal")
        st.metric("3. 美元指數", f"{df_tw[df_tw['代號']=='DX-Y.NYB']['現價'].values[0]}", f"{round(df_tw[df_tw['代號']=='DX-Y.NYB']['乖離率'].values[0],2)}%", delta_color="inverse")
        st.metric("4. 美債10Y", f"{df_tw[df_tw['代號']=='^TNX']['現價'].values[0]}%", f"{round(df_tw[df_tw['代號']=='^TNX']['乖離率'].values[0],2)}%", delta_color="inverse")
    
    st.divider()
    st.subheader("👑 千金股信心溫度計")
    high_p_list = ["5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "5269.TWO", "2330.TW"]
    df_high = get_data_from_cache(high_p_list, cached_data)
    st.dataframe(df_high[df_high['現價']>1000][["資產名稱", "趨勢(月線)", "乖離率", "現價"]], hide_index=True, use_container_width=True)

# --- Tab 3: 風險雷達 (流動性監控) ---
with tab_risk:
    st.subheader("🚀 市場風險雷達 (流動性劇本)")
    
    # 日圓套利監控
    risk_raw = cached_data['Close'] if 'Close' in cached_data.columns else cached_data
    if 'JPY=X' in risk_raw.columns:
        jpy = risk_raw['JPY=X'].dropna()
        p, ma60 = jpy.iloc[-1], jpy.rolling(60).mean().iloc[-1]
        c1, c2 = st.columns(2)
        with c1:
            st.metric("1. 日圓匯率 (JPY=X)", f"{round(p, 2)}", "🔴 安全 (季線上)" if p > ma60 else "🟢 警戒 (季線下)", delta_color="normal" if p > ma60 else "inverse")
        with c2:
            if 'ZQ=F' in risk_raw.columns:
                rate = round(100 - risk_raw['ZQ=F'].dropna().iloc[-1], 2)
                st.metric("2. 短端資金成本 (期貨反推)", f"{rate}%", "🔴 穩定" if rate < 5.2 else "🟢 緊俏", delta_color="normal" if rate < 5.2 else "inverse")
    
    st.markdown("##### 📉 短端利率趨勢圖 (ZQ=F 反推)")
    st.line_chart(100 - risk_raw['ZQ=F'].dropna(), color="#FF4B4B")

# --- Tab 4: 央行水龍頭 (Fed 數據) ---
with tab_fed:
    st.subheader("🏦 Fed 資產負債表動態")
    df_total = fetch_fred_data("WALCL")
    df_short = fetch_fred_data("UST1TO5")
    df_long = fetch_fred_data("USTGT10")
    
    if not df_total.empty:
        m1, m2, m3 = st.columns(3)
        with m1: st.metric("Fed 總資產", f"{round(df_total.iloc[-1].item()/1000000, 2)} 兆", delta=None)
        with m2: st.metric("短期持債 (1-5Y)", f"{int(df_short.iloc[-1].item()/1000)} B", delta=None)
        with m3: st.metric("長期持債 (>10Y)", f"{int(df_long.iloc[-1].item()/1000)} B", delta=None)
        
        st.markdown("##### 📊 Fed 持債走勢 (WALCL / UST1TO5 / USTGT10)")
        plot_df = pd.DataFrame({
            "總資產(兆)": df_total['WALCL']/1000000,
            "1-5Y短債(十億)": df_short['UST1TO5']/1000,
            "10Y+長債(十億)": df_long['USTGT10']/1000
        }).fillna(method='ffill').tail(52)
        st.line_chart(plot_df)

# --- Tab 5: 半導體相對強度 ---
with tab_semi:
    st.subheader("💎 半導體相對強度 (vs SPY)")
    bench = risk_raw['SPY'].dropna()
    if not bench.empty:
        bench_ret = (bench.iloc[-1] - bench.iloc[-60]) / bench.iloc[-60]
        semi_list = ["SOXX", "2330.TW", "NVDA", "TSM", "AMD", "AVGO"]
        res = []
        for t in semi_list:
            if t in risk_raw.columns:
                tgt = risk_raw[t].dropna()
                ret = (tgt.iloc[-1] - tgt.iloc[-60]) / tgt.iloc[-60]
                rs = (1 + ret) / (1 + bench_ret)
                clr = "background-color: rgba(255, 50, 50, 0.2)" if rs > 1 else "background-color: rgba(50, 255, 50, 0.2)"
                res.append({"名稱": name_map.get(t,t), "強度(RS)": round(rs,4), "_c": clr})
        df_s = pd.DataFrame(res).sort_values("強度(RS)", ascending=False)
        st.dataframe(df_s.style.apply(lambda x: [x['_c']]*len(x), axis=1), column_config={"_c":None}, hide_index=True, use_container_width=True)

# --- Tab 6: 趨勢圖 ---
with tab_chart:
    st.subheader("📈 全球資產趨勢檢視")
    sel = st.selectbox("選擇監控商品：", all_tickers, format_func=lambda x: f"{name_map.get(x,x)} ({x})")
    if sel:
        st.line_chart(risk_raw[sel].dropna())

# --- Tab 7: 法人估值模型 ---
with tab_valuation:
    st.subheader("⚖️ 法人估值模型 (Smart Engine)")
    val_ticker = st.text_input("輸入股票代號 (如 2330.TW, NVDA)", value="2330.TW").upper()
    if val_ticker:
        try:
            stock = yf.Ticker(val_ticker)
            info = stock.info
            eps = info.get('trailingEps', 0)
            pe = info.get('trailingPE', 0)
            price = info.get('currentPrice', 0)
            
            # 智慧成長率推算
            g_suggested = info.get('earningsGrowth', 0.15)
            if g_suggested is None: g_suggested = 0.15
            
            st.write(f"### {info.get('longName', val_ticker)}")
            c1, c2, c3 = st.columns(3)
            c1.metric("現價", f"${price}")
            c2.metric("EPS", f"{eps}")
            c3.metric("本益比", f"{round(pe, 2) if pe else 'N/A'}")
            
            st.divider()
            user_g = st.slider("預估成長率 (%)", 1.0, 50.0, float(g_suggested*100))
            
            # 模型 1: PEG
            my_peg = pe / user_g if user_g > 0 else 0
            st.markdown(f"**PEG 估值**: {round(my_peg, 2)} ({'🔴高估' if my_peg > 1.5 else '🔴低估'})")
            
            # 模型 2: DCF
            discount = 0.1
            intrinsic = sum([(eps * (1 + user_g/100)**i) / (1 + discount)**i for i in range(1, 6)])
            st.markdown(f"**5年內在價值 (DCF簡化)**: ${round(intrinsic, 2)} ({'🔴低估' if intrinsic > price else '🟢高估'})")
            
        except: st.error("代號輸入錯誤或無數據")
            
