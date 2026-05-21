import streamlit as st
import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime
import numpy as np
import requests
import json
from deep_translator import GoogleTranslator

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
        * **黑天鵝防禦**：當 Tab 7 出現 3 項以上極端數值，下週開盤應啟動尾部風險避險。
        * **歷史週期**：利用 Tab 8 掌握總統大選四年週期與季節性勝率，大跌時才有底氣承接。
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
    "^IXIC": "納斯達克", "SMH": "半導體ETF", "^SOX": "費半指數", "^TWII": "台灣加權", "^TWO": "櫃買指數"
}

high_price_list = [
    "5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "5269.TWO", "3443.TW", "2454.TW", 
    "2059.TW", "3533.TW", "3131.TWO", "3653.TW", "3293.TWO", "6409.TW", "8454.TW", "6643.TW", 
    "6415.TW", "8299.TWO", "8464.TW", "1590.TW", "2327.TW", "2330.TW", "3034.TW", "4966.TWO"
]

mag_7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "AVGO"]
all_tk = list(set(list(name_map.keys()) + high_price_list + ["SPY", "QQQ", "ZQ=F", "^SOX"]))

raw_df = fetch_raw_data(all_tk)

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
# 4. 介面分頁 (全面升級 8 大分頁)
# ==========================================
t1, t2, t3, t4, t5, t_poly, t_crash, t_cycle = st.tabs([
    "💀 AI 資金", "🇹🇼 台股戰略", "🚀 風險雷達", "💎 半導體", "📈 主要市場", "🔮 真金白銀", "🚨 極端背離雷達", "🗓️ 歷史週期雷達"
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
    def draw_m(col, ticker, name, inv=False):
        r = df_tw_l[df_tw_l['代號']==ticker]
        if not r.empty: col.metric(name, f"{r['現價'].values[0]}", f"{r['乖離率'].values[0]}%", delta_color="normal" if not inv else "inverse")
    draw_m(m1, "SOXX", "費半 ETF")
    draw_m(m2, "00733.TW", "富邦中小")
    draw_m(m3, "DX-Y.NYB", "美元指數", inv=True)
    draw_m(m4, "^TNX", "美債10Y", inv=True)
    draw_m(m5, "^TYX", "美債30Y", inv=True)
    
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

# --- Tab 6 (大資金過濾版 - 擴大樣本網) ---
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

# --- Tab 7: 🚨 極端背離 (黑天鵝雷達) ---
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

    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.markdown("#### 📈 價格與波動極端值")
        st.metric("SOX (費半) RSI", f"{sox_rsi_val}", "⚠️ 極度超買" if sox_rsi_val > 86 else "正常", delta_color="inverse" if sox_rsi_val > 80 else "normal")
        st.metric("NDX (納指) Sharpe", f"{ndx_sharpe_val}x", "⚠️ 極端高風險" if ndx_sharpe_val >= 1.6 else "正常", delta_color="inverse" if ndx_sharpe_val >= 1.6 else "normal")

    with c2:
        st.markdown("#### 🏦 機構動能警報窗")
        gex_label = "🛡️ 安全 Gamma 牆" if gex_input >= 10 else ("💀 崩盤引信啟動" if gex_input < 0 else "⚠️ 屏障消失區")
        st.metric("GEX (造市商曝險)", f"${gex_input} B", gex_label, delta_color="normal" if gex_input >= 10 else "inverse")
        
        naaim_label = "⚠️ 買盤枯竭 (滿倉)" if naaim_input >= 110 else ("🟢 子彈充足" if naaim_input < 60 else "穩定運行")
        st.metric("NAAIM 經理人曝險", f"{naaim_input}%", naaim_label, delta_color="inverse" if naaim_input >= 110 else "normal")

    with c3:
        st.markdown("#### 📉 結構與廣度失衡")
        st.metric("RAY 廣度健康度", "⚠️ 結構惡化" if "嚴重背離" in breadth_select else "結構穩健", delta_color="inverse" if "嚴重背離" in breadth_select else "normal")
        
        sma_label = "⚠️ 掏空風險 (巨頭撐盤)" if sma200_input < 50 else "🟢 健康普漲"
        st.metric("成份股高於年線比例", f"{sma200_input}%", sma_label, delta_color="inverse" if sma200_input < 50 else "normal")

    st.divider()
    st.markdown("### 📝 本週大局觀：量化防禦筆記")
    
    danger_count = 0
    if sox_rsi_val > 86: danger_count += 1
    if ndx_sharpe_val >= 1.6: danger_count += 1
    if gex_input < 0: danger_count += 1
    if naaim_input >= 110: danger_count += 1
    if "嚴重背離" in breadth_select: danger_count += 1
    if sma200_input < 50: danger_count += 1
    
    if danger_count >= 4:
        st.error(f"🚨 **紅色警戒：當前 6 大指標中有 {danger_count} 項陷入極端背離！** 市場流動性極度擁擠、且內部結構嚴重掏空。強烈建議提高現金水位，或買入防禦型 VIX 避險。")
    elif danger_count >= 2:
        st.warning(f"⚠️ **中度戒備：當前有 {danger_count} 項指標異常。** 市場多頭動能主要由少數大型股維繫。暫不開新多單，靜待市場廣度回溫。")
    else:
        st.info(f"✅ **宏觀環境安全：當前異常指標僅 {danger_count} 項。** 機構子彈正常，大盤拉回皆為健康修正，可繼續執行多頭台股選股策略。")

# --- Tab 8: 🗓️ 歷史週期雷達 (自動切換時間軸) ---
with t_cycle:
    st.error("## 🗓️ 總統大選週期與季節性地圖")
    st.caption("基於百年美股大數據統計：自動偵測當前年份，切換對應的四年週期歷史規律與實時大盤走勢對照。")
    st.divider()

    # 自動抓取系統當前年份
    current_year = datetime.now(tw_tz).year
    
    # 建立四年週期矩陣 (以 2024 大選年為基準推算)
    cycle_map = {
        2025: {"name": "第 1 年 (選後第一年 Post-Election)", "desc": "通常市場回歸基本面，政策落實期。走勢溫和，勝率約 65%。"},
        2026: {"name": "第 2 年 (期中選舉年 Midterm Year)", "desc": "歷史特徵：通常為四年週期中最震盪的一年。Q2-Q3 常因政策不確定性面臨龐大回檔壓力 (Sell in May 特性明顯)，通常在 10 月落底後，Q4 展開史詩級報復性反彈。", "win_rate": "全年度勝率約 60%"},
        2027: {"name": "第 3 年 (大選前一年 Pre-Election Year)", "desc": "歷史特徵：四年週期中漲幅最兇悍、勝率最高的一年。執政黨為求連任，通常會釋放大量政策利多與流動性，全年呈現易漲難跌的多頭行情。", "win_rate": "全年度勝率高達 90%"},
        2028: {"name": "第 4 年 (大選年 Election Year)", "desc": "歷史特徵：選前觀望氣氛濃厚，走勢呈現 V 型震盪。確認下一任總統後，不確定性消除，年末發動慶祝行情。", "win_rate": "全年度勝率約 75%"}
    }

    # 取得當前年份的劇本，若超過 2028 則利用餘數循環運算 (保護機制)
    cycle_key = 2025 + ((current_year - 2025) % 4)
    current_cycle = cycle_map.get(cycle_key)

    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown("### 🧭 當前時空定位")
        st.metric("戰情室現實時間線", f"{current_year} 年")
        st.metric("美國總統大選週期", current_cycle["name"])
        st.metric("歷史全年度統計勝率", current_cycle["win_rate"])
    
    with c2:
        st.markdown("### 📖 歷史統計特徵基準")
        st.info(current_cycle["desc"])
        
        # 繪製靜態的歷史每月平均漲跌幅 (這裡以 2026 期中選舉年典型的 Q3 殺盤、Q4 噴出為例)
        if cycle_key == 2026:
            st.markdown("#### 📊 期中選舉年 (Year 2) 歷史各月平均漲跌規律")
            seasonality_data = pd.DataFrame({
                "月份": ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"],
                "歷史平均報酬率 (%)": [1.2, 0.5, 1.0, 1.5, -0.5, -1.0, 0.8, -1.5, -2.5, 2.0, 3.5, 2.5]
            }).set_index("月份")
            st.bar_chart(seasonality_data, color="#deff9a")
            st.caption("💡 統計顯示：5-9 月為傳統淡季與風險好發期，而 10 月末通常為絕佳的波段中長線買點。")
        elif cycle_key == 2027:
            st.markdown("#### 📊 大選前一年 (Year 3) 歷史各月平均漲跌規律")
            seasonality_data = pd.DataFrame({
                "月份": ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"],
                "歷史平均報酬率 (%)": [1.5, 1.0, 1.8, 2.0, 1.2, 1.0, 1.5, 0.5, -0.5, 1.8, 2.5, 2.0]
            }).set_index("月份")
            st.bar_chart(seasonality_data, color="#deff9a")
            st.caption("💡 統計顯示：全年幾乎沒有明顯淡季，回檔幅度通常極淺，為重倉佈局的黃金年份。")

    st.divider()
    
    # 實時 YTD 走勢對照 (將 SPY 正規化，起點設為 0%)
    st.markdown(f"### 📈 {current_year} 年標普 500 (SPY) 實際走勢動態對照")
    
    # 自動抓取今年 1 月 1 日到今天的數據
    ytd_data = yf.download("SPY", start=f"{current_year}-01-01", progress=False)
    if not ytd_data.empty and 'Close' in ytd_data.columns:
        spy_ytd = ytd_data['Close']
        base_price = spy_ytd.iloc[0]
        # 計算累積報酬率
        spy_normalized = (spy_ytd / base_price - 1) * 100
        
        chart_df = pd.DataFrame({f"{current_year} 實際累積報酬 (%)": spy_normalized})
        st.line_chart(chart_df)
        st.caption(f"👆 上圖為 SPY 今年至今的真實走勢。您可藉此直接對照：今年的市場，是否完美複製了上述的歷史劇本？")
    else:
        st.warning("正在擷取今年大盤資料中，若年初第一天可能暫無數據...")
