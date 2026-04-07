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
st.set_page_config(page_title="全球金融戰情室 (AI旗艦版)", layout="wide")
st.title("🌐 全球金融戰情室 (AI旗艦版)")

tw_tz = pytz.timezone('Asia/Taipei')
current_time = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"🕒 最後更新時間 (台灣): {current_time}")

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
        """)
    with c2:
        st.markdown("""
        ### 🛡️ 2026 交易心法:
        * **避開擁擠**：Z-Score > +1.5 時需分批獲利。
        * **流動性警報**：當日圓匯率跌破季線，代表平倉潮隨時啟動。
        """)

# ==========================================
# 2. 數據下載
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
t1, t2, t3, t4, t5, t_poly = st.tabs(["💀 AI 資金", "🇹🇼 台股戰略", "🚀 風險雷達", "💎 半導體", "📈 主要市場", "🔮 真金白銀下注預測"])

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
    if not df_king.empty:
        s2.metric("強勢佔比", f"{int(len(df_king[df_king['乖離率']>0])/len(df_king)*100)}%")
        s4.metric("族群平均 Z-Score", round(df_king['Z-Score'].mean(), 2))
    s3.metric("低於門檻 (濾除)", f"{len(df_filt)} 檔")
    st.dataframe(df_king[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("現價", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 3 (王者時間) ---
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
        else: ct_label, ct_delta, ct_status_msg = "🛡️ 穩定套利 (Carry)", "normal", "💡 **正常：** 套利空間穩定。"

        c1, c2, c3 = st.columns(3)
        with c1: st.metric("名目匯率 (JPY=X)", f"{round(p_jpy, 2)}", f"{'🔴 貶值趨勢' if p_jpy > ma60_jpy else '🟢 日圓轉強'}")
        with c2: st.metric("10日變動斜率", f"{round(slope_10, 2)}", "⚠️ 急速" if slope_10 > 0.5 else "✅ 平穩", delta_color="inverse" if slope_10 > 0.5 else "normal")
        with c3: st.metric("Carry Trade 壓力", f"{stress_score}%", ct_label, delta_color=ct_delta); st.progress(stress_score / 100)

        st.divider()
        st.info(ct_status_msg)
    
    st.markdown("##### 🔍 風險資產 Z-Score 掃描")
    df_rz, _, _ = get_stats(["^VIX", "BTC-USD", "GC=F", "HG=F", "CL=F", "DX-Y.NYB"], raw_df)
    st.dataframe(df_rz[["資產名稱", "Z-Score", "趨勢", "現價"]], hide_index=True, use_container_width=True)

# --- Tab 4 ---
with t4:
    st.subheader("💎 科技巨頭與半導體強度 (vs SPY)")
    bench_s = raw_df['SPY'].ffill().dropna()
    if len(bench_s) > 60:
        bench_ret = (bench_s.iloc[-1] - bench_s.iloc[-60]) / bench_s.iloc[-60]
        res_rs = []
        for t in (["SOXX", "2330.TW"] + mag_7):
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
    st.subheader("📈 主要市場趨勢")
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
            st.metric("當前價格", round(plot_data.iloc[-1], 2))

# --- Tab 6: 真金白銀下注預測 (清淨翻譯版 - 嚴格縮排) ---
with t_poly:
    st.subheader("🔮 真金白銀下注預測 (全球 Top 5 焦點事件)")
    st.caption("數據來源：Manifold Markets | 已過濾隨機噪音。")
    
    @st.cache_data(ttl=300)
    def fetch_manifold_events_filtered():
        try:
            url = "https://api.manifold.markets/v0/markets?limit=50"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if res.status_code == 200:
                markets = res.json()
                noise = ["coin", "flip", "heads", "tails", "random", "shuffle"]
                filtered = []
                for m in markets:
                    title = m.get('question', '').lower()
                    if m.get('outcomeType') == 'BINARY' and m.get('volume', 0) > 0 and not any(kw in title for kw in noise):
                        filtered.append(m)
                return sorted(filtered, key=lambda x: x.get('volume', 0), reverse=True)[:5]
            return []
        except:
            return []

    events_data = fetch_manifold_events_filtered()
    st.divider()
    
    if events_data:
        translator = GoogleTranslator(source='en', target='zh-TW')
        for event in events_data:
            title_en = event.get('question', '未知事件')
            prob_yes = event.get('probability', 0)
            if prob_yes is None: continue
            
            try: title_zh = translator.translate(title_en)
            except: title_zh = f"{title_en} (翻譯暫停)"
                
            st.markdown(f"#### 🏷️ {title_zh}")
            st.caption(f"原文: {title_en} | 💰 總量: ${int(event.get('volume', 0)):,}")
            
            c1, c2 = st.columns([1, 4])
            with c1: st.metric("Yes", f"{round(prob_yes*100, 1)}%", delta_color="off")
            with c2: st.progress(min(1.0, max(0.0, prob_yes)))
            
            c3, c4 = st.columns([1, 4])
            with c3: st.metric("No", f"{round((1-prob_yes)*100, 1)}%", delta_color="off")
            with c4: st.progress(min(1.0, max(0.0, 1-prob_yes)))
            st.write("---")
    else:
        st.info("正在擷取重大事件中...")
