import streamlit as st
import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime

# === 設定網頁格式 ===
st.set_page_config(page_title="全球金融戰情室", layout="wide")
st.title("🌐 全球金融戰情室 (台股實戰版)")

# === 🕒 顯示台灣時間 ===
tw_tz = pytz.timezone('Asia/Taipei')
current_time = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"🕒 最後更新時間 (台灣): {current_time}")

st.markdown("整合 **台股戰略**、**風險預警**、**半導體雷達** 與 **資產輪動**")

# === 📖 新手指南 (新增實戰心法) ===
with st.expander("📖 新手指南：操盤手心法與判讀 (點擊展開)"):
    st.markdown("""
    ### 💡 戰情室使用心法 (Flow of Operations)：
    這不是隨機排列的數據，而是一套 **「從下單到確認」** 的決策流程：
    1. **先看行動 (Tab 1)**：台股今天能不能做？(結論優先：4燈全紅就衝，綠燈就縮)
    2. **再看環境 (Tab 2)**：全球現在是晴天還雨天？(雙重確認：有沒有突發風險)
    3. **檢查引擎 (Tab 3)**：半導體馬力夠不夠？(確認上漲純度：是真拉還是假拉)
    4. **找尋備案 (Tab 4)**：如果不買電子股，資金去哪了？(尋找避險或落後補漲)
    5. **確認大局 (Tab 5)**：長線趨勢有沒有改變？(心裡有底)
    6. **最後照鏡子 (Tab 6)**：下單前看K線圖確認。

    ---
    ### 🚦 各頁面判讀速查：
    * **Tab 1 台股戰略**：**4 燈全亮紅燈** = 資金鬆 (美元跌) + 動能強 (半導體漲) = **強力買點**。
    * **Tab 2 風險雷達**：**全紅 🔴** = 晴天 (安心持有) | **全綠 🟢** = 雨天 (現金為王)。
    * **Tab 3 半導體雷達**：**強度 > 1** = 半導體跑贏全球，台股火車頭馬力足。
    * **Tab 4 輪動策略**：**紅框** = 做多科技股 | **綠框** = 資金轉進債/匯/金。
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

    # 台股戰略
    "^TWOII": "櫃買指數" 
}

# === 2. 定義資產清單 ===
assets_tw_strategy = ["SOXX", "^TWOII", "DX-Y.NYB", "^TNX"]
assets_radar = {"1. 🚀 領先指標": ["^SOX", "BTC-USD", "HG=F", "AUDJPY=X"], "2. 🛡️ 避險資產": ["DX-Y.NYB", "GC=F", "JPY=X", "^VIX"], "3. 📉 股市現況": ["^TWII", "0050.TW", "^GSPC", "^N225"]}
assets_semi_tickers = ["SOXX", "2330.TW", "NVDA", "TSM", "AMD", "AVGO", "^TWII"]
benchmark_ticker = "SPY"
assets_rotation = ["QQQ", "HYG", "UUP", "BTC-USD", "GLD", "XLE", "DBA"]
assets_macro = {"1. 🔥 強勢動能觀察": ["VTI", "DBB", "XLE", "GC=F"], "2. ❄️ 弱勢動能觀察": ["DBA", "BTC-USD", "DOG"], "3. 🌏 核心市場": ["^GSPC", "000001.SS", "^TWII", "0050.TW"], "4. 🏦 利率與債券": ["^TNX", "TLT", "LQD"]}

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
                if price > ma20: score += 40 
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
tab_tw, tab_risk, tab_semi, tab_rotate, tab_macro, tab_chart = st.tabs([
    "🇹🇼 台股戰略", "🚀 風險雷達", "💎 半導體雷達", "🔄 輪動策略", "🌐 資產配置", "📈 趨勢圖"
])

# --- Tab 1: 台股戰略 ---
with tab_tw:
    st.subheader("🇹🇼 台股四大領先指標 (戰略指揮部)")
    st.markdown("邏輯：**資金源頭 (美元/美債) 跌** + **市場動能 (半導體/內資) 漲** = **4燈全紅強力買點**")
    
    df_tw = get_data(assets_tw_strategy)
    
    if not df_tw.empty:
        c1, c2, c3, c4 = st.columns(4)
        score_tw = 0 
        
        with c1:
            row = df_tw[df_tw['代號'] == 'SOXX']
            if not row.empty:
                bias = row['乖離率'].values[0]
                is_good = bias > 0
                if is_good: score_tw += 1
                st.metric("1. 半導體 (SOXX)", f"{row['現價'].values[0]}", f"{round(bias, 2)}% (乖離)", delta_color="normal" if is_good else "inverse")
                st.caption("🔴 動能強" if is_good else "🟢 動能弱")
        with c2:
            row = df_tw[df_tw['代號'] == '^TWOII']
            if not row.empty:
                bias = row['乖離率'].values[0]
                is_good = bias > 0
                if is_good: score_tw += 1
                st.metric("2. 內資 (櫃買)", f"{row['現價'].values[0]}", f"{round(bias, 2)}% (乖離)", delta_color="normal" if is_good else "inverse")
                st.caption("🔴 信心強" if is_good else "🟢 信心弱")
        with c3:
            row = df_tw[df_tw['代號'] == 'DX-Y.NYB']
            if not row.empty:
                bias = row['乖離率'].values[0]
                is_good = bias < 0 
                if is_good: score_tw += 1
                st.metric("3. 美元 (源頭)", f"{row['現價'].values[0]}", f"{round(bias, 2)}% (乖離)", delta_color="inverse")
                st.caption("🔴 資金鬆" if is_good else "🟢 資金緊")
        with c4:
            row = df_tw[df_tw['代號'] == '^TNX']
            if not row.empty:
                bias = row['乖離率'].values[0]
                is_good = bias < 0
                if is_good: score_tw += 1
                st.metric("4. 美債 (利率)", f"{row['現價'].values[0]}%", f"{round(bias, 2)}% (乖離)", delta_color="inverse")
                st.caption("🔴 壓力小" if is_good else "🟢 壓力大")
        
        st.divider()
        st.subheader(f"🚦 戰略總結：{score_tw} / 4 分")
        if score_tw == 4: st.error("### 🚀 火力全開 (Strong Buy)\n四大指標全數配合，台股最佳進場點。")
        elif score_tw == 3: st.warning("### 🌤️ 偏多操作 (Buy)\n大環境有利，拉回找買點。")
        elif score_tw == 2: st.info("### ☁️ 多空拉鋸 (Hold)\n建議區間操作，不追高。")
        else: st.success("### 🌧️ 保守防禦 (Sell/Wait)\n利空罩頂，建議保留現金。")
    else: st.write("讀取中...")

# --- Tab 2: 風險雷達 ---
with tab_risk:
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
            if not tnx_df.empty:
                val = tnx_df['Close'].iloc[-1]
                if isinstance(val, pd.Series): val = val.item()
                st.metric("美債殖利率", f"{round(val, 2)}%")
            else: st.write("暫無數據")
        except: st.write("讀取中...")
    with k2:
        try:
            data = yf.download(["HYG", "TLT"], period="3mo", progress=False)['Close'].dropna()
            if not data.empty:
                curr = (data['HYG']/data['TLT']).iloc[-1]
                msg = "🔴 貪婪 (利多)" if curr > (data['HYG']/data['TLT']).rolling(20).mean().iloc[-1] else "🟢 恐慌 (利空)"
                st.metric("風險胃口 (HYG/TLT)", round(curr, 4), msg)
        except: st.write("讀取中...")

# --- Tab 3: 半導體雷達 ---
with tab_semi:
    st.subheader("💎 半導體相對強度雷達")
    st.markdown(f"邏輯：**半導體漲幅 / 標普500 ({benchmark_ticker}) 漲幅**。數值 > 1 代表跑贏大盤。")
    st.caption("📈 漲幅基準：過去 60 個交易日 (約一季)。")
    all_tickers = assets_semi_tickers + [benchmark_ticker]
    try:
        raw_data = yf.download(all_tickers, period="6mo", progress=False)
        if 'Close' in raw_data.columns: data_closes = raw_data['Close']
        else: data_closes = raw_data 
        if benchmark_ticker in data_closes.columns:
            bench_series = data_closes[benchmark_ticker].dropna()
            if not bench_series.empty and len(bench_series) > 60:
                bench_ret = (bench_series.iloc[-1] - bench_series.iloc[-60]) / bench_series.iloc[-60]
                semi_results = []
                for ticker in assets_semi_tickers:
                    if ticker in data_closes.columns:
                        target_series = data_closes[ticker].dropna()
                        if not target_series.empty and len(target_series) > 60:
                            target_ret = (target_series.iloc[-1] - target_series.iloc[-60]) / target_series.iloc[-60]
                            rs_ratio = (1 + target_ret) / (1 + bench_ret)
                            status = "🔥 強" if rs_ratio > 1 else "🐢 弱"
                            color_code = "background-color: #ffe6e6" if rs_ratio > 1 else "background-color: #e6ffe6"
                            ch_name = name_map.get(ticker, ticker)
                            semi_results.append({"代號": ticker, "資產名稱": ch_name, "強度 (RS值)": round(rs_ratio, 4), "漲幅": f"{round(target_ret*100, 2)}%", "狀態": status, "_color": color_code})
                if semi_results:
                    df_semi = pd.DataFrame(semi_results).sort_values(by="強度 (RS值)", ascending=False)
                    sox_row = df_semi[df_semi['代號'] == 'SOXX']
                    if not sox_row.empty:
                        sox_rs = sox_row['強度 (RS值)'].values[0]
                        st.divider()
                        c1, c2 = st.columns([1, 2])
                        with c1: st.metric("費半ETF (SOXX) 強度", sox_rs)
                        with c2:
                            if sox_rs > 1: st.success("### 🚀 半導體跑贏大盤")
                            else: st.warning("### ⚠️ 半導體跑輸大盤")
                    st.divider()
                    def color_rows(row): return [row['_color'] for _ in row]
                    st.dataframe(df_semi.style.apply(color_rows, axis=1), column_config={"_color": None}, hide_index=True, use_container_width=True)
                else: st.warning("無數據")
            else: st.error("基準數據不足")
        else: st.error("基準數據缺失")
    except Exception as e: st.error(f"下載失敗: {e}")

# --- Tab 4: 輪動策略 ---
with tab_rotate:
    st.subheader("🔄 七大資產輪動策略")
    df_rotate = get_data(assets_rotation)
    if not df_rotate.empty:
        qqq = df_rotate[df_rotate['代號'] == 'QQQ']
        if not qqq.empty:
            score = qqq['宏觀分數'].values[0]
            if score >= 60: st.error(f"### 🐂 牛市攻擊 (紅漲)\n建議：持有 **科技股 (QQQ)**。")
            else: st.success(f"### 🐻 熊市避險 (綠跌)\n建議：分散至 **債、匯、金**。")
        st.dataframe(df_rotate[["代號", "資產名稱", "宏觀分數"]].sort_values("宏觀分數", ascending=False), hide_index=True, use_container_width=True)
    else: st.warning("暫無數據")

# --- Tab 5: 宏觀配置 ---
with tab_macro:
    st.subheader("中長期資產配置")
    c1, c2 = st.columns(2)
    with c1: st.dataframe(get_data(assets_macro["1. 🔥 強勢動能觀察"])[["資產名稱", "季動能 (3個月)"]], hide_index=True, use_container_width=True)
    with c2: st.dataframe(get_data(assets_macro["2. ❄️ 弱勢動能觀察"])[["資產名稱", "季動能 (3個月)"]], hide_index=True, use_container_width=True)
    st.divider()
    c3, c4 = st.columns(2)
    with c3: st.dataframe(get_data(assets_macro["3. 🌏 核心市場"])[["資產名稱", "季動能 (3個月)"]], hide_index=True, use_container_width=True)
    with c4: st.dataframe(get_data(assets_macro["4. 🏦 利率與債券"])[["資產名稱", "季動能 (3個月)"]], hide_index=True, use_container_width=True)

# --- Tab 6: 趨勢圖 ---
with tab_chart:
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


