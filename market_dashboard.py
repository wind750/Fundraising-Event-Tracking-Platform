import streamlit as st
import yfinance as yf
import pandas as pd

# === 設定網頁格式 ===
st.set_page_config(page_title="全球金融戰情室", layout="wide")
st.title("🌐 全球金融戰情室")
st.markdown("整合 **短線風險預警 (Risk Radar)**、**長線資產配置 (Asset Allocation)** 與 **類股輪動策略 (Rotation Strategy)**")

# === 📖 新手指南 (內建說明書) ===
with st.expander("📖 新手指南：如何一眼判讀這個儀表板？ (點擊展開)"):
    st.markdown("""
    ### 1. 🚀 市場風險雷達 (Tab 1) - 【看天氣】
    * **定位**：判斷現在是「晴天 (適合出門)」還是「雨天 (現金為王)」。
    * **怎麼看**：
        * **全紅 🔴**：資金湧入，趨勢向上 ⮕ **安心持有**。
        * **全綠 🟢**：資金撤退，趨勢向下 ⮕ **減碼觀望**。
        * **關鍵指標**：若「風險胃口」顯示 **🟢 恐慌**，即使指數沒跌，也建議先跑。

    ### 2. 🌐 宏觀資產配置 (Tab 2) - 【看季節】
    * **定位**：判斷現在的主流是誰？(科技？能源？還是避險？)
    * **怎麼看**：
        * **強勢動能區**：如果這裡依然是 **🔴 紅色**，代表主流沒變，繼續抱緊。
        * **弱勢動能區**：如果這裡突然轉紅，代表資金在輪動 (例如從科技轉去農產品)，尋找新機會。

    ### 3. 🔄 類股輪動模擬 (Tab 3) - 【看指令】
    * **定位**：傻瓜操作指令，告訴你現在該「攻」還是「守」。
    * **怎麼看**：
        * **🟩 綠色框 (牛市)**：不用想太多，資金集中買 **科技股 (QQQ)**。
        * **🟥 紅色框 (熊市)**：科技股轉弱！賣掉 QQQ，去下方的排行榜找 **前 3 名** 高分資產避險。

    ### 4. 📈 趨勢檢視器 (Tab 4) - 【照鏡子】
    * **定位**：眼見為憑。
    * **怎麼看**：買進前先來這裡看圖，確認線圖是 **「左下右上」** 的多頭排列才下單。
    """)

# === 1. 建立超級對照表 (包含所有商品) ===
name_map = {
    # --- 風險雷達用 ---
    "^SOX": "費城半導體", "BTC-USD": "比特幣", "HG=F": "銅期貨", "AUDJPY=X": "澳幣/日圓",
    "DX-Y.NYB": "美元指數", "GC=F": "黃金期貨", "JPY=X": "美元/日圓", "^VIX": "VIX恐慌",
    "^TWII": "台灣加權", "0050.TW": "元大台灣50", "^GSPC": "S&P 500", "^N225": "日經225",
    "^TNX": "美債10年殖利", "HYG": "高收益債", "TLT": "美債20年",
    
    # --- 宏觀配置用 ---
    "VTI": "美股全市場", "DBB": "工業金屬", "XLE": "能源類股",
    "DBA": "農產品", "DOG": "放空道瓊", "000001.SS": "上證指數", "LQD": "投資級債",

    # --- 輪動策略專用 (七大資產 ETF) ---
    "QQQ": "科技股 (QQQ)",
    "UUP": "美元ETF (UUP)",
    "GLD": "黃金ETF (GLD)"
}

# === 2. 定義資產清單 ===
assets_radar = {
    "1. 🚀 領先指標": ["^SOX", "BTC-USD", "HG=F", "AUDJPY=X"],
    "2. 🛡️ 避險資產": ["DX-Y.NYB", "GC=F", "JPY=X", "^VIX"],
    "3. 📉 股市現況": ["^TWII", "0050.TW", "^GSPC", "^N225"]
}

assets_macro = {
    "1. 🔥 強勢動能觀察": ["VTI", "DBB", "XLE", "GC=F"],
    "2. ❄️ 弱勢動能觀察": ["DBA", "BTC-USD", "DOG"],
    "3. 🌏 核心市場": ["^GSPC", "000001.SS", "^TWII", "0050.TW"],
    "4. 🏦 利率與債券": ["^TNX", "TLT", "LQD"]
}

# 七大類資產 (策略核心)
assets_rotation = ["QQQ", "HYG", "UUP", "BTC-USD", "GLD", "XLE", "DBA"]

# === 3. 萬用運算引擎 ===
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
            # 下載 6 個月資料
            df = yf.download(ticker, period="6mo", progress=False)
            if not df.empty:
                price = df['Close'].iloc[-1]
                if isinstance(price, pd.Series): price = price.item()
                
                # 1. 月線 (20MA)
                ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
                if isinstance(ma20, pd.Series): ma20 = ma20.item()
                bias = (price - ma20) / ma20 * 100
                trend_status = "🔴強勢" if bias > 0 else "🟢弱勢"
                
                # 2. 季線 (60MA)
                ma60 = df['Close'].rolling(window=60).mean().iloc[-1]
                if isinstance(ma60, pd.Series): ma60 = ma60.item()
                
                # 3. RSI
                rsi_series = calculate_rsi(df['Close'])
                rsi = rsi_series.iloc[-1]
                if isinstance(rsi, pd.Series): rsi = rsi.item()
                rsi_status = "🔥過熱" if rsi > 70 else ("❄️超賣" if rsi < 30 else "☁️")
                
                # 4. 季動能
                if len(df) > 60:
                    price_q = df['Close'].iloc[-60]
                    if isinstance(price_q, pd.Series): price_q = price_q.item()
                    q_mom = (price - price_q) / price_q * 100
                else: q_mom = 0
                
                mom_str = f"{round(q_mom, 2)}%"
                if q_mom > 0: mom_str = f"🔴 +{mom_str}"
                else: mom_str = f"🟢 {mom_str}"

                # 宏觀分數
                score = 0
                if price > ma60: score += 40
                if q_mom > 0: score += 30
                if rsi > 50: score += 30
                
                ch_name = name_map.get(ticker, ticker)
                
                results.append({
                    "代號": ticker, 
                    "資產名稱": ch_name,
                    "趨勢 (月線)": trend_status,
                    "RSI訊號": f"{rsi_status} ({int(rsi)})",
                    "季動能 (3個月)": mom_str,
                    "宏觀分數": score,
                    "現價": round(price, 2)
                })
        except: pass
    return pd.DataFrame(results)

# === 4. 介面分頁 ===
tab1, tab2, tab3, tab4 = st.tabs(["🚀 市場風險雷達", "🌐 宏觀資產配置", "🔄 類股輪動模擬", "📈 趨勢檢視器"])

# --- Tab 1: 風險雷達 ---
with tab1:
    st.subheader("短線資金流向與風險預警")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.write("**1. 領先指標**")
        st.dataframe(get_data(assets_radar["1. 🚀 領先指標"])[["資產名稱", "趨勢 (月線)", "RSI訊號", "現價"]], hide_index=True, use_container_width=True)
    with c2:
        st.write("**2. 避險資產**")
        st.dataframe(get_data(assets_radar["2. 🛡️ 避險資產"])[["資產名稱", "趨勢 (月線)", "RSI訊號", "現價"]], hide_index=True, use_container_width=True)
    with c3:
        st.write("**3. 股市現況**")
        st.dataframe(get_data(assets_radar["3. 📉 股市現況"])[["資產名稱", "趨勢 (月線)", "RSI訊號", "現價"]], hide_index=True, use_container_width=True)

    st.divider()
    k1, k2 = st.columns(2)
    with k1:
        st.info("📊 **美債殖利率 (^TNX)**")
        try:
            tnx = yf.download("^TNX", period="5d", progress=False)['Close']
            st.metric("殖利率 (高=不利科技股)", f"{round(tnx.iloc[-1].item(), 2)}%")
        except: st.write("讀取中...")
    with k2:
        st.info("🦁 **風險胃口 (HYG/TLT)**")
        try:
            data = yf.download(["HYG", "TLT"], period="3mo", progress=False)['Close'].dropna()
            if not data.empty:
                ratio = data['HYG'] / data['TLT']
                curr = ratio.iloc[-1]
                ma20 = ratio.rolling(window=20).mean().iloc[-1]
                msg = "🔴 貪婪 (利多)" if (curr - ma20) > 0 else "🟢 恐慌 (利空)"
                st.metric("風險胃口比率", round(curr, 4), msg)
        except: st.write("讀取中...")

# --- Tab 2: 宏觀配置 ---
with tab2:
    st.subheader("中長期資產強弱勢分佈")
    c1, c2 = st.columns(2)
    with c1:
        st.write("**🔥 強勢動能觀察**")
        st.dataframe(get_data(assets_macro["1. 🔥 強勢動能觀察"])[["資產名稱", "趨勢 (月線)", "季動能 (3個月)", "現價"]], hide_index=True, use_container_width=True)
    with c2:
        st.write("**❄️ 弱勢動能觀察**")
        st.dataframe(get_data(assets_macro["2. ❄️ 弱勢動能觀察"])[["資產名稱", "趨勢 (月線)", "季動能 (3個月)", "現價"]], hide_index=True, use_container_width=True)
    
    st.divider()
    c3, c4 = st.columns(2)
    with c3:
        st.write("**🌏 核心市場**")
        st.dataframe(get_data(assets_macro["3. 🌏 核心市場"])[["資產名稱", "趨勢 (月線)", "季動能 (3個月)", "現價"]], hide_index=True, use_container_width=True)
    with c4:
        st.write("**🏦 利率與債券**")
        st.dataframe(get_data(assets_macro["4. 🏦 利率與債券"])[["資產名稱", "趨勢 (月線)", "季動能 (3個月)", "現價"]], hide_index=True, use_container_width=True)

# --- Tab 3: 類股輪動模擬 ---
with tab3:
    st.subheader("🔄 七大資產輪動策略模擬")
    
    # 1. 取得數據
    df_rotate = get_data(assets_rotation)
    
    # 2. 判斷 QQQ
    qqq_row = df_rotate[df_rotate['代號'] == 'QQQ']
    if not qqq_row.empty:
        qqq_score = qqq_row['宏觀分數'].values[0]
        st.divider()
        col_score, col_signal = st.columns([1, 2])
        with col_score:
            st.metric("科技股 (QQQ) 宏觀分數", f"{qqq_score} 分")
        with col_signal:
            if qqq_score >= 60:
                st.success(f"### 🐂 判定：牛市攻擊模式\n**建議策略**：資金集中持有 **科技股 (QQQ)**，享受趨勢紅利。")
            else:
                st.error(f"### 🐻 判定：熊市避險模式\n**建議策略**：科技股轉弱！建議將資金分散至 **債、匯、金、能** 等其他高分資產。")

    st.divider()
    st.write("**📊 七大類資產戰力排行榜 (依分數高低排序)**")
    
    df_rotate = df_rotate.sort_values(by="宏觀分數", ascending=False)
    
    def highlight_qqq(row):
        return ['background-color: #e6f3ff' if row['代號'] == 'QQQ' else '' for _ in row]

    st.dataframe(
        df_rotate[["代號", "資產名稱", "宏觀分數", "季動能 (3個月)", "RSI訊號", "現價"]].style.apply(highlight_qqq, axis=1), 
        hide_index=True, 
        use_container_width=True
    )

# --- Tab 4: 走勢圖 ---
with tab4:
    st.subheader("📈 資產趨勢檢視")
    all_keys = list(name_map.keys()) + ["QQQ", "UUP", "GLD"]
    all_keys = list(set(all_keys))
    opts = [f"{name_map.get(k, k)} ({k})" for k in all_keys]
    sel = st.selectbox("選擇商品：", opts)
    if sel:
        code = sel.split("(")[-1].replace(")", "")
        try:
            df = yf.download(code, period="6mo", progress=False)
            st.line_chart(df['Close'])
        except: st.write("無圖表")