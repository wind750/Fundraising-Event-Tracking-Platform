import streamlit as st
import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime, timedelta
import numpy as np
import requests
import json
from deep_translator import GoogleTranslator
import altair as alt

# ==========================================
# 1. 系統設定
# ==========================================
st.set_page_config(page_title="全球金融戰情室 (AI週線旗艦版)", layout="wide")
st.title("🌐 全球金融戰情室 (AI週線旗艦版)")

tw_tz = pytz.timezone('Asia/Taipei')
current_time = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"🕒 最後更新時間 (台灣): {current_time} | 📡 每週戰略決策模式已啟動")

# ==========================================
# 📖 說明手冊
# ==========================================
with st.expander("📖 查看：操盤判讀邏輯 & 交易心法 (點擊展開)", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        ### 🔍 數據判讀 (🔴多/強 | 🟢空/弱):
        1. **AI 資金雷達**：平均離差 > 0 代表資金熱絡，< 0 代表退潮。
        2. **台股戰略**：費半/中小乖離 > 0 亮紅燈。
        3. **風險雷達**：日圓 > 60MA (季線) 代表美元強，為安全(紅)；日圓 < 60MA 為日圓強，為警戒(綠)。
        4. **Z-Score**：基於兩年統計。
        5. **極端背離**：監控 RSI 超買、廣度失衡與機構滿倉風險。
        """)
    with c2:
        st.markdown("""
        ### 🛡️ 交易心法:
        * **避開擁擠**：Z-Score > +1.5 時需分批獲利。
        * **流動性警報**：當日圓匯率跌破季線，代表平倉潮隨時啟動。
        * **黑天鵝防禦**：當 Tab 7 出現 3 項以上極端數值，應啟動尾部風險避險。
        * **歷史週期**：利用 Tab 8 與 Tab 9 掌握大選週期與地緣政治百年大循環，提前部署避險資產。
        """)

# ==========================================
# 2. 數據下載 ENGINE
# ==========================================
@st.cache_data(ttl=3600)
def fetch_raw_data(tickers):
    data = yf.download(tickers, period="5y", progress=False)
    if 'Close' in data.columns:
        return data['Close']
    return data

@st.cache_data(ttl=86400)
def fetch_sp500_history():
    """專為 Tab 8 設計的百年級別大數據下載引擎 (^GSPC 標普500指數)"""
    data = yf.download("^GSPC", period="max", progress=False)
    if 'Close' in data.columns:
        # yfinance 傳回可能是 Series 或 DataFrame
        series = data['Close']
        if isinstance(series, pd.DataFrame):
            return series.squeeze()
        return series
    return pd.Series()

@st.cache_data(ttl=86400)
def fetch_naaim_official_csv():
    try:
        url = "https://www.naaim.org/wp-content/uploads/naaim_data.csv"
        df = pd.read_csv(url, timeout=10)
        if not df.empty and 'NAAIM Number' in df.columns:
            latest_val = df['NAAIM Number'].iloc[-1]
            return float(latest_val)
        return None
    except:
        return None

name_map = {
    "NVDA": "輝達", "AAPL": "蘋果", "MSFT": "微軟", "GOOGL": "Google", "AMZN": "亞馬遜", 
    "META": "Meta", "TSLA": "特斯拉", "AVGO": "博通", "SPY": "標普 500", "QQQ": "納指 ETF",
    "SOXX": "費半 ETF", "2330.TW": "台積電", "2454.TW": "聯發科", "00733.TW": "富邦中小",
    "DX-Y.NYB": "美元指數", "^TNX": "美債10年", "^TYX": "美債30年", "JPY=X": "美元/日圓", "ZQ=F": "利率期貨",
    "^VIX": "VIX 恐慌", "BTC-USD": "比特幣", "GC=F": "黃金", "HG=F": "期貨銅", "CL=F": "原油",
    "^IXIC": "納斯達克", "SMH": "半導體ETF", "^SOX": "費半指數", "^TWII": "台灣加權", "^TWO": "櫃買指數",
    "ITA": "美國軍工ETF", "GLD": "黃金ETF", "TLT": "20年美債ETF"
}

high_price_list = [
    "5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "5269.TWO", "3443.TW", "2454.TW", 
    "2059.TW", "3533.TW", "3131.TWO", "3653.TW", "3293.TWO", "6409.TW", "8454.TW", "6643.TW", 
    "6415.TW", "8299.TWO", "8464.TW", "1590.TW", "2327.TW", "2330.TW", "3034.TW", "4966.TWO"
]

mag_7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "AVGO"]
all_tk = list(set(list(name_map.keys()) + high_price_list + ["SPY", "QQQ", "ZQ=F", "^SOX", "ITA", "GLD", "TLT"]))

raw_df = fetch_raw_data(all_tk)
sp500_hist_df = fetch_sp500_history() # 預先載入百年數據供 Tab 8 使用

# ==========================================
# 3. 處理引擎 & 量化公式
# ==========================================
def get_stats(tk_list, source_df, threshold=0):
    processed, filtered, failed = [], [], []
    for tk in tk_list:
        if tk not in source_df.columns:
            failed.append(tk)
            continue
        series = source_df[tk].ffill().dropna()
        if series.empty:
            failed.append(tk)
            continue
            
        price = series.iloc[-1]
        if threshold > 0 and price < threshold:
            filtered.append({"代號": tk, "現價": round(price, 2)})
            continue
            
        ma20 = series.rolling(20).mean().iloc[-1]
        bias = (price - ma20) / ma20 * 100
        window = series.tail(504)
        z = (price - window.mean()) / window.std() if len(window) > 30 and window.std() != 0 else 0
        
        processed.append({
            "代號": tk, "資產名稱": name_map.get(tk, tk), 
            "趨勢": "🔴強勢" if bias > 0 else "🟢弱勢", 
            "現價": round(price, 2), "乖離率": round(bias, 2), "Z-Score": round(z, 2)
        })
    return pd.DataFrame(processed), pd.DataFrame(filtered), failed

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_sharpe(series, period=252):
    returns = series.pct_change().tail(period)
    if returns.std() == 0: return 0
    return (returns.mean() / returns.std()) * np.sqrt(period)

# ==========================================
# 4. 介面分頁
# ==========================================
t1, t2, t3, t4, t5, t_poly, t_crash, t_cycle, t_war = st.tabs([
    "💀 AI 資金", "🇹🇼 台股戰略", "🚀 風險雷達", "💎 半導體", "📈 主要市場", 
    "🔮 真金白銀", "🚨 極端背離雷達", "🗓️ 歷史週期", "⚔️ 戰爭週期雷達"
])

# --- Tab 1 ---
with t1:
    df_ai, _, _ = get_stats(mag_7 + ["^IXIC", "SMH"], raw_df)
    if not df_ai.empty:
        c1, c2 = st.columns([1, 2])
        avg_b = df_ai['乖離率'].mean()
        with c1:
            if avg_b > 0: st.error(f"### 🔴 資金湧入\n平均離差: {round(avg_b, 2)}%")
            else: st.success(f"### 🟢 資金退潮\n平均離差: {round(avg_b, 2)}%")
            st.metric("整體擁擠度 (Z-Score)", round(df_ai['Z-Score'].mean(), 2))
        with c2:
            st.dataframe(df_ai[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("乖離率", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 2 ---
with t2:
    df_tw_l, _, _ = get_stats(["SOXX", "00733.TW", "DX-Y.NYB", "^TNX", "^TYX"], raw_df)
    m1, m2, m3, m4, m5 = st.columns(5)
    
    def draw_m(col, ticker, name):
        r = df_tw_l[df_tw_l['代號']==ticker]
        if not r.empty: 
            col.metric(name, f"{r['現價'].values[0]}", f"{r['乖離率'].values[0]}%", delta_color="inverse")
            
    draw_m(m1, "SOXX", "費半 ETF")
    draw_m(m2, "00733.TW", "富邦中小")
    draw_m(m3, "DX-Y.NYB", "美元指數")
    draw_m(m4, "^TNX", "美債10Y")
    draw_m(m5, "^TYX", "美債30Y")
    
    st.divider()
    df_king, df_filt, _ = get_stats(high_price_list, raw_df, threshold=800)
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("當前監控檔數", f"{len(df_king)} 檔")
    s2.metric("強勢佔比", f"{int(len(df_king[df_king['乖離率']>0])/len(df_king)*100)}%" if not df_king.empty else "0%")
    s3.metric("低於門檻 (濾除)", f"{len(df_filt)} 檔")
    s4.metric("族群平均 Z-Score", round(df_king['Z-Score'].mean(), 2) if not df_king.empty else 0)
    st.dataframe(df_king[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("現價", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 3 ---
with t3:
    st.subheader("⏳ 時間之王：動態風險與Carry Trade壓力測試")
    jpy_s = raw_df['JPY=X'].ffill().dropna()
    if not jpy_s.empty:
        p_jpy = jpy_s.iloc[-1]
        ma60_jpy = jpy_s.rolling(60).mean().iloc[-1]
        slope_10 = (jpy_s.iloc[-1] - jpy_s.iloc[-10]) / 10
        adaptive_threshold = round(ma60_jpy * 1.05, 2) 
        high_days = (jpy_s.tail(20) > ma60_jpy).sum()
        stress_score = min(100, int((p_jpy / 170) * 80 + (high_days / 20) * 20))

        is_unwind = p_jpy > 165 and slope_10 < 0  
        if is_unwind: ct_label, ct_delta, ct_status_msg = "💀 撤退警報 (Unwind)", "inverse", "🚨 **緊急：** 資金大抽水已啟動！"
        elif stress_score > 90: ct_label, ct_delta, ct_status_msg = "⚠️ 臨界預警 (Alert)", "off", "🔥 **警告：** 壓力鍋已飽和。"
        else: ct_label, ct_delta, ct_status_msg = "🛡️ 穩定套利 (Carry)", "normal", "💡 **正常：** 匯率平穩。"

        c1, c2, c3 = st.columns(3)
        with c1: st.metric("名目匯率 (JPY=X)", f"{round(p_jpy, 2)}", f"{'🔴 貶值趨勢' if p_jpy > ma60_jpy else '🟢 日圓轉強'}"); st.caption(f"適應基準: {adaptive_threshold}")
        with c2: st.metric("10日變動斜率", f"{round(slope_10, 2)}", "⚠️ 急速" if slope_10 > 0.5 else "✅ 平穩", delta_color="inverse" if slope_10 > 0.5 else "normal")
        with c3: st.metric("Carry Trade 壓力", f"{stress_score}%", ct_label, delta_color=ct_delta); st.progress(stress_score / 100)

    st.divider()
    df_rz, _, _ = get_stats(["^VIX", "BTC-USD", "GC=F", "HG=F", "CL=F", "DX-Y.NYB"], raw_df)
    st.dataframe(df_rz[["資產名稱", "Z-Score", "趨勢", "現價"]], hide_index=True, use_container_width=True)
    
# --- Tab 4 ---
with t4:
    st.subheader("💎 科技巨頭與半導體強度 (vs SPY)")
    bench_s = raw_df['SPY'].ffill().dropna()
    if len(bench_s) > 60:
        bench_ret = (bench_s.iloc[-1] - bench_s.iloc[-60]) / bench_s.iloc[-60]
        res_rs = []
        for t in ["SOXX", "2330.TW"] + mag_7:
            if t in raw_df.columns:
                target_s = raw_df[t].ffill().dropna()
                common = target_s.index.intersection(bench_s.index)
                if len(common) > 60:
                    t_val = target_s.loc[common]
                    ret_t = (t_val.iloc[-1] - t_val.iloc[-60]) / t_val.iloc[-60]
                    rs = (1 + ret_t) / (1 + bench_ret)
                    clr = "background-color: rgba(255, 50, 50, 0.15)" if rs > 1 else "background-color: rgba(50, 255, 50, 0.15)"
                    res_rs.append({"名稱": name_map.get(t,t), "強度(RS)": round(rs,4), "_c": clr})
        if res_rs:
            df_rs = pd.DataFrame(res_rs).sort_values("強度(RS)", ascending=False)
            st.dataframe(df_rs.style.apply(lambda x: [x['_c']]*len(x), axis=1), column_config={"_c":None}, hide_index=True, use_container_width=True)

# --- Tab 5 ---
with t5:
    st.subheader("📈 全球資產趨勢與動態基準")
    sel = st.selectbox("選擇商品：", all_tk, format_func=lambda x: f"{name_map.get(x,x)} ({x})", key="main_trend_selector")
    if sel:
        plot_data = raw_df[sel].ffill().dropna()
        if not plot_data.empty:
            chart_df = pd.DataFrame({"現價": plot_data})
            if sel == "JPY=X":
                ma60 = plot_data.rolling(60).mean()
                chart_df["動態適應基準 (DAT)"] = ma60 * 1.05
            st.line_chart(chart_df)

# --- Tab 6 ---
with t_poly:
    st.subheader("🔮 真金白銀下注預測")
    @st.cache_data(ttl=300)
    def fetch_manifold_events_filtered():
        try:
            url = "https://api.manifold.markets/v0/search-markets?term=&sort=volume&filter=open&limit=100"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if res.status_code != 200:
                url = "https://api.manifold.markets/v0/markets?limit=500"
                res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if res.status_code == 200:
                markets = res.json()
                noise = ["coin", "flip", "heads", "tails", "random", "test"]
                filtered = [m for m in markets if m.get('outcomeType') == 'BINARY' and m.get('volume', 0) > 3000 and not any(kw in m.get('question', '').lower() for kw in noise)]
                return sorted(filtered, key=lambda x: x.get('volume', 0), reverse=True)[:5]
            return []
        except: return []

    events_data = fetch_manifold_events_filtered()
    if events_data:
        translator = GoogleTranslator(source='en', target='zh-TW')
        for event in events_data:
            title_en = event.get('question', '未知事件')
            prob_yes = event.get('probability', 0)
            vol = int(event.get('volume', 0))
            if prob_yes is None: continue
            try: title_zh = translator.translate(title_en)
            except: title_zh = title_en
            st.markdown(f"#### 🏷️ {title_zh}")
            st.caption(f"原文: {title_en} | 💰 總量: ${vol:,}")
            
            c1, c2 = st.columns([1, 4])
            with c1: st.metric("Yes", f"{round(prob_yes*100, 1)}%", delta_color="off")
            with c2: st.progress(min(1.0, max(0.0, prob_yes)))
            
            c3, c4 = st.columns([1, 4])
            with c3: st.metric("No", f"{round((1-prob_yes)*100, 1)}%", delta_color="off")
            with c4: st.progress(min(1.0, max(0.0, 1-prob_yes)))
            st.write("---")

# --- Tab 7: 🚨 極端背離雷達 ---
with t_crash:
    st.error("## 🚨 黑天鵝雷達：系統性反轉與流動性枯竭預警")
    st.caption("專為每週複盤設計的宏觀風險控制台。結合即時量化運算與機構籌碼面。")
    st.divider()

    naaim_auto_val = fetch_naaim_official_csv()

    st.subheader("🛠️ 每週核心籌碼數據校正（動態響應面板）")
    col_in1, col_in2, col_in3 = st.columns(3)
    
    with col_in1:
        default_naaim = naaim_auto_val if naaim_auto_val is not None else 110.0
        naaim_input = st.slider("1. NAAIM 機構經理人曝險 (%)", 0.0, 200.0, float(default_naaim), step=5.0)
        if naaim_auto_val is not None:
            st.success(f"✅ 自動同步 NAAIM 最新數據: {naaim_auto_val}%")
        else:
            st.caption("💡 提示：可手動拉動滑桿校正")
            
    with col_in2:
        gex_input = st.number_input("2. 當前 GEX 曝險 (十億, B)", value=21.5, step=1.0)
        st.caption("💡 提示：> +10B 安全區；< 0 多殺多區")
        
    with col_in3:
        breadth_select = st.selectbox("3. RAY (羅素3000) 內部廣度", ["嚴重背離 (指數高、個股破底)", "正常同步", "極度健康"])
        sma200_input = st.slider("4. S&P500 高於年線比例 (%)", 0.0, 100.0, 42.0, step=1.0)

    st.divider()

    sox_rsi_val = 0
    if '^SOX' in raw_df.columns:
        sox_data = raw_df['^SOX'].ffill().dropna()
        if not sox_data.empty:
            sox_rsi_val = round(calculate_rsi(sox_data).iloc[-1], 2)

    ndx_sharpe_val = 0
    if 'QQQ' in raw_df.columns:
        qqq_data = raw_df['QQQ'].ffill().dropna()
        if not qqq_data.empty:
            ndx_sharpe_val = round(calculate_sharpe(qqq_data), 2)

    # 確保數值存在防崩潰
    _sox = float(sox_rsi_val) if sox_rsi_val is not None else 50.0
    _gex = float(gex_input) if gex_input is not None else 0.0
    _naaim = float(naaim_input) if naaim_input is not None else 50.0

    c1, c2, c3 = st.columns(3)
    
    # 採用顯示分離法，避免 delta 接收字串報錯
    with c1:
        st.markdown("#### 📈 價格與波動極端值")
        st.metric("SOX (費半) RSI", f"{_sox:.1f}", delta=f"{_sox - 50:.1f}", delta_color="inverse")
        st.caption("警示: 極端超買" if _sox > 86 else "狀態: 正常")
        
        st.metric("NDX (納指) Sharpe", f"{ndx_sharpe_val:.2f}x", delta=f"{ndx_sharpe_val - 1.0:.2f}", delta_color="inverse")
        st.caption("警示: 極端高風險" if ndx_sharpe_val >= 1.6 else "狀態: 正常")

    with c2:
        st.markdown("#### 🏦 機構動能警報窗")
        st.metric("GEX (造市商曝險)", f"{_gex:.1f} B", delta=f"{_gex:.1f}", delta_color="inverse")
        st.caption("狀態: " + ("崩盤引信啟動" if _gex < 0 else ("安全區" if _gex > 10 else "屏障消失區")))
        
        st.metric("NAAIM 經理人曝險", f"{_naaim:.0f}%", delta=f"{_naaim - 60:.0f}", delta_color="inverse")
        st.caption("狀態: " + ("買盤枯竭 (滿倉)" if _naaim >= 110 else ("子彈充足" if _naaim < 60 else "穩定運行")))

    with c3:
        st.markdown("#### 📉 結構與廣度失衡")
        st.metric("RAY 廣度健康度", "數據就緒", delta="0", delta_color="inverse")
        st.caption("狀態: 結構惡化" if "嚴重背離" in breadth_select else "狀態: 結構穩健")
        
        st.metric("成份股高於年線比例", f"{sma200_input:.0f}%", delta=f"{sma200_input - 50:.0f}", delta_color="inverse")
        st.caption("狀態: " + ("掏空風險 (巨頭撐盤)" if sma200_input < 50 else "健康普漲"))

    st.divider()
    st.markdown("### 📝 本週大局觀：量化防禦筆記")
    
    danger_count = 0
    if _sox > 86: danger_count += 1
    if ndx_sharpe_val >= 1.6: danger_count += 1
    if _gex < 0: danger_count += 1
    if _naaim >= 110: danger_count += 1
    if "嚴重背離" in breadth_select: danger_count += 1
    if sma200_input < 50: danger_count += 1
    
    if danger_count >= 4:
        st.error(f"🚨 **紅色警戒：當前 6 大指標中有 {danger_count} 項陷入極端背離！** 市場流動性極度擁擠、且內部結構嚴重掏空。強烈建議提高現金水位，或買入防禦型 VIX 避險。")
    elif danger_count >= 2:
        st.warning(f"⚠️ **中度戒備：當前有 {danger_count} 項指標異常。** 市場多頭動能主要由少數大型股維繫。暫不開新多單，靜待市場廣度回溫。")
    else:
        st.info(f"✅ **宏觀環境安全：當前異常指標僅 {danger_count} 項。** 機構子彈正常，大盤拉回皆為健康修正，可繼續執行多頭台股選股策略。")

# --- Tab 8: 🗓️ 歷史週期雷達 (無敵進化版) ---
with t_cycle:
    st.error("## 🗓️ 總統大選週期與月度歷史地圖")
    st.caption("由本地量化引擎自動分析 **標普 500 指數 (^GSPC)** 近百年的大數據庫，支援自訂觀測時空與回溯區間。")
    st.divider()

    current_year = datetime.now(tw_tz).year
    
    # --- 1. 建立動態時間定位與回溯控制面板 ---
    c_year, c_lookback, c_month = st.columns([1, 1, 1])
    with c_year:
        selected_cycle_year = st.selectbox("1️⃣ 選擇觀測年份：", [current_year, current_year + 1, current_year + 2], index=0)
    with c_lookback:
        lookback_options = {"30年": 30, "40年": 40, "50年": 50, "全部 (1927至今)": 100}
        selected_lookback_str = st.selectbox("2️⃣ 選擇歷史回溯區間：", list(lookback_options.keys()), index=2)
        lookback_years = lookback_options[selected_lookback_str]
    with c_month:
        months_list = [f"{i}月" for i in range(1, 13)]
        default_month_index = datetime.now(tw_tz).month - 1
        selected_month_str = st.selectbox("3️⃣ 選擇深度分析月份：", months_list, index=default_month_index)
        selected_month_num = int(selected_month_str.replace("月", ""))

    # --- 2. 核心：量化總統週期定位 ---
    cycle_index = (selected_cycle_year - 2025) % 4
    cycle_names = ["第一年 (選後/重新定調)", "第二年 (期中選舉/通常最震盪)", "第三年 (選前/通常最強勁)", "第四年 (大選/波動後迎慶祝)"]
    current_cycle_name = cycle_names[cycle_index]

    # 過濾歷史對照年份 (依據選擇的回溯區間)
    start_eval_year = max(1927, current_year - lookback_years)
    base_history_years = [y for y in range(start_eval_year, current_year) if (y - 2025) % 4 == cycle_index]
    # 反轉排序讓最近的年份排前面
    base_history_years.sort(reverse=True)
    
    st.markdown(f"### 🧭 戰略時空定位：{selected_cycle_year} 年 | 週期屬性：{current_cycle_name}")
    st.info(f"🔍 **本地量化引擎已啟動**：正在計算過去 **{selected_lookback_str}** 內，所有符合該週期的歷史年份\n\n對照年份：**{', '.join(map(str, base_history_years))}**")

    if not sp500_hist_df.empty:
        # --- 3. 計算 1-12 月的全年歷史平均 (重現原版柱狀圖) ---
        sp500_monthly = sp500_hist_df.resample('ME').last() if pd.__version__ >= '2.2.0' else sp500_hist_df.resample('M').last()
        sp500_monthly_ret = sp500_monthly.pct_change() * 100
        
        # 取出所有對應年份的月度報酬
        matched_rets = sp500_monthly_ret[sp500_monthly_ret.index.year.isin(base_history_years)]
        if not matched_rets.empty:
            avg_rets_by_month = matched_rets.groupby(matched_rets.index.month).mean()
            
            # 確保 1 到 12 月都有數據
            rets_array = [avg_rets_by_month.get(m, 0.0) for m in range(1, 13)]
            months_labels = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"]
            
            seasonality_df = pd.DataFrame({
                "月份": pd.Categorical(months_labels, categories=months_labels, ordered=True),
                "歷史平均報酬率 (%)": rets_array
            })
            
            st.markdown(f"#### 📊 {selected_cycle_year} 年 (週期{cycle_index+1})：全年度 1-12 月歷史平均漲跌規律")
            
            # 使用 Altair 繪製柱狀圖，並保持紅漲綠跌
            bar_chart = alt.Chart(seasonality_df).mark_bar().encode(
                x=alt.X('月份', sort=months_labels, axis=alt.Axis(labelAngle=0)),
                y='歷史平均報酬率 (%)',
                color=alt.condition(
                    alt.datum['歷史平均報酬率 (%)'] > 0,
                    alt.value('#FF3333'),  # 🔴 紅色代表上漲 (大於0)
                    alt.value('#00C000')   # 🟢 綠色代表下跌 (小於0)
                ),
                tooltip=['月份', alt.Tooltip('歷史平均報酬率 (%)', format='.2f')]
            ).properties(height=350).configure_axis(
                labelFontSize=14, titleFontSize=16
            )
            st.altair_chart(bar_chart, use_container_width=True)
            st.divider()

        # --- 4. 計算單月 (指定月) 的內部走勢疊加圖 ---
        monthly_returns = []
        monthly_trends = pd.DataFrame()

        for hist_year in base_history_years:
            try:
                # 擷取該歷史年份、指定月份的「日線」數據
                month_daily = sp500_hist_df[(sp500_hist_df.index.year == hist_year) & (sp500_hist_df.index.month == selected_month_num)]
                if len(month_daily) > 1:
                    first_price = float(month_daily.iloc[0])
                    last_price = float(month_daily.iloc[-1])
                    ret_percent = ((last_price - first_price) / first_price) * 100
                    monthly_returns.append(ret_percent)
                    
                    # 標準化走勢（以該月第一天為基期 100）
                    normalized_trend = (month_daily / first_price) * 100
                    trend_df = pd.DataFrame({f"{hist_year}年": normalized_trend.values})
                    monthly_trends = pd.concat([monthly_trends, trend_df], axis=1)
            except Exception as e:
                pass 

        if monthly_returns:
            avg_return = np.mean(monthly_returns)
            win_count = sum(1 for r in monthly_returns if r > 0)
            win_rate = (win_count / len(monthly_returns)) * 100
            
            # 決定面板燈號 (紅漲綠跌邏輯)
            if avg_return > 0:
                ret_color = "inverse"
                status_text = "多頭強勢月"
            else:
                ret_color = "normal"
                status_text = "季節性回調月 (十字路口)"

            c_stat1, c_stat2, c_stat3 = st.columns(3)
            with c_stat1:
                st.metric(f"歷史 {selected_month_str} 平均報酬", f"{avg_return:.2f}%", delta=f"{avg_return:.2f}", delta_color=ret_color)
            with c_stat2:
                st.metric(f"歷史 {selected_month_str} 上漲勝率", f"{win_rate:.0f}%", delta="偏多" if win_rate >= 50 else "偏空", delta_color="inverse" if win_rate >= 50 else "normal")
            with c_stat3:
                st.metric("季節性慣性判定", status_text, delta="0", delta_color="off")
            
            st.markdown(f"#### 📈 歷史 {selected_month_str} 內部每日走勢疊加與基準預測線")
            if not monthly_trends.empty:
                # 計算歷史平均預測線
                monthly_trends['平均基準線 (Avg Base)'] = monthly_trends.mean(axis=1)
                monthly_trends['交易日 (Day)'] = range(1, len(monthly_trends) + 1)
                
                chart_data = monthly_trends.melt(id_vars=['交易日 (Day)'], var_name='年份', value_name='標準化點位 (基準100)')
                
                lines = alt.Chart(chart_data).mark_line().encode(
                    x=alt.X('交易日 (Day):O', axis=alt.Axis(labelAngle=0)),
                    y=alt.Y('標準化點位 (基準100):Q', scale=alt.Scale(zero=False)),
                    color=alt.condition(
                        alt.datum.年份 == '平均基準線 (Avg Base)',
                        alt.value('#deff9a'), # 主預測線為亮黃綠色
                        alt.Color('年份:N', legend=alt.Legend(title="歷史疊加")) # 其他歷史線自動分色
                    ),
                    size=alt.condition(
                        alt.datum.年份 == '平均基準線 (Avg Base)',
                        alt.value(4), 
                        alt.value(1)  
                    ),
                    opacity=alt.condition(
                        alt.datum.年份 == '平均基準線 (Avg Base)',
                        alt.value(1.0), 
                        alt.value(0.4) 
                    ),
                    tooltip=['交易日 (Day)', '年份', alt.Tooltip('標準化點位 (基準100)', format='.2f')]
                ).properties(height=400)
                
                st.altair_chart(lines, use_container_width=True)
                st.caption(f"💡 圖表判讀：若當前市場 ({selected_cycle_year}年 {selected_month_str}) 的實際走勢強於黃綠色的「平均基準線」，代表『近期強勢資金』成功抵銷歷史魔咒；反之則需提防技術修正。")
        else:
            st.warning(f"在所選的歷史區間內，無足夠的 {selected_month_str} 數據樣本進行疊加計算。")
    else:
        st.warning("無法載入 S&P 500 歷史大數據庫，請確認網路連線。")

# --- Tab 9: ⚔️ 戰爭週期雷達 ---
with t_war:
    st.error("## ⚔️ 三大戰爭週期共振雷達 (2027-2032)")
    st.caption("源自 Dewey、Mogey 與 Wheeler 百年量化學派。透過正弦波演算法追蹤太陽活動、地緣衝突與霸權重組的歷史共振節點。")
    st.divider()

    current_year_for_war = datetime.now(tw_tz).year
    selected_year = st.slider("時間觀測儀 (模擬年份推演)", min_value=2000, max_value=2050, value=current_year_for_war, step=1)
    
    years_array = np.arange(2000, 2051)
    
    dewey_wave = (np.sin(2 * np.pi * (years_array - 2026) / 16) + 1) * 50
    mogey_wave = (np.sin(2 * np.pi * (years_array - 2023.5) / 26) + 1) * 50
    long_wave = (np.sin(2 * np.pi * (years_array - 2014.25) / 63) + 1) * 50
    danger_index_array = (dewey_wave + mogey_wave + long_wave) / 3
    idx = np.where(years_array == selected_year)[0][0]
    current_danger = round(danger_index_array[idx], 1)

    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown("### 🌡️ 宏觀地緣風險指數")
        if 2027 <= selected_year <= 2032:
            alert_color = "inverse"
            alert_text = "💀 極端紅區：三大週期波峰交會"
        elif 2024 <= selected_year < 2027:
            alert_color = "off"
            alert_text = "⚠️ 醞釀期：危機正在升溫 (太陽極大期)"
        else:
            alert_color = "normal"
            alert_text = "🟢 衰退期：進入秩序重組"
            
        st.metric(label=f"{selected_year} 年共振強度 (0-100)", value=f"{current_danger}", delta=alert_text, delta_color=alert_color)
        
        st.markdown("---")
        st.markdown("#### 🔭 週期解析")
        st.write("**1. 16年 Dewey 週期：** 短期區域衝突爆發規律。")
        st.write("**2. 26年 Mogey 週期：** 國家級地緣政治板塊碰撞。")
        st.write("**3. 63年 長波週期：** 全球霸權與法幣系統的歷史更迭。")

    with c2:
        st.markdown("### 📈 百年戰爭週期共振矩陣圖")
        war_df = pd.DataFrame({
            "年份": years_array,
            "16年 Dewey": dewey_wave,
            "26年 Mogey": mogey_wave,
            "63年 長波": long_wave,
            "共振危險指數": danger_index_array
        })
        war_df_melted = war_df.melt(id_vars=["年份"], var_name="週期類型", value_name="能量強度")
        
        war_chart = alt.Chart(war_df_melted).mark_line(strokeWidth=2).encode(
            x=alt.X('年份:O', axis=alt.Axis(values=[2000, 2010, 2020, 2027, 2032, 2040, 2050], labelAngle=0)),
            y=alt.Y('能量強度:Q', scale=alt.Scale(domain=[0, 100])),
            color=alt.Color('週期類型:N', scale=alt.Scale(
                domain=['16年 Dewey', '26年 Mogey', '63年 長波', '共振危險指數'],
                range=['#5bc0de', '#f0ad4e', '#d9534f', '#ffffff']
            )),
            tooltip=['年份', '週期類型', alt.Tooltip('能量強度', format='.1f')]
        ).properties(height=350)
        
        rect_df = pd.DataFrame([{"start": 2027, "end": 2032}])
        danger_zone = alt.Chart(rect_df).mark_rect(color='red', opacity=0.15).encode(
            x='start:O', x2='end:O'
        )
        
        rule_df = pd.DataFrame([{"year": selected_year}])
        vline = alt.Chart(rule_df).mark_rule(color='#deff9a', strokeWidth=2, strokeDash=[5, 5]).encode(
            x='year:O'
        )
        
        st.altair_chart(war_chart + danger_zone + vline, use_container_width=True)

    st.divider()

    st.markdown("### 🛡️ 戰略避險矩陣 (Strategic Asset Shield)")
    st.caption("當時間軸進入 2027-2032 共振紅區時，傳統法幣與科技股將面臨估值重估，資金將流向以下實體硬資產與避險核心。")
    
    df_shield, _, _ = get_stats(["GC=F", "CL=F", "TLT", "ITA", "DX-Y.NYB"], raw_df)
    
    if not df_shield.empty:
        s1, s2, s3, s4 = st.columns(4)
        def draw_shield(col, ticker, name, purpose):
            r = df_shield[df_shield['代號']==ticker]
            if not r.empty: 
                col.metric(f"🪙 {name} ({purpose})", f"{r['現價'].values[0]}", f"{r['乖離率'].values[0]}%", delta_color="inverse")
        
        draw_shield(s1, "GC=F", "黃金期貨", "抗通膨與法幣貶值")
        draw_shield(s2, "CL=F", "原油期貨", "供應鏈地緣溢價")
        draw_shield(s3, "TLT", "20年美債", "終極無風險避風港")
        draw_shield(s4, "ITA", "美國軍工", "國防預算擴張受惠")
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.dataframe(df_shield[["資產名稱", "趨勢", "現價", "乖離率", "Z-Score"]], hide_index=True, use_container_width=True)
    else:
        st.warning("避險資產數據載入中...")
