import streamlit as st
import yfinance as yf
import pandas as pd
import pytz
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
# 2. 核心函數與設定
# ==========================================

# 快取下載函數
@st.cache_data(ttl=3600)
def fetch_data_cached(tickers, period="6mo"):
    try:
        data = yf.download(tickers, period=period, progress=False)
        return data
    except:
        return pd.DataFrame()

# 建立中英文對照表
name_map = {
    # AI 戰情
    "^IXIC": "納斯達克", "SMH": "半導體ETF", "^TWO": "櫃買指數",
    # 台股戰略
    "SOXX": "費半 ETF", "^TWOII": "櫃買(舊)", "00733.TW": "富邦中小", 
    "DX-Y.NYB": "美元指數", "^TNX": "美債10年殖利",
    # 風險雷達
    "^SOX": "費城半導體", "BTC-USD": "比特幣", "HG=F": "銅期貨", "AUDJPY=X": "澳幣/日圓",
    "GC=F": "黃金期貨", "JPY=X": "美元/日圓", "^VIX": "VIX恐慌",
    "^TWII": "台灣加權", "0050.TW": "元大台灣50", "^GSPC": "S&P 500", "^N225": "日經225",
    "HYG": "高收益債", "TLT": "美債20年", "LQD": "投資級債",
    "RSP": "S&P500 等權重", "SPY": "S&P500 市值權重",
    "VTI": "美股全市場", "DBB": "工業金屬", "XLE": "能源類股",
    "DBA": "農產品", "DOG": "放空道瓊", "000001.SS": "上證指數",
    # 輪動 & 半導體
    "QQQ": "科技股 (QQQ)", "UUP": "美元ETF", "GLD": "黃金ETF",
    "2330.TW": "台積電", "NVDA": "輝達", "AVGO": "博通", "AMD": "超微", "TSM": "台積電ADR",
    # 千金股 (增加更多高價股觀察名單，以免漏掉新科千金)
    "3661.TWO": "信驊", "3008.TW": "大立光", "3529.TWO": "力旺", 
    "3661.TW": "世芯-KY", "6669.TW": "緯穎", "5269.TWO": "祥碩", 
    "3443.TW": "創意", "2454.TW": "聯發科", "2059.TW": "川湖",
    "3533.TW": "嘉澤", "3131.TWO": "弘塑", "3653.TW": "健策", 
    "3293.TWO": "鈊象", "6409.TW": "旭隼", "8454.TW": "富邦媒",
    "6643.TW": "M31", "6415.TW": "矽力*-KY"
}

# 定義資產清單
assets_ai_risk = ["^IXIC", "^SOX", "^TWII", "^TWO", "SMH", "NVDA"]
assets_tw_strategy = ["SOXX", "^TWOII", "00733.TW", "DX-Y.NYB", "^TNX"]
assets_radar = {"1. 🚀 領先指標": ["^SOX", "BTC-USD", "HG=F", "AUDJPY=X"], "2. 🛡️ 避險資產": ["DX-Y.NYB", "GC=F", "JPY=X", "^VIX"], "3. 📉 股市現況": ["^TWII", "0050.TW", "^GSPC", "^N225"]}
assets_semi_tickers = ["SOXX", "2330.TW", "NVDA", "TSM", "AMD", "AVGO", "^TWII"]
benchmark_ticker = "SPY"
assets_rotation = ["QQQ", "HYG", "UUP", "BTC-USD", "GLD", "XLE", "DBA"]
assets_macro = {"1. 🔥 強勢動能觀察": ["VTI", "DBB", "XLE", "GC=F"], "2. ❄️ 弱勢動能觀察": ["DBA", "BTC-USD", "DOG"], "3. 🌏 核心市場": ["^GSPC", "000001.SS", "^TWII", "0050.TW"], "4. 🏦 利率與債券": ["^TNX", "TLT", "LQD"]}
assets_high_price = ["3661.TWO", "3008.TW", "3529.TWO", "3661.TW", "6669.TW", "5269.TWO", "3443.TW", "2454.TW", "2330.TW", "2059.TW", "3533.TW", "3131.TWO", "3653.TW", "3293.TWO", "6409.TW", "8454.TW", "6643.TW", "6415.TW"]
cnn_tickers = ["RSP", "SPY", "HYG", "LQD"]

# 萬用運算引擎
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_data_from_cache(ticker_list, cached_df):
    results = []
    if 'Close' in cached_df.columns: data = cached_df['Close']
    else: data = cached_df

    for ticker in ticker_list:
        try:
            if ticker in data.columns:
                series = data[ticker].dropna()
                if not series.empty:
                    price = series.iloc[-1]
                    ma20 = series.rolling(window=20).mean().iloc[-1]
                    bias = (price - ma20) / ma20 * 100
                    trend_status = "🔴強勢" if bias > 0 else "🟢弱勢"
                    
                    rsi_series = calculate_rsi(series)
                    rsi = rsi_series.iloc[-1]
                    rsi_status = "🔥過熱" if rsi > 70 else ("❄️超賣" if rsi < 30 else "☁️")
                    
                    if len(series) > 60: q_mom = (price - series.iloc[-60]) / series.iloc[-60] * 100
                    else: q_mom = 0
                    mom_str = f"🔴 +{round(q_mom, 2)}%" if q_mom > 0 else f"🟢 {round(q_mom, 2)}%"

                    score = 0
                    if bias > 0: score += 40
                    if q_mom > 0: score += 30
                    if rsi > 50: score += 30
                    
                    ch_name = name_map.get(ticker, ticker)
                    results.append({
                        "代號": ticker, "資產名稱": ch_name, "趨勢 (月線)": trend_status,
                        "RSI訊號": f"{rsi_status} ({int(rsi)})", "季動能 (3個月)": mom_str,
                        "宏觀分數": score, "現價": round(price, 2), "乖離率": bias
                    })
        except: pass
    return pd.DataFrame(results)

# ==========================================
# 3. 資料下載
# ==========================================
all_needed_tickers = list(set(
    assets_ai_risk + assets_tw_strategy + assets_semi_tickers + [benchmark_ticker] + 
    assets_rotation + assets_high_price + cnn_tickers + 
    [t for sublist in assets_radar.values() for t in sublist] +
    [t for sublist in assets_macro.values() for t in sublist] + 
    ["^VIX"]
))

cached_data = fetch_data_cached(all_needed_tickers, period="6mo")

# ==========================================
# 4. 介面分頁
# ==========================================
tab_ai, tab_tw, tab_risk, tab_semi, tab_rotate, tab_macro, tab_chart = st.tabs([
    "💀 AI 戰情", "🇹🇼 台股戰略", "🚀 風險雷達", "💎 半導體雷達", "🔄 輪動策略", "🌐 資產配置", "📈 趨勢圖"
])

# --- Tab 1: AI 戰情 ---
with tab_ai:
    st.subheader("💀 AI 資金掃描雷達")
    st.info("💡 **核心邏輯**：當 Tech Index (納斯達克、費半、台股...) 的 **「平均離差」** 同步小於零，代表趨勢團結向下。")
    
    tech_data = []
    total_bias = 0
    count = 0
    
    if not cached_data.empty:
        if 'Close' in cached_data.columns: ai_source = cached_data['Close']
        else: ai_source = cached_data
        
        for t in assets_ai_risk:
            if t in ai_source.columns:
                series = ai_source[t].dropna()
                if not series.empty:
                    price = series.iloc[-1]
                    ma20 = series.rolling(window=20).mean().iloc[-1]
                    if ma20 == 0: ma20 = price
                    bias = (price - ma20) / ma20 * 100
                    total_bias += bias
                    count += 1
                    status = "🔴 強勢" if bias > 0 else "🟢 弱勢"
                    tech_data.append({
                        "名稱": name_map.get(t, t),
                        "狀態": status,
                        "乖離率(%)": round(bias, 2),
                        "現價": round(price, 2)
                    })
            else:
                tech_data.append({"名稱": name_map.get(t, t), "狀態": "⚠️ N/A", "乖離率(%)": 0, "現價": 0})
    
    avg_bias = total_bias / count if count > 0 else 0
    
    c1, c2 = st.columns([1, 2])
    with c1:
        if avg_bias < 0:
            st.error("⚠️ **警報：全面翻負**")
            st.metric(
                label="Tech 平均離差", 
                value=f"{round(avg_bias, 2)}%", 
                delta=round(avg_bias, 2), 
                delta_color="inverse"
            )
        else:
            st.success("🔴 **多頭支撐**")
            st.metric(
                label="Tech 平均離差", 
                value=f"{round(avg_bias, 2)}%", 
                delta=round(avg_bias, 2), 
                delta_color="normal"
            )
    with c2:
        st.dataframe(pd.DataFrame(tech_data), hide_index=True, use_container_width=True)

# --- Tab 2: 台股戰略 (升級版) ---
with tab_tw:
    st.subheader("🇹🇼 台股四大領先指標")
    if not cached_data.empty:
        df_tw = get_data_from_cache(assets_tw_strategy, cached_data)
        if not df_tw.empty:
            c1, c2, c3, c4 = st.columns(4)
            score_tw = 0 
            
            def get_metric(df, ticker):
                row = df[df['代號'] == ticker]
                return row.iloc[0] if not row.empty else None

            with c1:
                r = get_metric(df_tw, 'SOXX')
                if r is not None:
                    good = r['乖離率'] > 0
                    if good: score_tw += 1
                    st.metric("1. 半導體 (SOXX)", f"{r['現價']}", f"{round(r['乖離率'], 2)}%", delta_color="normal" if good else "inverse")
            
            with c2:
                r = get_metric(df_tw, '^TWOII')
                name = "2. 內資 (櫃買)"
                if r is None: r = get_metric(df_tw, '00733.TW'); name = "2. 內資 (富邦中小)"
                if r is not None:
                    good = r['乖離率'] > 0
                    if good: score_tw += 1
                    st.metric(name, f"{r['現價']}", f"{round(r['乖離率'], 2)}%", delta_color="normal" if good else "inverse")
                else: st.metric("2. 內資", "無數據")

            with c3:
                r = get_metric(df_tw, 'DX-Y.NYB')
                if r is not None:
                    good = r['乖離率'] < 0
                    if good: score_tw += 1
                    st.metric("3. 美元 (源頭)", f"{r['現價']}", f"{round(r['乖離率'], 2)}%", delta_color="inverse")

            with c4:
                r = get_metric(df_tw, '^TNX')
                if r is not None:
                    good = r['乖離率'] < 0
                    if good: score_tw += 1
                    st.metric("4. 美債 (利率)", f"{r['現價']}%", f"{round(r['乖離率'], 2)}%", delta_color="inverse")
            
            st.divider()
            if score_tw == 4: st.error("### 🚀 火力全開 (4燈全紅)")
            elif score_tw == 3: st.warning("### 🌤️ 偏多操作 (3燈)")
            elif score_tw == 2: st.info("### ☁️ 多空拉鋸 (2燈)")
            else: st.success("### 🌧️ 保守防禦 (0-1燈)")

            # === 升級版：千金股信心溫度計 ===
            st.divider()
            st.subheader("👑 千金股信心溫度計")
            st.caption("追蹤股價 > 1000 元之高價股結構，代表主力大戶信心。")

            df_high_raw = get_data_from_cache(assets_high_price, cached_data)
            if not df_high_raw.empty:
                # 1. 篩選出真正的千金股 (股價 >= 1000)
                club_members = df_high_raw[df_high_raw['現價'] >= 1000].copy()
                club_count = len(club_members)

                if club_count > 0:
                    # 2. 計算強弱結構
                    # 強勢股：乖離率 > 0 (站上月線)
                    strong_members = club_members[club_members['乖離率'] > 0]
                    strong_count = len(strong_members)
                    weak_count = club_count - strong_count
                    strong_pct = strong_count / club_count

                    # 3. 計算族群平均乖離 (火力值)
                    avg_club_bias = club_members['乖離率'].mean()

                    # 4. 找出股王
                    king = club_members.loc[club_members['現價'].idxmax()]

                    # 5. 顯示數據
                    h1, h2, h3, h4 = st.columns(4)
                    
                    with h1:
                        st.metric("🏆 股王", f"{king['資產名稱']}", f"${int(king['現價'])}")
                    
                    with h2:
                        st.metric("💰 千金股家數", f"{club_count} 檔")

                    with h3:
                        # 顯示結構：強 vs 弱
                        st.metric(
                            "📊 多空結構 (強/弱)", 
                            f"{strong_count} 強 / {weak_count} 弱", 
                            f"佔比 {int(strong_pct*100)}%",
                            delta_color="off"
                        )
                    
                    with h4:
                        # 顯示火力：平均乖離
                        if avg_club_bias > 0:
                            st.metric("🔥 族群火力 (平均乖離)", f"+{round(avg_club_bias, 2)}%", "多方控盤", delta_color="normal")
                        else:
                            st.metric("❄️ 族群火力 (平均乖離)", f"{round(avg_club_bias, 2)}%", "信心潰散", delta_color="inverse")

                    # 6. 顯示詳細清單 (排序：乖離率高的在上面)
                    st.dataframe(
                        club_members[["資產名稱", "現價", "乖離率", "趨勢 (月線)"]].sort_values("乖離率", ascending=False), 
                        hide_index=True, 
                        use_container_width=True
                    )
                else:
                    st.warning("⚠️ 目前沒有股價大於 1000 元的股票，市場極度恐慌？")
            else:
                st.write("數據讀取中...")
            # =========================================

    else: st.error("數據下載失敗，請重新整理網頁")

# --- Tab 3: 風險雷達 ---
with tab_risk:
    st.subheader("🚀 市場風險雷達 (含市場廣度)")
    if 'Close' in cached_data.columns: data = cached_data['Close']
    else: data = cached_data
    
    if 'RSP' in data.columns and 'SPY' in data.columns:
        rsp_series = data['RSP'].dropna()
        spy_series = data['SPY'].dropna()
        if not rsp_series.empty and not spy_series.empty:
            rsp_ret = (rsp_series.iloc[-1] - rsp_series.iloc[-20]) / rsp_series.iloc[-20]
            spy_ret = (spy_series.iloc[-1] - spy_series.iloc[-20]) / spy_series.iloc[-20]
            b_msg = "🔴 廣度佳" if rsp_ret > spy_ret else "🟢 廣度差"
            b_desc = f"RSP({round(rsp_ret*100,2)}%) vs SPY({round(spy_ret*100,2)}%)"
        else: b_msg, b_desc = "---", "數據不足"
    else: b_msg, b_desc = "---", "無數據"

    if 'HYG' in data.columns and 'LQD' in data.columns:
        hyg_series = data['HYG'].dropna()
        lqd_series = data['LQD'].dropna()
        if not hyg_series.empty and not lqd_series.empty:
            hyg_ret = (hyg_series.iloc[-1] - hyg_series.iloc[-20]) / hyg_series.iloc[-20]
            lqd_ret = (lqd_series.iloc[-1] - lqd_series.iloc[-20]) / lqd_series.iloc[-20]
            c_msg = "🔴 追逐風險" if hyg_ret > lqd_ret else "🟢 趨避風險"
            c_desc = f"HYG({round(hyg_ret*100,2)}%) vs LQD({round(lqd_ret*100,2)}%)"
        else: c_msg, c_desc = "---", "數據不足"
    else: c_msg, c_desc = "---", "無數據"

    cb1, cb2 = st.columns(2)
    with cb1: st.info(f"📊 **市場廣度**：**{b_msg}**\n\n{b_desc}")
    with cb2: st.info(f"🦁 **信用風險**：**{c_msg}**\n\n{c_desc}")

    c1, c2, c3 = st.columns(3)
    with c1: st.write("**1. 領先指標**"); st.dataframe(get_data_from_cache(assets_radar["1. 🚀 領先指標"], cached_data)[["資產名稱", "趨勢 (月線)", "RSI訊號"]], hide_index=True, use_container_width=True)
    with c2: st.write("**2. 避險資產**"); st.dataframe(get_data_from_cache(assets_radar["2. 🛡️ 避險資產"], cached_data)[["資產名稱", "趨勢 (月線)", "RSI訊號"]], hide_index=True, use_container_width=True)
    with c3: st.write("**3. 股市現況**"); st.dataframe(get_data_from_cache(assets_radar["3. 📉 股市現況"], cached_data)[["資產名稱", "趨勢 (月線)", "RSI訊號"]], hide_index=True, use_container_width=True)

# --- Tab 4: 半導體雷達 ---
with tab_semi:
    st.subheader("💎 半導體相對強度雷達")
    st.markdown(f"邏輯：**半導體漲幅 / 標普500 ({benchmark_ticker}) 漲幅**")
    if 'Close' in cached_data.columns: data = cached_data['Close']
    else: data = cached_data

    if benchmark_ticker in data.columns:
        bench = data[benchmark_ticker].dropna()
        if not bench.empty and len(bench) > 60:
            bench_ret = (bench.iloc[-1] - bench.iloc[-60]) / bench.iloc[-60]
            res = []
            for t in assets_semi_tickers:
                if t in data.columns:
                    tgt = data[t].dropna()
                    if not tgt.empty and len(tgt) > 60:
                        tgt_ret = (tgt.iloc[-1] - tgt.iloc[-60]) / tgt.iloc[-60]
                        rs = (1 + tgt_ret) / (1 + bench_ret)
                        status = "🔥 強" if rs > 1 else "🐢 弱"
                        clr = "background-color: #ffe6e6" if rs > 1 else "background-color: #e6ffe6"
                        res.append({
                            "代號": t, "資產名稱": name_map.get(t,t), 
                            "強度 (RS)": round(rs,4), "漲幅": f"{round(tgt_ret*100, 2)}%", 
                            "狀態": status, "_c": clr
                        })
            if res:
                df_s = pd.DataFrame(res).sort_values("強度 (RS)", ascending=False)
                sox_row = df_s[df_s['代號'] == 'SOXX']
                if not sox_row.empty:
                    s_rs = sox_row['強度 (RS)'].values[0]
                    st.metric("費半ETF (SOXX) 強度", s_rs, "🚀 跑贏" if s_rs > 1 else "⚠️ 跑輸")
                st.dataframe(df_s.style.apply(lambda x: [x['_c']]*len(x), axis=1), column_config={"_c":None}, hide_index=True, use_container_width=True)
            else: st.warning("計算後無數據")
        else: st.error("基準數據不足")
    else: st.error("基準數據缺失")

# --- Tab 5: 輪動策略 ---
with tab_rotate:
    st.subheader("🔄 七大資產輪動策略")
    df_rot = get_data_from_cache(assets_rotation, cached_data)
    if not df_rot.empty:
        qqq = df_rot[df_rot['代號'] == 'QQQ']
        if not qqq.empty:
            sc = qqq['宏觀分數'].values[0]
            if sc >= 60: st.error(f"### 🐂 牛市攻擊 (分數:{sc})\n建議持有 **科技股**")
            else: st.success(f"### 🐻 熊市避險 (分數:{sc})\n建議分散至 **債、匯、金**")
        st.dataframe(df_rot[["代號", "資產名稱", "宏觀分數"]].sort_values("宏觀分數", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 6: 宏觀配置 ---
with tab_macro:
    st.subheader("中長期資產配置")
    c1, c2 = st.columns(2)
    with c1: st.dataframe(get_data_from_cache(assets_macro["1. 🔥 強勢動能觀察"], cached_data)[["資產名稱", "季動能 (3個月)"]], hide_index=True, use_container_width=True)
    with c2: st.dataframe(get_data_from_cache(assets_macro["2. ❄️ 弱勢動能觀察"], cached_data)[["資產名稱", "季動能 (3個月)"]], hide_index=True, use_container_width=True)
    st.divider()
    c3, c4 = st.columns(2)
    with c3: st.dataframe(get_data_from_cache(assets_macro["3. 🌏 核心市場"], cached_data)[["資產名稱", "季動能 (3個月)"]], hide_index=True, use_container_width=True)
    with c4: st.dataframe(get_data_from_cache(assets_macro["4. 🏦 利率與債券"], cached_data)[["資產名稱", "季動能 (3個月)"]], hide_index=True, use_container_width=True)

# --- Tab 7: 趨勢圖 ---
with tab_chart:
    st.subheader("📈 資產趨勢檢視")
    all_keys = list(set(all_needed_tickers))
    opts = [f"{name_map.get(k, k)} ({k})" for k in all_keys]
    sel = st.selectbox("選擇商品：", opts)
    if sel:
        code = sel.split("(")[-1].replace(")", "")
        if 'Close' in cached_data.columns:
            if code in cached_data['Close'].columns:
                st.line_chart(cached_data['Close'][code].dropna())
            else: st.write("無數據")
        else: st.write("數據格式錯誤")

