import streamlit as st
import yfinance as yf
import pandas as pd

# === 設定網頁格式 ===
st.set_page_config(page_title="全球金融戰情室", layout="wide")
st.title("🌐 全球金融戰情室")
st.markdown("整合 **沛然資訊影片(風險預警)** 與 **Q4展望報告(資產配置)** 雙模型")

# === 1. 建立超級對照表 (包含所有商品) ===
name_map = {
    # --- 風險雷達用 ---
    "^SOX": "費城半導體", "BTC-USD": "比特幣", "HG=F": "銅期貨", "AUDJPY=X": "澳幣/日圓",
    "DX-Y.NYB": "美元指數", "GC=F": "黃金期貨", "JPY=X": "美元/日圓", "^VIX": "VIX恐慌",
    "^TWII": "台灣加權", "0050.TW": "元大台灣50", "^GSPC": "S&P 500", "^N225": "日經225",
    "^TNX": "美債10年殖利", "HYG": "高收益債", "TLT": "美債20年",
    
    # --- 宏觀配置用 ---
    "VTI": "美股全市場 (巴菲特指標)", "DBB": "工業金屬", "XLE": "能源類股",
    "DBA": "農產品", "DOG": "放空道瓊 (反向)", "000001.SS": "上證指數", "LQD": "投資級債"
}

# === 2. 定義兩套資產清單 ===
# (A) 風險雷達清單
assets_radar = {
    "1. 🚀 領先指標": ["^SOX", "BTC-USD", "HG=F", "AUDJPY=X"],
    "2. 🛡️ 避險資產": ["DX-Y.NYB", "GC=F", "JPY=X", "^VIX"],
    "3. 📉 股市現況": ["^TWII", "0050.TW", "^GSPC", "^N225"]
}

# (B) 宏觀配置清單
assets_macro = {
    "1. 🔥 強勢動能觀察": ["VTI", "DBB", "XLE", "GC=F"],
    "2. ❄️ 弱勢動能觀察": ["DBA", "BTC-USD", "DOG"],
    "3. 🌏 核心市場 (美/中/台)": ["^GSPC", "000001.SS", "^TWII", "0050.TW"],
    "4. 🏦 利率與債券": ["^TNX", "TLT", "LQD"]
}

# === 3. 萬用運算引擎 (同時算好所有指標) ===
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_data(ticker_list):
    results = []
    for ticker in ticker_list:
        try:
            # 下載 6 個月資料 (足夠算季動能和RSI)
            df = yf.download(ticker, period="6mo", progress=False)
            if not df.empty:
                price = df['Close'].iloc[-1]
                if isinstance(price, pd.Series): price = price.item()
                
                # --- 指標 1: 月線趨勢 (Trend) ---
                ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
                if isinstance(ma20, pd.Series): ma20 = ma20.item()
                bias = (price - ma20) / ma20 * 100
                trend_status = "🔴強勢" if bias > 0 else "🟢弱勢"
                
                # --- 指標 2: RSI (Risk) ---
                rsi_series = calculate_rsi(df['Close'])
                rsi = rsi_series.iloc[-1]
                if isinstance(rsi, pd.Series): rsi = rsi.item()
                rsi_status = "☁️"
                if rsi > 70: rsi_status = "🔥過熱"
                elif rsi < 30: rsi_status = "❄️超賣"
                
                # --- 指標 3: 季動能 (Momentum) ---
                if len(df) > 60:
                    price_q = df['Close'].iloc[-60]
                    if isinstance(price_q, pd.Series): price_q = price_q.item()
                    q_mom = (price - price_q) / price_q * 100
                else: q_mom = 0
                
                mom_str = f"{round(q_mom, 2)}%"
                if q_mom > 0: mom_str = f"🔴 +{mom_str}"
                else: mom_str = f"🟢 {mom_str}"

                ch_name = name_map.get(ticker, ticker)
                
                results.append({
                    "資產名稱": ch_name,
                    "趨勢 (月線)": trend_status,
                    "RSI訊號": f"{rsi_status} ({int(rsi)})",
                    "季動能 (3個月)": mom_str,
                    "現價": round(price, 2),
                    "原始代號": ticker
                })
        except: pass
    return pd.DataFrame(results)

# === 4. 建立分頁 (Tabs) ===
tab1, tab2, tab3 = st.tabs(["🚀 市場風險雷達", "🌐 宏觀資產配置", "📈 趨勢檢視器"])

# --- 分頁 1: 市場風險雷達 (原版邏輯) ---
with tab1:
    st.subheader("短線資金流向與風險預警")
    st.caption("邏輯：三大類資產同步轉向 (沛然影片) + RSI 過熱警示")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.write("**1. 領先指標**")
        df = get_data(assets_radar["1. 🚀 領先指標"])
        # 只顯示跟短線有關的欄位
        st.dataframe(df[["資產名稱", "趨勢 (月線)", "RSI訊號", "現價"]], hide_index=True, use_container_width=True)
    with c2:
        st.write("**2. 避險資產**")
        df = get_data(assets_radar["2. 🛡️ 避險資產"])
        st.dataframe(df[["資產名稱", "趨勢 (月線)", "RSI訊號", "現價"]], hide_index=True, use_container_width=True)
    with c3:
        st.write("**3. 股市現況**")
        df = get_data(assets_radar["3. 📉 股市現況"])
        st.dataframe(df[["資產名稱", "趨勢 (月線)", "RSI訊號", "現價"]], hide_index=True, use_container_width=True)

    st.divider()
    # 法人視野 (短線)
    k1, k2 = st.columns(2)
    with k1:
        st.info("📊 **美債殖利率 (^TNX)**")
        try:
            tnx = yf.download("^TNX", period="5d", progress=False)['Close']
            val = tnx.iloc[-1].item()
            chg = val - tnx.iloc[0].item()
            st.metric("殖利率 (高=不利科技股)", f"{round(val, 2)}%", f"{round(chg, 2)}", delta_color="inverse")
        except: st.write("讀取中...")
    with k2:
        st.info("🦁 **風險胃口 (HYG/TLT)**")
        try:
            data = yf.download(["HYG", "TLT"], period="3mo", progress=False)['Close'].dropna()
            if not data.empty:
                ratio = data['HYG'] / data['TLT']
                curr = ratio.iloc[-1]
                ma20 = ratio.rolling(window=20).mean().iloc[-1]
                delta = curr - ma20
                msg = "🔴 貪婪 (利多)" if delta > 0 else "🟢 恐慌 (利空)"
                st.metric("風險胃口比率", round(curr, 4), msg)
        except: st.write("讀取中...")

# --- 分頁 2: 宏觀資產配置 (新版邏輯) ---
with tab2:
    st.subheader("中長期資產強弱勢分佈")
    st.caption("邏輯：動能策略 (Momentum) - 追強勢、避弱勢")
    
    c1, c2 = st.columns(2)
    with c1:
        st.write("**🔥 強勢動能觀察**")
        df = get_data(assets_macro["1. 🔥 強勢動能觀察"])
        # 這裡顯示「季動能」
        st.dataframe(df[["資產名稱", "趨勢 (月線)", "季動能 (3個月)", "現價"]], hide_index=True, use_container_width=True)
    with c2:
        st.write("**❄️ 弱勢動能觀察**")
        df = get_data(assets_macro["2. ❄️ 弱勢動能觀察"])
        st.dataframe(df[["資產名稱", "趨勢 (月線)", "季動能 (3個月)", "現價"]], hide_index=True, use_container_width=True)
    
    st.divider()
    c3, c4 = st.columns(2)
    with c3:
        st.write("**🌏 核心市場 (美/中/台)**")
        df = get_data(assets_macro["3. 🌏 核心市場 (美/中/台)"])
        st.dataframe(df[["資產名稱", "趨勢 (月線)", "季動能 (3個月)", "現價"]], hide_index=True, use_container_width=True)
    with c4:
        st.write("**🏦 利率與債券**")
        df = get_data(assets_macro["4. 🏦 利率與債券"])
        st.dataframe(df[["資產名稱", "趨勢 (月線)", "季動能 (3個月)", "現價"]], hide_index=True, use_container_width=True)

# --- 分頁 3: 走勢圖 ---
with tab3:
    st.subheader("📈 資產趨勢檢視")
    # 合併所有資產清單
    all_keys = list(name_map.keys())
    opts = [f"{name_map[k]} ({k})" for k in all_keys]
    sel = st.selectbox("選擇商品：", opts)
    if sel:
        code = sel.split("(")[-1].replace(")", "")
        st.write(f"正在顯示 **{sel}** 過去半年的走勢...")
        try:
            df = yf.download(code, period="6mo", progress=False)
            st.line_chart(df['Close'])
        except: st.write("無圖表")