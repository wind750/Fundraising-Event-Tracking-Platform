import streamlit as st
import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime
import numpy as np

# ==========================================
# 1. 系統核心設定 (佈局與時區)
# ==========================================
st.set_page_config(page_title="全球金融戰情室 (AI旗艦版)", layout="wide")
st.title("🌐 全球金融戰情室 (AI旗艦版)")

tw_tz = pytz.timezone('Asia/Taipei')
current_time = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"🕒 最後更新時間 (台灣): {current_time}")

# ==========================================
# 2. 📖 說明手冊 (確保永久存在且內容精確)
# ==========================================
with st.expander("📖 查看：操盤判讀邏輯 & 交易心法 (點擊展開)", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        ### 🔍 數據判讀 (🔴多/強 | 🟢空/弱):
        1. **AI 資金雷達**：平均離差 > 0 代表資金熱絡。
        2. **台股戰略**：費半與中小指標皆紅代表內外資同步做多。
        3. **風險雷達**：日圓匯率跌破 **60MA (季線)** 即觸發平倉預警。
        4. **Z-Score**：衡量擁擠度。超過 ±1.5 代表進入極端區間。
        """)
    with c2:
        st.markdown("""
        ### 🛡️ 2026 交易心法:
        * **避開擁擠**：當平均 Z-Score > 1.5，即使噴出也不應追高，需防範融漲末端回撤。
        * **流動性生命線**：日圓強弱（JPY=X）比任何財經新聞都更能預告科技股的修正。
        * **數據稽核**：千金股門檻定為 800 元，確保只追蹤具備實質動能的高價指標。
        """)

# ==========================================
# 3. 數據下載 (Period="5y" 解決 nan 問題)
# ==========================================

@st.cache_data(ttl=3600)
def fetch_complete_data(tickers):
    # 抓取 5 年數據，確保 504 根 K 線的 Z-Score 計算穩定
    data = yf.download(tickers, period="5y", progress=False)
    if 'Close' in data.columns:
        return data['Close']
    return data

# 名稱對照與追蹤列表
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
    "6415.TW", "8299.TWO", "8464.TW", "1590.TW", "2327.TW", "2330.TW", "3034.TW", "4966.TWO", "3680.TW"
]

mag_7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "AVGO"]
all_tk = list(set(list(name_map.keys()) + high_price_list + ["SPY", "ZQ=F"]))

raw_df = fetch_complete_data(all_tk)

# ==========================================
# 4. 數據處理引擎 (強化數據對齊與透明度)
# ==========================================

def get_engine_data(tk_list, source_df, threshold=0):
    p, f, e = [], [], [] # Processed, Filtered, Errors
    for tk in tk_list:
        if tk not in source_df.columns:
            e.append(tk)
            continue
        series = source_df[tk].ffill().dropna()
        if series.empty or len(series) < 30:
            e.append(tk)
            continue
            
        now_p = series.iloc[-1]
        if threshold > 0 and now_p < threshold:
            f.append({"代號": tk, "現價": round(now_p, 2)})
            continue
            
        ma20 = series.rolling(20).mean().iloc[-1]
        bias = (now_p - ma20) / ma20 * 100
        # 兩年 Z-Score 邏輯
        win = series.tail(504)
        z_val = (now_p - win.mean()) / win.std() if win.std() != 0 else 0
        
        p.append({
            "代號": tk, "資產名稱": name_map.get(tk, tk), 
            "趨勢": "🔴強勢" if bias > 0 else "🟢弱勢", 
            "現價": round(now_p, 2), "乖離率": round(bias, 2), "Z-Score": round(z_val, 2)
        })
    return pd.DataFrame(p), pd.DataFrame(f), e

# ==========================================
# 5. 分頁顯示邏輯
# ==========================================
tabs = st.tabs(["💀 AI 資金", "🇹🇼 台股戰略", "🚀 風險雷達", "💎 半導體", "📈 趨勢圖", "⚖️ 法人估值"])

# --- Tab 1: AI 資金 (修正渲染亂碼) ---
with tabs[0]:
    df_ai, _, _ = get_engine_data(mag_7 + ["^IXIC", "SMH"], raw_df)
    if not df_ai.empty:
        c1, c2 = st.columns([1, 2])
        avg_bias = df_ai['乖離率'].mean()
        with c1:
            # 修正：杜絕 DeltaGenerator 文字渲染錯誤
            if avg_bias > 0:
                st.error(f"### 🔴 資金湧入\n平均離差: {round(avg_bias, 2)}%")
            else:
                st.success(f"### 🟢 資金退潮\n平均離差: {round(avg_bias, 2)}%")
            st.metric("整體擁擠度 (Z-Score)", round(df_ai['Z-Score'].mean(), 2))
        with c2:
            st.dataframe(df_ai[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("乖離率", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 2: 台股戰略 (數據彙整與稽核中心) ---
with tabs[1]:
    st.subheader("🇹🇼 台股戰術領先指標")
    df_l, _, _ = get_engine_data(["SOXX", "00733.TW", "DX-Y.NYB", "^TNX"], raw_df)
    m1, m2, m3, m4 = st.columns(4)
    def draw_m(col, ticker, name, inv=False):
        r = df_l[df_l['代號']==ticker]
        if not r.empty: col.metric(name, f"{r['現價'].values[0]}", f"{r['乖離率'].values[0]}%", delta_color="normal" if not inv else "inverse")
    draw_m(m1, "SOXX", "費半 ETF")
    draw_m(m2, "00733.TW", "富邦中小")
    draw_m(m3, "DX-Y.NYB", "美元指數", inv=True)
    draw_m(m4, "^TNX", "美債10Y", inv=True)
    
    st.divider()
    st.subheader("👑 千金股動態觀察 (門檻 800 元)")
    df_k, df_f, fail_list = get_engine_data(high_price_list, raw_df, threshold=800)
    
    # 彙整數據卡片
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("達標監控檔數", f"{len(df_k)} 檔")
    s2.metric("強勢佔比", f"{int(len(df_k[df_king['乖離率']>0])/len(df_k)*100)}%" if len(df_k)>0 else "0%")
    s3.metric("已濾除 (低於門檻)", f"{len(df_f)} 檔")
    s4.metric("平均 Z-Score", round(df_k['Z-Score'].mean(), 2) if not df_k.empty else 0)
    
    st.dataframe(df_k[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("現價", ascending=False), hide_index=True, use_container_width=True)
    
    with st.expander("🔍 數據稽核中心 (數據為何變動？)"):
        ac1, ac2 = st.columns(2)
        with ac1: st.write("**🛡️ 已濾除名單 (現價 < 800)**"); st.dataframe(df_f, hide_index=True)
        with ac2: st.write("**❌ 系統下載失敗 (API 缺失)**"); st.write(fail_list if fail_list else "名單全部下載成功。")

# --- Tab 3: 風險雷達 (修正日圓顏色邏輯) ---
with tabs[2]:
    st.subheader("🚀 市場風險雷達 (流動性監控)")
    c1, c2 = st.columns(2)
    with c1:
        js = raw_df['JPY=X'].ffill().dropna()
        if not js.empty:
            now_j, ma60_j = js.iloc[-1], js.rolling(60).mean().iloc[-1]
            # 修正：匯率越過季線(貶值)為紅/安全，跌破季線(升值)為綠/警戒
            safe = now_j > ma60_j
            st.metric("日圓匯率 (JPY=X)", f"{round(now_j, 2)}", 
                      f"{'🔴 安全' if safe else '🟢 警戒'} (季線:{round(ma60_j, 2)})", 
                      delta_color="normal" if safe else "inverse")
    with c2:
        zs = raw_df['ZQ=F'].ffill().dropna()
        if not zs.empty:
            st.metric("短端利率 (ZQ=F)", f"{round(100 - zs.iloc[-1], 2)}%", "🔴 穩定" if (100-zs.iloc[-1]) < 5.2 else "🟢 緊繃")
            
    st.divider()
    st.markdown("##### 🔍 風險資產擁擠度掃描")
    df_rz, _, _ = get_engine_data(["^VIX", "BTC-USD", "GC=F", "HG=F", "CL=F", "DX-Y.NYB"], raw_df)
    st.dataframe(df_rz[["資產名稱", "Z-Score", "趨勢", "現價"]], hide_index=True, use_container_width=True)

# --- Tab 4: 相對強度 (解決日期不對齊 None 問題) ---
with tabs[3]:
    st.subheader("💎 科技巨頭與半導體強度 (vs SPY)")
    b_s = raw_df['SPY'].ffill().dropna()
    if len(b_s) > 60:
        b_ret = (b_s.iloc[-1] - b_s.iloc[-60]) / b_s.iloc[-60]
        c_list = ["SOXX", "2330.TW"] + mag_7
        res_rs = []
        for t in c_list:
            if t in raw_df.columns:
                t_s = raw_df[t].ffill().dropna()
                # 關鍵：強制對齊交易日期
                shared = t_s.index.intersection(b_s.index)
                if len(shared) > 60:
                    t_val = t_s.loc[shared]
                    ret = (t_val.iloc[-1] - t_val.iloc[-60]) / t_val.iloc[-60]
                    rs = (1 + ret) / (1 + b_ret)
                    clr = "background-color: rgba(255, 50, 50, 0.15)" if rs > 1 else "background-color: rgba(50, 255, 50, 0.15)"
                    res_rs.append({"名稱": name_map.get(t,t), "強度(RS)": round(rs,4), "_c": clr})
        if res_rs:
            df_rs = pd.DataFrame(res_rs).sort_values("強度(RS)", ascending=False)
            st.dataframe(df_rs.style.apply(lambda x: [x['_c']]*len(x), axis=1), column_config={"_c":None}, hide_index=True, use_container_width=True)
        else: st.warning("數據對齊失敗，無法計算相對強度。")
    else: st.warning("基準數據不足。")

# --- Tab 5/6 保持穩定 ---
with tabs[4]:
    s_tk = st.selectbox("選擇商品：", all_tk, format_func=lambda x: f"{name_map.get(x,x)} ({x})")
    if s_tk: st.line_chart(raw_df[s_tk].dropna())

with tabs[5]:
    v_tk = st.text_input("輸入股票代號", value="2330.TW").upper()
    if v_tk:
        try:
            info = yf.Ticker(v_tk).info
            st.metric(f"{info.get('longName')} 現價", f"${info.get('currentPrice')}")
            g_rate = st.slider("預估成長率 (%)", 1, 50, 15)
            peg = info.get('trailingPE', 0)/g_rate if g_rate else 0
            st.write(f"PEG: {round(peg, 2)} ({'🟢低估' if peg < 1.2 else '🔴高估'})")
        except: st.error("數據獲取失敗")
