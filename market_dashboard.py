import streamlit as st
import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime
import numpy as np

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
    "^IXIC": "納斯達克", "SMH": "半導體ETF", "^SOX": "費半指數", "^TWII": "台灣加權", "^TWO": "櫃買指數",
    "TWN=F": "富台期" # 新增富台期代號
}

high_price_list = [
    "5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "5269.TWO", "3443.TW", "2454.TW", 
    "2059.TW", "3533.TW", "3131.TWO", "3653.TW", "3293.TWO", "6409.TW", "8454.TW", "6643.TW", 
    "6415.TW", "8299.TWO", "8464.TW", "1590.TW", "2327.TW", "2330.TW", "3034.TW", "4966.TWO"
]

mag_7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "AVGO"]
# 將富台期加入下載清單
all_tk = list(set(list(name_map.keys()) + high_price_list + ["SPY", "ZQ=F", "TWN=F"]))

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
t1, t2, t3, t4, t5, t6 = st.tabs(["💀 AI 資金", "🇹🇼 台股戰略", "🚀 風險雷達", "💎 半導體", "📈 趨勢圖", "⚖️ 法人估值"])

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

# --- Tab 2 (新增：春節長假富台期觀測) ---
with t2:
    st.subheader("🧧 春節長假：富台期對應加權觀測 (11天假期)")
    
    # 建立封關基準常數 (2026/02/11)
    TAIEX_CLOSE_BASE = 33605.71
    FTSE_CLOSE_BASE = 2726.15
    CONVERSION_RATIO = TAIEX_CLOSE_BASE / FTSE_CLOSE_BASE
    
    # 獲取富台期即時價格
    ftse_series = raw_df['TWN=F'].ffill().dropna()
    if not ftse_series.empty:
        curr_ftse = ftse_series.iloc[-1]
        theo_taiex = curr_ftse * CONVERSION_RATIO
        diff_points = theo_taiex - TAIEX_CLOSE_BASE
        diff_percent = (diff_points / TAIEX_CLOSE_BASE) * 100
        
        # 視覺化呈現
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("富台現價", f"{round(curr_ftse, 2)}", f"基準: {FTSE_CLOSE_BASE}", delta_color="off")
        with col2:
            st.metric("理論加權點數", f"{round(theo_taiex, 2)}", f"{round(diff_points, 2)} 點")
        with col3:
            st.metric("預期開盤漲跌幅", f"{round(diff_percent, 2)}%", delta_color="normal")
            
        st.info(f"💡 換算邏輯：以 2/11 封關價為基準（Ratio: {round(CONVERSION_RATIO, 4)}）。若富台現在為 {round(curr_ftse, 2)}，則對應加權理論值為 {round(theo_taiex, 2)}。")
    else:
        st.warning("暫時無法獲取富台期 (TWN=F) 數據，請檢查網路連線或代號。")

    st.divider()
    
    # 原有的台股指標監控
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

# --- Tab 3 (維持原樣) ---
with t3:
    st.subheader("⏳ 王者時間：動態風險與 Carry Trade 壓力測試")
    jpy_s = raw_df['JPY=X'].ffill().dropna()
    if not jpy_s.empty:
        p_jpy = jpy_s.iloc[-1]
        ma60_jpy = jpy_s.rolling(60).mean().iloc[-1]
        slope_10 = (jpy_s.iloc[-1] - jpy_s.iloc[-10]) / 10
        adaptive_threshold = round(ma60_jpy * 1.05, 2) 
        high_days = (jpy_s.tail(20) > ma60_jpy).sum()
        stress_score = min(100, int((p_jpy / 170) * 80 + (high_days / 20) * 20))
        is_unwind = p_jpy > 165 and slope_10 < 0 
        
        if is_unwind:
            ct_label = "💀 撤退警報 (Unwind)"
            ct_delta = "inverse"
            ct_status_msg = "🚨 **緊急：** 資金大抽水已啟動！日圓高位反轉，請立即迴避風險資產。"
        elif stress_score > 90:
            ct_label = "⚠️ 臨界預警 (Alert)"
            ct_delta = "off"
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
            speed_note = "⚠️ 急速貶值" if slope_10 > 0.5 else "✅ 步調平穩"
            st.metric("10日變動斜率", f"{round(slope_10, 2)}", speed_note, delta_color="inverse" if slope_10 > 0.5 else "normal")
            st.caption("斜率 > 0.5 易觸發政策干預")
        with c3:
            st.metric("Carry Trade 壓力", f"{stress_score}%", ct_label, delta_color=ct_delta)
            st.progress(stress_score / 100)

        st.divider()
        col_msg1, col_msg2 = st.columns([2, 1])
        with col_msg1:
            if is_unwind: st.error(ct_status_msg)
            elif stress_score > 90: st.warning(ct_status_msg)
            else: st.info(ct_status_msg)
            if p_jpy > 165:
                st.markdown("---")
                st.caption("🚩 **2026 戰略提醒**：匯率已進入「主權信用危險區」。")
        with col_msg2:
            st.write("📊 **判讀筆記：**")
            st.caption("1. 壓力 > 90%：地雷已埋好。")
            st.caption("2. 價格 > 165 且斜率為負：引信觸發。")

    st.divider()
    zq_s = raw_df['ZQ=F'].ffill().dropna()
    if not zq_s.empty:
        rate = round(100 - zq_s.iloc[-1], 2)
        st.metric("短端利率 (ZQ=F)", f"{rate}%", "🔴 穩定" if rate < 5.2 else "🟢 緊繃")
            
    st.markdown("##### 🔍 風險資產 Z-Score 掃描")
    df_rz, _, _ = get_stats(["^VIX", "BTC-USD", "GC=F", "HG=F", "CL=F", "DX-Y.NYB"], raw_df)
    st.dataframe(df_rz[["資產名稱", "Z-Score", "趨勢", "現價"]], hide_index=True, use_container_width=True)

# --- Tab 4 ---
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
                chart_df["60日季線"] = ma60
            st.line_chart(chart_df)
