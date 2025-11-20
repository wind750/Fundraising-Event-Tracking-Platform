import streamlit as st
import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime

# === 設定網頁格式 ===
st.set_page_config(page_title="全球金融戰情室", layout="wide")
st.title("🌐 全球金融戰情室 (完全體旗艦版)")

# === 🕒 顯示台灣時間 ===
tw_tz = pytz.timezone('Asia/Taipei')
current_time = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"🕒 最後更新時間 (台灣): {current_time}")

st.markdown("整合 **風險預警**、**資產配置**、**輪動策略**、**半導體雷達** 與 **台股戰略指標**")

# === 📖 新手指南 (新增 Tab 6 說明) ===
with st.expander("📖 新手指南：如何一眼判讀？ (點擊展開)"):
    st.markdown("""
    ### 1. 🚀 市場風險雷達 (Tab 1) - 【看天氣】
    * **全紅 🔴** = 晴天 | **全綠 🟢** = 雨天。
    
    ### 2. 🌐 宏觀資產配置 (Tab 2) - 【看季節】
    * **強勢區**：持續紅燈代表主流沒變。
    
    ### 3. 🔄 類股輪動模擬 (Tab 3) - 【看指令】
    * **🟥 紅色框 (牛市)**：買科技股 (QQQ)。
    * **🟩 綠色框 (熊市)**：避險。

    ### 4. 💎 半導體深層雷達 (Tab 5) - 【看馬力】
    * **強度 > 1**：半導體是火車頭 (強)。

    ### 5. 🇹🇼 台股戰略指揮部 (Tab 6) - 【看信號】 (NEW!)
    * **邏輯 (圖990)**：整合半導體、櫃買(內資)、美元(資金源)、美債(利率) 四大指標。
    * **判讀**：
        * **半導體/櫃買**：要 **漲** (🔴) 才好。
        * **美元/美債**：要 **跌** (🔴) 才好 (反向指標)。
        * **總結**：**4 個燈全亮紅燈** = 台股最強買點。
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
    
    # 半導體雷達
    "SPY": "標普500 ETF", "SOXX": "費半 ETF",
    "2330.TW": "台積電", "NVDA": "輝達", "AVGO": "博通", "AMD": "超微", "TSM": "台積電ADR",

    # 台股戰略 (Tab 6)
    "00733.TW": "富邦中小 (櫃買代理)" 
}

# === 2. 定義資產清單 ===
# ... (既有清單保持不變)
assets_radar = {"1. 🚀 領先指標": ["^SOX", "BTC-USD", "HG=F", "AUDJPY=X"], "2. 🛡️ 避險資產": ["DX-Y.NYB", "GC=F", "JPY=X", "^VIX"], "3. 📉 股市現況": ["^TWII", "0050.TW", "^GSPC", "^N225"]}
assets_macro = {"1. 🔥 強勢動能觀察": ["VTI", "DBB", "XLE", "GC=F"], "2. ❄️ 弱勢動能觀察": ["DBA", "BTC-USD", "DOG"], "3. 🌏 核心市場": ["^GSPC", "000001.SS", "^TWII", "0050.TW"], "4. 🏦 利率與債券": ["^TNX", "TLT", "LQD"]}
assets_rotation = ["QQQ", "HYG", "UUP", "BTC-USD", "GLD", "XLE", "DBA"]
assets_semi_tickers = ["SOXX", "2330.TW", "NVDA", "TSM", "AMD", "AVGO", "^TWII"]
benchmark_ticker = "SPY"

# 台股戰略清單 (圖片 990 的四大天王)
# 櫃買指數 Yahoo 抓不到，改用 00733 (中小股ETF) 代表內資信心
assets_tw_strategy = ["SOXX", "00733.TW", "DX-Y.NYB", "^TNX"] 

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
                if price > ma20: score += 40 # 改用月線更靈敏
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
                    "現價": round(price, 2),
                    "乖離率": bias
                })
        except: pass
    return pd.DataFrame(results)

# === 4. 介面分頁 ===
tab1, tab2, tab3, tab5, tab6, tab4 = st.tabs(["🚀 風險雷達", "🌐 資產配置", "🔄 輪動模擬", "💎 半導體雷達", "🇹🇼 台股戰略", "📈 趨勢圖"])

# --- Tab 1~3 & 5 (保持不變，僅簡化代碼以節省篇幅，功能與之前一致) ---
# (為確保完整性，這裡重複關鍵邏輯，您可以直接覆蓋舊檔)

with tab1:
    st.subheader("短線資金流向與風險預警")
    c1, c2, c3 = st.columns(3)
    with c1: st.write("**1. 領先指標**"); st.dataframe(get_data(assets_radar["1. 🚀 領先指標"])[["資產名稱", "趨勢 (月線)", "RSI訊號"]], hide_index=True, use_container_width=True)
    with c2: st.write("**2. 避險資產**"); st.dataframe(get_data(assets_radar["2. 🛡️ 避險資產"])[["資產名稱", "趨勢 (月線)", "RSI訊號"]], hide_index=True, use_container_width=True)
    with c3: st.write("**3. 股市現況**"); st.dataframe(get_data(assets_radar["3. 📉 股市現況"])[["資產名稱", "趨勢 (月線)", "RSI訊號"]], hide_index=True, use_container_width=True)
    st.divider()
    k1, k2 = st.columns(2)
    with k1:
        try:
            tnx_df = yf.download("^TNX", period="5d", progress=False)
            st.metric("美債殖利率", f"{round(tnx_df['Close'].iloc[-1].item(), 2)}%")
        except: st.write("讀取中...")
    with k2:
        try:
            data = yf.download(["HYG", "TLT"], period="3mo", progress=False)['Close'].dropna()
            curr = (data['HYG']/data['TLT']).iloc[-1]
            msg = "🔴 貪婪 (利多)" if curr > (data['HYG']/data['TLT']).rolling(20).mean().iloc[-1] else "🟢 恐慌 (利空)"
            st.metric("風險胃口 (HYG/TLT)", round(curr, 4), msg)
        except: st.write("讀取中...")

with tab2:
    st.subheader("中長期資產配置")
    c1, c2 = st.columns(2)
    with c1: st.dataframe(get_data(assets_macro["1. 🔥 強勢動能觀察"])[["資產名稱", "季動能 (3個月)"]], hide_index=True, use_container_width=True)
    with c2: st.dataframe(get_data(assets_macro["2. ❄️ 弱勢動能觀察"])[["資產名稱", "季動能 (3個月)"]], hide_index=True, use_container_width=True)
    st.divider()
    c3, c4 = st.columns(2)
    with c3: st.dataframe(get_data(assets_macro["3. 🌏 核心市場"])[["資產名稱", "季動能 (3個月)"]], hide_index=True, use_container_width=True)
    with c4: st.dataframe(get_data(assets_macro["4. 🏦 利率與債券"])[["資產名稱", "季動能 (3個月)"]], hide_index=True, use_container_width=True)

with tab3:
    st.subheader("🔄 七大資產輪動策略")
    df_rotate = get_data(assets_rotation)
    if not df_rotate.empty:
        qqq = df_rotate[df_rotate['代號'] == 'QQQ']
        if not qqq.empty:
            score = qqq['宏觀分數'].values[0]
            if score >= 60: st.error(f"### 🐂 牛市攻擊 (紅漲)\n建議：持有 **科技股 (QQQ)**。")
            else: st.success(f"### 🐻 熊市避險 (綠跌)\n建議：分散至 **債、匯、金**。")
        st.dataframe(df_rotate[["代號", "資產名稱", "宏觀分數"]].sort_values("宏觀分數", ascending=False), hide_index=True, use_container_width=True)

with tab5:
    st.subheader("💎 半導體相對強度")
    try:
        raw = yf.download(assets_semi_tickers + [benchmark_ticker], period="6mo", progress=False)['Close']
        if benchmark_ticker in raw.columns:
            bench = raw[benchmark_ticker].dropna()
            bench_ret = (bench.iloc[-1] - bench.iloc[-60])/bench.iloc[-60]
            res = []
            for t in assets_semi_tickers:
                if t in raw.columns:
                    tgt = raw[t].dropna()
                    if not tgt.empty:
                        tgt_ret = (tgt.iloc[-1]-tgt.iloc[-60])/tgt.iloc[-60]
                        rs = (1+tgt_ret)/(1+bench_ret)
                        status = "🔥 強" if rs > 1 else "🐢 弱"
                        clr = "background-color: #ffe6e6" if rs > 1 else "background-color: #e6ffe6"
                        res.append({"代號":t, "名稱":name_map.get(t,t), "強度":round(rs,4), "漲幅":f"{round(tgt_ret*100,2)}%", "狀態":status, "_c":clr})
            df_s = pd.DataFrame(res).sort_values("強度", ascending=False)
            st.dataframe(df_s.style.apply(lambda x: [x['_c']]*len(x), axis=1), column_config={"_c":None}, hide_index=True, use_container_width=True)
    except: st.write("數據讀取中...")

# --- Tab 6: 台股戰略指揮部 (NEW!) ---
with tab6:
    st.subheader("🇹🇼 台股四大領先指標 (戰略指揮部)")
    st.markdown("""
    邏輯來源 (圖990)：**資金源頭 (美元/美債) vs 資金動能 (半導體/內資)**。
    * **資金閘門 (Source)**：美元與美債利率，**下跌 (🟢)** 代表資金寬鬆，有利台股。
    * **市場動能 (Use)**：半導體與櫃買指數，**上漲 (🔴)** 代表動能強勁，有利台股。
    """)
    
    # 1. 取得四大指標數據
    df_tw = get_data(assets_tw_strategy)
    
    if not df_tw.empty:
        # 2. 顯示四個儀表板
        c1, c2, c3, c4 = st.columns(4)
        
        score_tw = 0 # 台股信心分數 (滿分4分)
        
        # --- 指標 1: 半導體 (SOXX) ---
        with c1:
            row = df_tw[df_tw['代號'] == 'SOXX']
            if not row.empty:
                bias = row['乖離率'].values[0]
                val = row['現價'].values[0]
                # 判斷：站上月線(乖離率>0) = 強
                is_good = bias > 0
                status = "🔴 動能強 (利多)" if is_good else "🟢 動能弱 (保守)"
                if is_good: score_tw += 1
                st.metric("1. 半導體 (SOXX)", f"{val}", f"{round(bias, 2)}% (乖離)", delta_color="normal" if is_good else "inverse")
                st.caption(status)

        # --- 指標 2: 內資/櫃買 (00733) ---
        with c2:
            row = df_tw[df_tw['代號'] == '00733.TW']
            if not row.empty:
                bias = row['乖離率'].values[0]
                val = row['現價'].values[0]
                is_good = bias > 0
                status = "🔴 內資強 (利多)" if is_good else "🟢 內資逃 (保守)"
                if is_good: score_tw += 1
                st.metric("2. 內資信心 (櫃買)", f"{val}", f"{round(bias, 2)}% (乖離)", delta_color="normal" if is_good else "inverse")
                st.caption(status)

        # --- 指標 3: 美元指數 (DXY) - 反向 ---
        with c3:
            row = df_tw[df_tw['代號'] == 'DX-Y.NYB']
            if not row.empty:
                bias = row['乖離率'].values[0]
                val = row['現價'].values[0]
                # 判斷：跌破月線(乖離率<0) = 資金寬鬆 = 對台股好
                is_good = bias < 0 
                status = "🔴 資金鬆 (利多)" if is_good else "🟢 資金緊 (利空)"
                if is_good: score_tw += 1
                # 這裡 delta_color="inverse" 代表數值跌是綠色(美股慣例)，但我們文字標示利多
                st.metric("3. 美元指數 (源頭)", f"{val}", f"{round(bias, 2)}% (乖離)", delta_color="inverse")
                st.caption(status)

        # --- 指標 4: 美債利率 (TNX) - 反向 ---
        with c4:
            row = df_tw[df_tw['代號'] == '^TNX']
            if not row.empty:
                bias = row['乖離率'].values[0]
                val = row['現價'].values[0]
                # 判斷：跌破月線 = 壓力小 = 對台股好
                is_good = bias < 0
                status = "🔴 壓力小 (利多)" if is_good else "🟢 壓力大 (利空)"
                if is_good: score_tw += 1
                st.metric("4. 美債利率 (評價)", f"{val}%", f"{round(bias, 2)}% (乖離)", delta_color="inverse")
                st.caption(status)
        
        st.divider()
        
        # 3. 總結判定
        st.subheader(f"🚦 台股戰略總結：{score_tw} / 4 分")
        if score_tw == 4:
            st.error("### 🚀 火力全開 (Strong Buy)\n四大指標全數利多！半導體強、內資在、美元美債弱，這是台股最舒服的飆漲環境。")
        elif score_tw == 3:
            st.warning("### 🌤️ 偏多操作 (Buy)\n大環境有利，僅有一項指標未配合，拉回找買點。")
        elif score_tw == 2:
            st.info("### ☁️ 多空拉鋸 (Hold)\n資金面與基本面打架，建議區間操作，不要追高。")
        else:
            st.success("### 🌧️ 保守防禦 (Sell/Wait)\n多數指標呈現利空，資金緊縮或動能不足，建議保留現金。")
    
    else:
        st.write("數據讀取中...")

# --- Tab 4: 走勢圖 ---
with tab4:
    st.subheader("📈 資產趨勢檢視")
    all_keys = list(name_map.keys()) + ["QQQ", "UUP", "GLD", "SPY", "SOXX", "00733.TW"]
    all_keys = list(set(all_keys))
    opts = [f"{name_map.get(k, k)} ({k})" for k in all_keys]
    sel = st.selectbox("選擇商品：", opts)
    if sel:
        code = sel.split("(")[-1].replace(")", "")
        try:
            df = yf.download(code, period="6mo", progress=False)
            st.line_chart(df['Close'])
        except: st.write("無圖表")