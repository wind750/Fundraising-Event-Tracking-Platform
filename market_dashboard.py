import streamlit as st
import yfinance as yf
import pandas as pd

# === 設定網頁格式 ===
st.set_page_config(page_title="全球金融戰情室", layout="wide")
st.title("🌐 全球金融戰情室 (穩定旗艦版)")
st.markdown("整合 **風險預警**、**資產配置**、**輪動策略** 與 **半導體深層雷達**")

# === 📖 新手指南 ===
with st.expander("📖 新手指南：如何一眼判讀？ (點擊展開)"):
    st.markdown("""
    ### 1. 🚀 市場風險雷達 (Tab 1) - 【看天氣】
    * **全紅 🔴** = 晴天 (安心持有) | **全綠 🟢** = 雨天 (現金為王)。
    
    ### 2. 🌐 宏觀資產配置 (Tab 2) - 【看季節】
    * **強勢區**：若持續 **🔴 紅色**，代表主流沒變。
    * **弱勢區**：若轉紅，代表資金輪動尋找新機會。

    ### 3. 🔄 類股輪動模擬 (Tab 3) - 【看指令】
    * **🟩 綠色框 (牛市)**：資金集中買 **科技股 (QQQ)**。
    * **🟥 紅色框 (熊市)**：賣掉 QQQ，去排行榜找 **前 3 名** 避險。

    ### 4. 💎 半導體深層雷達 (Tab 5) - 【看馬力】
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
    
    # 半導體雷達 (改用 ETF)
    "SPY": "標普500 ETF (全球基準)", 
    "SOXX": "費半 ETF (SOXX)",
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

# 半導體雷達清單 (改用 SOXX 和 SPY)
assets_semi_tickers = ["SOXX", "2330.TW", "NVDA", "TSM", "AMD", "AVGO", "^TWII"]
benchmark_ticker = "SPY" # 基準改用 SPY

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
            tnx_df = yf.download("^TNX", period="5d", progress=False)
            if not tnx_df.empty:
                tnx_val = tnx_df['Close'].iloc[-1]
                if isinstance(tnx_val, pd.Series): tnx_val = tnx_val.item()
                st.metric("殖利率 (高=不利科技股)", f"{round(tnx_val, 2)}%")
            else:
                st.write("暫無數據")
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
    if not df_rotate.empty:
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
    else:
        st.warning("⚠️ 暫無輪動數據")

# --- Tab 5: 半導體雷達 (一次下載版) ---
with tab5:
    st.subheader("💎 半導體相對強度雷達 (Relative Strength)")
    st.markdown(f"邏輯：**半導體漲幅 / 標普500 ({benchmark_ticker}) 漲幅**。數值 > 1 代表跑贏大盤 (強勢)。")
    
    # 1. 一次下載所有資料 (Bulk Download) - 避免迴圈被擋
    all_tickers = assets_semi_tickers + [benchmark_ticker]
    
    try:
        # 下載所有數據
        raw_data = yf.download(all_tickers, period="6mo", progress=False)
        
        # 處理資料結構 (yfinance 有時會回傳 MultiIndex)
        if 'Close' in raw_data.columns:
            data_closes = raw_data['Close']
        else:
            data_closes = raw_data # 萬一結構不同
            
        # 檢查基準數據是否存在
        if benchmark_ticker in data_closes.columns:
            bench_series = data_closes[benchmark_ticker].dropna()
            
            if not bench_series.empty:
                # 計算基準漲幅
                bench_ret = (bench_series.iloc[-1] - bench_series.iloc[-60]) / bench_series.iloc[-60]
                
                semi_results = []
                for ticker in assets_semi_tickers:
                    if ticker in data_closes.columns:
                        target_series = data_closes[ticker].dropna()
                        if not target_series.empty and len(target_series) > 60:
                            # 計算個股漲幅
                            target_ret = (target_series.iloc[-1] - target_series.iloc[-60]) / target_series.iloc[-60]
                            
                            # 計算 RS
                            rs_ratio = (1 + target_ret) / (1 + bench_ret)
                            
                            status = "🔥 強於大盤" if rs_ratio > 1 else "🐢 弱於大盤"
                            color_code = "background-color: #ffe6e6" if rs_ratio > 1 else "background-color: #e6ffe6"
                            ch_name = name_map.get(ticker, ticker)
                            
                            semi_results.append({
                                "代號": ticker,
                                "資產名稱": ch_name,
                                "強度 (RS值)": round(rs_ratio, 4),
                                "漲幅": f"{round(target_ret*100, 2)}%",
                                "狀態": status,
                                "_color": color_code
                            })
                
                # 顯示結果
                if semi_results:
                    df_semi = pd.DataFrame(semi_results).sort_values(by="強度 (RS值)", ascending=False)
                    
                    # 指標顯示 (費半 SOXX)
                    sox_row = df_semi[df_semi['代號'] == 'SOXX']
                    if not sox_row.empty:
                        sox_rs = sox_row['強度 (RS值)'].values[0]
                        st.divider()
                        c1, c2 = st.columns([1, 2])
                        with c1:
                            st.metric("費半ETF (SOXX) 強度", sox_rs)
                        with c2:
                            if sox_rs > 1:
                                st.success("### 🚀 半導體跑贏大盤\n資金集中在半導體，多頭趨勢明確。")
                            else:
                                st.warning("### ⚠️ 半導體跑輸大盤\n半導體表現不如標普500，留意修正風險。")
                    
                    # 表格顯示
                    st.divider()
                    def color_rows(row):
                        return [row['_color'] for _ in row]
                    st.dataframe(df_semi.style.apply(color_rows, axis=1), column_config={"_color": None}, hide_index=True, use_container_width=True)
                else:
                    st.warning("⚠️ 下載成功但數據不足 (可能上市時間太短)")
            else:
                st.error("⚠️ 基準指數 (SPY) 數據不足")
        else:
            st.error(f"⚠️ 無法取得基準指數 ({benchmark_ticker})，請稍後重試")
            
    except Exception as e:
        st.error(f"數據下載失敗，請檢查網路或稍後重試: {e}")

# --- Tab 4: 走勢圖 ---
with tab4:
    st.subheader("📈 資產趨勢檢視")
    all_keys = list(name_map.keys()) + ["QQQ", "UUP", "GLD", "SPY", "SOXX"]
    all_keys = list(set(all_keys))
    opts = [f"{name_map.get(k, k)} ({k})" for k in all_keys]
    sel = st.selectbox("選擇商品：", opts)
    if sel:
        code = sel.split("(")[-1].replace(")", "")
        try:
            df = yf.download(code, period="6mo", progress=False)
            st.line_chart(df['Close'])
        except: st.write("無圖表")