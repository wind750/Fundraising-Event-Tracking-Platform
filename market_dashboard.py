import streamlit as st
import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime
import numpy as np
import requests
import json  # <--- 必須補上這一行

# ==========================================
# 1. 系統設定
# ==========================================
st.set_page_config(page_title="全球金融戰情室 (AI旗艦版)", layout="wide")
st.title("🌐 全球金融戰情室 (AI旗艦版)")

tw_tz = pytz.timezone('Asia/Taipei')
current_time = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"🕒 最後更新時間 (台灣): {current_time}")

# ==========================================
# 📖 說明手冊 (確保永久穩定)
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
        """)
    with c2:
        st.markdown("""
        ### 🛡️ 2026 交易心法:
        * **避開擁擠**：Z-Score > +1.5 時需分批獲利。
        * **流動性警報**：當日圓匯率跌破季線，代表平倉潮隨時啟動。
        """)

# ==========================================
# 2. 數據下載 (強化穩定性)
# ==========================================

@st.cache_data(ttl=3600)
def fetch_raw_data(tickers):
    # 下載 5 年數據確保兩年回測穩定
    data = yf.download(tickers, period="5y", progress=False)
    if 'Close' in data.columns:
        return data['Close']
    return data

name_map = {
    "NVDA": "輝達", "AAPL": "蘋果", "MSFT": "微軟", "GOOGL": "Google", "AMZN": "亞馬遜", 
    "META": "Meta", "TSLA": "特斯拉", "AVGO": "博通", "SPY": "標普 500", "QQQ": "納指 ETF",
    "SOXX": "費半 ETF", "2330.TW": "台積電", "2454.TW": "聯發科", "00733.TW": "富邦中小",
    "DX-Y.NYB": "美元指數", "^TNX": "美債10年", "JPY=X": "美元/日圓", "ZQ=F": "利率期貨",
    "^VIX": "VIX 恐慌", "BTC-USD": "比特幣", "GC=F": "黃金", "HG=F": "期貨銅", "CL=F": "原油",
    "^IXIC": "納斯達克", "SMH": "半導體ETF", "^SOX": "費半指數", "^TWII": "台灣加權", "^TWO": "櫃買指數"
}

high_price_list = [
    "5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "5269.TWO", "3443.TW", "2454.TW", 
    "2059.TW", "3533.TW", "3131.TWO", "3653.TW", "3293.TWO", "6409.TW", "8454.TW", "6643.TW", 
    "6415.TW", "8299.TWO", "8464.TW", "1590.TW", "2327.TW", "2330.TW", "3034.TW", "4966.TWO"
]

mag_7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "AVGO"]
all_tk = list(set(list(name_map.keys()) + high_price_list + ["SPY", "ZQ=F"]))

raw_df = fetch_raw_data(all_tk)

# ==========================================
# 3. 處理引擎 (修復 None 與 nan)
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
        # Z-Score (兩年 504 天)
        window = series.tail(504)
        z = (price - window.mean()) / window.std() if len(window) > 30 and window.std() != 0 else 0
        
        processed.append({
            "代號": tk, "資產名稱": name_map.get(tk, tk), 
            "趨勢": "🔴強勢" if bias > 0 else "🟢弱勢", 
            "現價": round(price, 2), "乖離率": round(bias, 2), "Z-Score": round(z, 2)
        })
    return pd.DataFrame(processed), pd.DataFrame(filtered), failed

# ==========================================
# 4. 介面分頁
# ==========================================
t1, t2, t3, t4, t5, t6, t_poly = st.tabs(["💀 AI 資金", "🇹🇼 台股戰略", "🚀 風險雷達", "💎 半導體", "📈 趨勢圖", "⚖️ 法人估值", "🔮 預測市場"])

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
    df_tw_l, _, _ = get_stats(["SOXX", "00733.TW", "DX-Y.NYB", "^TNX"], raw_df)
    m1, m2, m3, m4 = st.columns(4)
    def draw_m(col, ticker, name, inv=False):
        r = df_tw_l[df_tw_l['代號']==ticker]
        if not r.empty: col.metric(name, f"{r['現價'].values[0]}", f"{r['乖離率'].values[0]}%", delta_color="normal" if not inv else "inverse")
    draw_m(m1, "SOXX", "費半 ETF")
    draw_m(m2, "00733.TW", "富邦中小")
    draw_m(m3, "DX-Y.NYB", "美元指數", inv=True)
    draw_m(m4, "^TNX", "美債10Y", inv=True)
    
    st.divider()
    df_king, df_filt, _ = get_stats(high_price_list, raw_df, threshold=800)
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("當前監控檔數", f"{len(df_king)} 檔")
    s2.metric("強勢佔比", f"{int(len(df_king[df_king['乖離率']>0])/len(df_king)*100)}%" if not df_king.empty else "0%")
    s3.metric("低於門檻 (濾除)", f"{len(df_filt)} 檔")
    s4.metric("族群平均 Z-Score", round(df_king['Z-Score'].mean(), 2) if not df_king.empty else 0)
    st.dataframe(df_king[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("現價", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 3 (AI 旗艦增強版：時間之王 2.0 - 結構化預警) ---
with t3:
    st.subheader("⏳ 王者時間：動態風險與 Carry Trade 壓力測試")
    
    jpy_s = raw_df['JPY=X'].ffill().dropna()
    if not jpy_s.empty:
        p_jpy = jpy_s.iloc[-1]
        ma60_jpy = jpy_s.rolling(60).mean().iloc[-1]
        
        # --- [AI 核心：動態閾值與壓力演算法] ---
        # 1. 計算斜率 (10 天變動速度)
        slope_10 = (jpy_s.iloc[-1] - jpy_s.iloc[-10]) / 10
        # 2. 定義適應性基準 (5% 緩衝)
        adaptive_threshold = round(ma60_jpy * 1.05, 2) 
        # 3. 壓力飽和度計算
        high_days = (jpy_s.tail(20) > ma60_jpy).sum()
        stress_score = min(100, int((p_jpy / 170) * 80 + (high_days / 20) * 20))

        # --- [三段式 Carry Trade 狀態邏輯] ---
        is_unwind = p_jpy > 165 and slope_10 < 0  # 關鍵：高位反轉
        
        if is_unwind:
            ct_label = "💀 撤退警報 (Unwind)"
            ct_delta = "inverse"
            ct_status_msg = "🚨 **緊急：** 資金大抽水已啟動！日圓高位反轉，請立即迴避風險資產。"
        elif stress_score > 90:
            ct_label = "⚠️ 臨界預警 (Alert)"
            ct_delta = "off" # 顯示灰色/中性，代表高度戒備但尚未引爆
            ct_status_msg = "🔥 **警告：** 壓力鍋已飽和。雖然目前尚未反轉，但任何風吹草動都可能觸發閃崩。"
        else:
            ct_label = "🛡️ 穩定套利 (Carry)"
            ct_delta = "normal"
            ct_status_msg = "💡 **正常：** 匯率與時間同步演進中，目前仍具備套利空間。"

        c1, c2, c3 = st.columns(3)
        with c1:
            is_trend_safe = p_jpy > ma60_jpy
            st.metric("名目匯率 (JPY=X)", f"{round(p_jpy, 2)}", 
                      f"{'🔴 貶值趨勢' if is_trend_safe else '🟢 日圓轉強'}")
            st.caption(f"動態適應基準: {adaptive_threshold}")

        with c2:
            # 監控貶值速率
            if slope_10 > 0.5:
                speed_note = "⚠️ 急速貶值"
                speed_color = "inverse"
            else:
                speed_note = "✅ 步調平穩"
                speed_color = "normal"
            st.metric("10日變動斜率", f"{round(slope_10, 2)}", speed_note, delta_color=speed_color)
            st.caption("斜率 > 0.5 易觸發政策干預")

        with c3:
            # 顯示新的三段式狀態
            st.metric("Carry Trade 壓力", f"{stress_score}%", ct_label, delta_color=ct_delta)
            st.progress(stress_score / 100)

        # --- AI 深度觀察與筆記 ---
        st.divider()
        col_msg1, col_msg2 = st.columns([2, 1])
        with col_msg1:
            if is_unwind:
                st.error(ct_status_msg)
            elif stress_score > 90:
                st.warning(ct_status_msg)
            else:
                st.info(ct_status_msg)
            
            # 針對 170 關卡的額外提醒
            if p_jpy > 165:
                st.markdown("---")
                st.caption("🚩 **2026 戰略提醒**：匯率已進入「主權信用危險區」，此時技術指標僅供參考，應隨時準備因應日銀暴力升息引發的流動性枯竭。")
        
        with col_msg2:
            st.write("📊 **判讀筆記：**")
            st.caption("1. 壓力 > 90%：地雷已埋好，等待反轉引信。")
            st.caption("2. 價格 > 165 且斜率為負：引信觸發。")
            st.caption("3. 適應基準：若匯率低於此線，市場尚有喘息空間。")

    st.divider()
    zq_s = raw_df['ZQ=F'].ffill().dropna()
    if not zq_s.empty:
        rate = round(100 - zq_s.iloc[-1], 2)
        st.metric("短端利率 (ZQ=F)", f"{rate}%", "🔴 穩定" if rate < 5.2 else "🟢 緊繃")
            
    st.markdown("##### 🔍 風險資產 Z-Score 掃描")
    df_rz, _, _ = get_stats(["^VIX", "BTC-USD", "GC=F", "HG=F", "CL=F", "DX-Y.NYB"], raw_df)
    st.dataframe(df_rz[["資產名稱", "Z-Score", "趨勢", "現價"]], hide_index=True, use_container_width=True)
    
# --- Tab 4 (修復 None 問題) ---
with t4:
    st.subheader("💎 科技巨頭與半導體強度 (vs SPY)")
    bench_s = raw_df['SPY'].ffill().dropna()
    if len(bench_s) > 60:
        bench_ret = (bench_s.iloc[-1] - bench_s.iloc[-60]) / bench_s.iloc[-60]
        comp_list = ["SOXX", "2330.TW"] + mag_7
        res_rs = []
        for t in comp_list:
            if t in raw_df.columns:
                target_s = raw_df[t].ffill().dropna()
                # 關鍵：強制對齊日期
                common_dates = target_s.index.intersection(bench_s.index)
                if len(common_dates) > 60:
                    t_val = target_s.loc[common_dates]
                    ret_t = (t_val.iloc[-1] - t_val.iloc[-60]) / t_val.iloc[-60]
                    rs = (1 + ret_t) / (1 + bench_ret)
                    clr = "background-color: rgba(255, 50, 50, 0.15)" if rs > 1 else "background-color: rgba(50, 255, 50, 0.15)"
                    res_rs.append({"名稱": name_map.get(t,t), "強度(RS)": round(rs,4), "_c": clr})
        if res_rs:
            df_rs = pd.DataFrame(res_rs).sort_values("強度(RS)", ascending=False)
            st.dataframe(df_rs.style.apply(lambda x: [x['_c']]*len(x), axis=1), column_config={"_c":None}, hide_index=True, use_container_width=True)
    else: st.warning("基準數據不足")

# --- 其餘分頁 ---
# --- Tab 5 (趨勢圖：時間之王視覺化升級) ---
with t5:
    st.subheader("📈 全球資產趨勢與動態基準 (Time-Value Chart)")
    
    # 關鍵修正：加入專屬 key 防止跳轉
    sel = st.selectbox(
        "選擇商品：", 
        all_tk, 
        format_func=lambda x: f"{name_map.get(x,x)} ({x})",
        key="main_trend_selector"  # 鎖定 ID，防止選取後跳回 Tab 1
    )
    
    if sel:
        # 獲取該商品數據
        plot_data = raw_df[sel].ffill().dropna()
        
        if not plot_data.empty:
            # 建立 DataFrame 繪製多線圖
            chart_df = pd.DataFrame({"現價": plot_data})
            
            # 如果選的是日圓，我們強行加入「時間之王」的動態基準線
            if sel == "JPY=X":
                ma60 = plot_data.rolling(60).mean()
                chart_df["動態適應基準 (DAT)"] = ma60 * 1.05
                chart_df["60日季線"] = ma60
                
                # 提示
                st.info(f"💡 目前正在監控日圓的『時間壓力』。當現價突破動態基準 (DAT) 時，代表痛點平移失效。")
            
            # 使用 streamlit 內建圖表 (或 Plotly)
            st.line_chart(chart_df)
            
            # 輔助數據
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("當前價格", round(plot_data.iloc[-1], 2))
            with c2:
                st.metric("60日平均", round(plot_data.tail(60).mean(), 2))
            with c3:
                volatility = plot_data.tail(20).std()
                st.metric("20日波動度", round(volatility, 2))
        else:
            st.warning("該商品尚無足夠數據繪製趨勢圖。")

# --- Tab 7: 預測市場 (Polymarket 真金白銀風向球) ---
with t_poly:
    st.subheader("🔮 預測市場 (真金白銀流向預測)")
    st.caption("數據來源：Polymarket 公開 API | 顯示全球資金對地緣政治與宏觀事件的真實下注機率。")
    
    # 建立一個簡單的 API 抓取函數
    @st.cache_data(ttl=300) # 每 5 分鐘更新一次即可
    def fetch_polymarket_events(limit=5):
        try:
            # 抓取 Polymarket 目前交易量最大的活躍事件
            url = f"https://gamma-api.polymarket.com/events?limit={limit}&active=true&closed=false&order=volumeNum"
            headers = {"Accept": "application/json"}
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                return res.json()
            return None
        except:
            return None

    # UI 佈局：讓使用者可以選擇看「熱門事件」或「搜尋」
    poly_mode = st.radio("觀測模式", ["🔥 全球熱門交易 (依資金量)", "🔍 搜尋特定事件 (如: Iran, Fed)"], horizontal=True)
    
    events_data = []
    
    if poly_mode == "🔥 全球熱門交易 (依資金量)":
        events_data = fetch_polymarket_events(5)
    else:
        search_kw = st.text_input("輸入英文關鍵字 (例如：Iran, Rate, Taiwan)")
        if search_kw:
            try:
                search_url = f"https://gamma-api.polymarket.com/events?limit=5&active=true&closed=false&query={search_kw}"
                res = requests.get(search_url, timeout=5).json()
                events_data = res
            except:
                st.error("搜尋失敗或無相關事件")
    
    st.divider()
    
    # 解析並渲染 Polymarket 數據
    if events_data:
        for event in events_data:
            title = event.get('title', '未知事件')
            volume = event.get('volume', 0)
            markets = event.get('markets', [])
            
            if markets:
                # 通常取第一個子市場的數據
                market = markets[0] 
                outcomes = json.loads(market.get('outcomes', '[]'))
                prices = json.loads(market.get('outcomePrices', '[]'))
                
                # 過濾出有 Yes/No 雙向機率的市場
                if len(outcomes) >= 2 and len(prices) >= 2:
                    st.markdown(f"#### {title}")
                    st.write(f"💰 **總下注資金 (Volume)**: ${int(volume):,}")
                    
                    p1_name, p1_val = outcomes[0], float(prices[0]) * 100
                    p2_name, p2_val = outcomes[1], float(prices[1]) * 100
                    
                    # 視覺化機率條 (Progress Bar)
                    c1, c2 = st.columns([1, 4])
                    with c1:
                        st.metric(p1_name, f"{round(p1_val, 1)}%", delta_color="off")
                    with c2:
                        st.progress(min(1.0, max(0.0, float(prices[0]))))
                    
                    c3, c4 = st.columns([1, 4])
                    with c3:
                        st.metric(p2_name, f"{round(p2_val, 1)}%", delta_color="off")
                    with c4:
                        st.progress(min(1.0, max(0.0, float(prices[1]))))
                    
                    st.write("---")
    else:
        st.info("目前無資料或正在載入中...")

