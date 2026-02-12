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
# 📖 說明手冊 (封關長假增強版)
# ==========================================
with st.expander("📖 查看：操盤判讀邏輯 & 交易心法 (點擊展開)", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        ### 🔍 數據判讀 (🔴多/強 | 🟢空/弱):
        1. **AI 資金雷達**：平均離差 > 0 代表資金熱絡，< 0 代表退潮。
        2. **台股戰略**：費半/中小乖離 > 0 亮紅燈。
        3. **風險雷達**：日圓 > 60MA (季線) 為安全；日圓 < 60MA 為日圓強，需警戒。
        4. **春節觀測**：利用新加坡富台期與加權指數之比例 (12.3272) 推估假期點位。
        """)
    with c2:
        st.markdown("""
        ### 🛡️ 2026 交易心法:
        * **長假風險**：2/11-2/22 封關期間，全球市場波動全看富台期 (STW=F)。
        * **避開擁擠**：Z-Score > +1.5 時需分批獲利。
        """)

# ==========================================
# 2. 數據下載 (修正代碼：STW=F 為最穩定摩台/富台期貨)
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
    "STW=F": "富台期(SGX)" 
}

high_price_list = [
    "5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "5269.TWO", "3443.TW", "2454.TW", 
    "2059.TW", "3533.TW", "3131.TWO", "3653.TW", "3293.TWO", "6409.TW", "8454.TW", "6643.TW", 
    "6415.TW", "8299.TWO", "8464.TW", "1590.TW", "2327.TW", "2330.TW", "3034.TW", "4966.TWO"
]

mag_7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "AVGO"]
all_tk = list(set(list(name_map.keys()) + high_price_list + ["SPY", "ZQ=F", "STW=F"]))

raw_df = fetch_raw_data(all_tk)

# ==========================================
# 3. 處理引擎
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

# --- Tab 1: AI 資金 ---
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

# --- Tab 2: 台股戰略 (新增春節觀測) ---
with t2:
    st.subheader("🧧 春節長假：富台期對應加權觀測 (2/11-2/22)")
    
    # 封關錨定常數
    TAIEX_CLOSE_BASE = 33605.71
    FTSE_CLOSE_BASE = 2726.15
    RATIO = TAIEX_CLOSE_BASE / FTSE_CLOSE_BASE
    
    # 抓取 STW=F 數據
    ftse_series = raw_df['STW=F'].ffill().dropna()
    if not ftse_series.empty:
        curr_ftse = ftse_series.iloc[-1]
        theo_taiex = curr_ftse * RATIO
        diff_points = theo_taiex - TAIEX_CLOSE_BASE
        diff_pct = (diff_points / TAIEX_CLOSE_BASE) * 100
        
        c1, c2, c3 = st.columns(3)
        c1.metric("新加坡富台期 (STW=F)", f"{round(curr_ftse, 2)}", f"基準: {FTSE_CLOSE_BASE}")
        c2.metric("理論加權點數", f"{round(theo_taiex, 2)}", f"{round(diff_points, 2)} Pts")
        c3.metric("預期開盤幅", f"{round(diff_pct, 2)}%", delta_color="normal" if diff_points >= 0 else "inverse")
        
        st.info(f"💡 換算公式：富台現價 {round(curr_ftse, 2)} × 封關比例 {round(RATIO, 4)} = 理論加權 {round(theo_taiex, 2)}")
    else:
        st.warning("⚠️ 暫時無法從 Yahoo Finance 獲取 STW=F 數據。請檢查網址或嘗試更換代碼為 ^FTW (富時台灣指數)。")

    st.divider()
    
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
    if not df_king.empty:
        s1.metric("當前監控檔數", f"{len(df_king)} 檔")
        s2.metric("強勢佔比", f"{int(len(df_king[df_king['乖離率']>0])/len(df_king)*100)}%")
        s3.metric("低於門檻 (濾除)", f"{len(df_filt)} 檔")
        s4.metric("族群平均 Z-Score", round(df_king['Z-Score'].mean(), 2))
        st.dataframe(df_king[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("現價", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 3: 風險雷達 (王者時間) ---
with t3:
    st.subheader("⏳ 王者時間：動態風險與 Carry Trade 壓力測試")
    jpy_s = raw_df['JPY=X'].ffill().dropna()
    if not jpy_s.empty:
        p_jpy = jpy_s.iloc[-1]
        ma60_jpy = jpy_s.rolling(60).mean().iloc[-1]
        slope_10 = (jpy_s.iloc[-1] - jpy_s.iloc[-10]) / 10
        adaptive_threshold = round(ma60_jpy * 1.05, 2) 
        stress_score = min(100, int((p_jpy / 170) * 80 + ((jpy_s.tail(20) > ma60_jpy).sum() / 20) * 20))
        
        c1, c2, c3 = st.columns(3)
        c1.metric("美元/日圓 (JPY=X)", f"{round(p_jpy, 2)}", f"{'🔴 貶值' if p_jpy > ma60_jpy else '🟢 日圓強'}")
        c2.metric("10日變動斜率", f"{round(slope_10, 2)}", "⚠️ 急速" if slope_10 > 0.5 else "✅ 平穩", delta_color="inverse" if slope_10 > 0.5 else "normal")
        c3.metric("Carry Trade 壓力", f"{stress_score}%")
        st.progress(stress_score / 100)
        
    st.divider()
    zq_s = raw_df['ZQ=F'].ffill().dropna()
    if not zq_s.empty:
        rate = round(100 - zq_s.iloc[-1], 2)
        st.metric("短端利率 (ZQ=F)", f"{rate}%", "🔴 穩定" if rate < 5.2 else "🟢 緊繃")
    
    df_rz, _, _ = get_stats(["^VIX", "BTC-USD", "GC=F", "HG=F", "CL=F", "DX-Y.NYB"], raw_df)
    st.dataframe(df_rz[["資產名稱", "Z-Score", "趨勢", "現價"]], hide_index=True, use_container_width=True)

# --- Tab 4: 半導體 ---
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
                    res_rs.append({"名稱": name_map.get(t,t), "強度(RS)": round(rs,4)})
        if res_rs:
            st.dataframe(pd.DataFrame(res_rs).sort_values("強度(RS)", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 5: 趨勢圖 ---
with t5:
    st.subheader("📈 全球資產趨勢與動態基準")
    sel = st.selectbox("選擇商品：", all_tk, format_func=lambda x: f"{name_map.get(x,x)} ({x})", key="main_trend_selector")
    if sel:
        plot_data = raw_df[sel].ffill().dropna()
        if not plot_data.empty:
            chart_df = pd.DataFrame({"現價": plot_data})
            if sel == "JPY=X":
                ma60 = plot_data.rolling(60).mean()
                chart_df["動態基準 (DAT)"] = ma60 * 1.05
                chart_df["60日季線"] = ma60
            st.line_chart(chart_df)
