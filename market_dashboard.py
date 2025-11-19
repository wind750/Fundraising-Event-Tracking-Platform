import streamlit as st
import yfinance as yf
import pandas as pd

# === 設定網頁格式 ===
st.set_page_config(page_title="全球金融戰情室", layout="wide")
st.title("🌐 全球金融戰情室 (旗艦版)")
st.markdown("整合 **風險預警**、**資產配置**、**輪動策略** 與 **半導體深層雷達**")

# === 📖 新手指南 (更新版) ===
with st.expander("📖 新手指南：如何一眼判讀這個儀表板？ (點擊展開)"):
    st.markdown("""
    ### 1. 🚀 市場風險雷達 (Tab 1) - 【看天氣】
    * **全紅 🔴** = 晴天 (安心持有) | **全綠 🟢** = 雨天 (現金為王)。
    * **關鍵**：若「風險胃口」顯示 **🟢 恐慌**，建議先跑。

    ### 2. 🌐 宏觀資產配置 (Tab 2) - 【看季節】
    * **強勢區**：若持續 **🔴 紅色**，代表主流沒變。
    * **弱勢區**：若轉紅，代表資金輪動尋找新機會。

    ### 3. 🔄 類股輪動模擬 (Tab 3) - 【看指令】
    * **🟩 綠色框 (牛市)**：資金集中買 **科技股 (QQQ)**。
    * **🟥 紅色框 (熊市)**：賣掉 QQQ，去排行榜找 **前 3 名** 避險。

    ### 4. 💎 半導體深層雷達 (Tab 5) - 【看馬力】(NEW!)
    * **定位**：影片核心算法，判斷半導體是否跑贏全世界。
    * **怎麼看**：
        * **強度 (RS) > 1**：🔥 強於大盤 (火車頭)，適合進攻。
        * **強度 (RS) < 1**：🐢 弱於大盤 (拖油瓶)，建議避開。
    """)

# === 1. 建立超級對照表 ===
name_map = {
    # 風險雷達
    "^SOX": "費城半導體", "BTC-USD": "比特幣", "HG=F": "銅期貨", "AUDJPY=X": "澳幣/日圓",
    "DX-Y.NYB": "美元指數", "GC=F": "黃金期貨", "JPY=X": "美元/日圓", "^VIX": "VIX恐慌",
    "^TWII": "台灣加權", "0050.TW": "元大台灣50", "^GSPC": "S&P 500", "^N225": "日經225",
    "^TNX": "美債10年殖利", "HYG": "高收益債", "TLT": "美債20年",
    
    # 宏觀配置
    "VTI": "美股全市場", "DBB": "工業金屬", "XLE": "能源類股",
    "DBA": "農產品", "DOG": "放空道瓊", "000001.SS": "上證指數", "LQD": "投資級債",

    # 輪動策略
    "QQQ": "科技股 (QQQ)", "UUP": "美元ETF (UUP)", "GLD": "黃金ETF (GLD)",
    
    # 半導體雷達 (新增)
    "URTH": "MSCI世界指數 (全球基準)", 
    "2330.TW": "台積電 (2330)", 
    "NVDA": "輝達 (NVIDIA)", 
    "AVGO": "博通 (Broadcom)",
    "AMD": "超微 (AMD)",
    "TSM": "台積電 ADR"
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

assets_rotation = ["QQQ", "HYG", "UUP", "BTC-USD", "GLD", "XLE", "DBA"]

# 半導體雷達清單
assets_semi = ["^SOX", "2330.TW", "NVDA", "TSM", "AMD", "AVGO", "^TWII"]

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
            df = yf.download(ticker, period="6mo", progress=False)
            if not df.empty:
                price = df['Close'].iloc[-1]
                if isinstance(price, pd.Series): price = price.item()
                
                ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
                if isinstance(ma20, pd.Series): ma20 = ma20.item()
                bias = (price - ma20) / ma20 * 100
                trend_status = "🔴強勢" if bias > 0 else "🟢弱勢"
                
                ma60 = df['Close'].rolling(window=60).mean().iloc[-1]
                if isinstance(ma60, pd.Series): ma60 = ma60.item()
                
                rsi_series = calculate_rsi(df['Close'])
                rsi = rsi_series.iloc[-1]
                if isinstance(rsi, pd.Series): rsi = rsi.item()
                rsi_status = "🔥過熱" if rsi > 70 else ("❄️超賣" if rsi < 30 else "☁️")
                
                if len(df) > 60:
                    price_q = df['Close'].iloc[-60]
                    if isinstance(price_q, pd.Series): price_q = price_q.item()
                    q_mom = (price - price_q) / price_q * 100
                else: q_mom = 0
                
                mom_str = f"{round(q_mom, 2)}%"
                if q_mom > 0: mom_str = f"🔴 +{mom_str}"
                else: mom_str = f"🟢 {mom_str}"

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
tab1, tab2, tab3, tab5, tab4 = st.tabs(["🚀 市場風險雷達", "🌐 宏觀資產配置", "🔄 類股輪動模擬", "💎 半導體雷達", "📈 趨勢檢視器"])

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

# --- Tab 3: 類股輪動 ---
with tab3:
    st.subheader("🔄 七大資產輪動策略模擬")
    df_rotate = get_data(assets_rotation)
    qqq_row = df_rotate[df_rotate['代號'] == 'QQQ']
    
    if not qqq_row.empty:
        qqq_score = qqq_row['宏觀分數'].values[0]
        st.divider()
        col_score, col_signal = st.columns([1, 2])
        with col_score:
            st.metric("科技股 (QQQ) 宏觀分數", f"{qqq_score} 分")
        with col_signal:
            if qqq_score >= 60:
                st.success(f"### 🐂 判定：牛市攻擊模式\n**建議**：持有 **科技股 (QQQ)**。")
            else:
                st.error(f"### 🐻 判定：熊市避險模式\n**建議**：分散至 **債、匯、金** 等高分資產。")

    st.divider()
    st.write("**📊 戰力排行榜**")
    df_rotate = df_rotate.sort_values(by="宏觀分數", ascending=False)
    def highlight_qqq(row):
        return ['background-color: #e6f3ff' if row['代號'] == 'QQQ' else '' for _ in row]
    st.dataframe(df_rotate[["代號", "資產名稱", "宏觀分數", "季動能 (3個月)", "RSI訊號"]].style.apply(highlight_qqq, axis=1), hide_index=True, use_container_width=True)

# --- Tab 5: 半導體雷達 (NEW) ---
with tab5:
    st.subheader("💎 半導體相對強度雷達 (Relative Strength)")
    st.markdown("邏輯：**半導體漲幅 / 全球股市(URTH)漲幅**。數值 > 1 代表跑贏大盤 (強勢)。")
    
    # 1. 下載基準資料 (全球股市)
    world_df = yf.download("URTH", period="6mo", progress=False)['Close']
    
    # 2. 計算半導體個股的相對強度
    semi_results = []
    for ticker in assets_semi:
        try:
            target_df = yf.download(ticker, period="6mo", progress=False)['Close']
            
            # 計算近一季 (60天) 漲幅
            ret_target = (target_df.iloc[-1] - target_df.iloc[-60]) / target_df.iloc[-60]
            ret_world = (world_df.iloc[-1] - world_df.iloc[-60]) / world_df.iloc[-60]
            
            # 相對強度公式：(1+個股漲幅) / (1+全球漲幅)
            rs_ratio = (1 + ret_target) / (1 + ret_world)
            
            # 判斷
            if rs_ratio > 1:
                status = "🔥 強於大盤"
                color_code = "background-color: #ffe6e6" # 淺紅
            else:
                status = "🐢 弱於大盤"
                color_code = "background-color: #e6ffe6" # 淺綠
                
            ch_name = name_map.get(ticker, ticker)
            
            semi_results.append({
                "代號": ticker,
                "資產名稱": ch_name,
                "強度 (RS值)": round(rs_ratio, 4),
                "半導體漲幅": f"{round(ret_target*100, 2)}%",
                "全球漲幅": f"{round(ret_world*100, 2)}%",
                "狀態": status,
                "_color": color_code # 藏一個顏色欄位
            })
        except: pass
        
    df_semi = pd.DataFrame(semi_results)
    df_semi = df_semi.sort_values(by="強度 (RS值)", ascending=False)
    
    # 3. 顯示指標 (以費半為準)
    sox_row = df_semi[df_semi['代號'] == '^SOX']
    if not sox_row.empty:
        sox_rs = sox_row['強度 (RS值)'].values[0]
        st.divider()
        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric("費城半導體 RS強度", sox_rs)
        with c2:
            if sox_rs > 1:
                st.success("### 🚀 半導體為市場主流\n目前費半跑贏全球股市，趨勢向上。")
            else:
                st.warning("### ⚠️ 半導體轉弱\n目前費半落後全球股市，需留意回檔風險。")
    
    # 4. 顯示表格 (帶顏色)
    st.divider()
    st.write("**📊 半導體成分股戰力掃描**")
    
    def color_rows(row):
        # 讀取隱藏的顏色欄位來上色
        return [row['_color'] for _ in row]
    
    # 顯示時把顏色欄位藏起來，但用它來畫色
    st.dataframe(
        df_semi.style.apply(color_rows, axis=1),
        column_config={"_color": None}, # 隱藏輔助欄
        hide_index=True, 
        use_container_width=True
    )

# --- Tab 4: 走勢圖 ---
with tab4:
    st.subheader("📈 資產趨勢檢視")
    all_keys = list(name_map.keys()) + ["QQQ", "UUP", "GLD", "URTH"]
    all_keys = list(set(all_keys))
    opts = [f"{name_map.get(k, k)} ({k})" for k in all_keys]
    sel = st.selectbox("選擇商品：", opts)
    if sel:
        code = sel.split("(")[-1].replace(")", "")
        try:
            df = yf.download(code, period="6mo", progress=False)
            st.line_chart(df['Close'])
        except: st.write("無圖表")