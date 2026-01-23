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
# 2. 📖 說明手冊 (確保永久存在於標題下方)
# ==========================================
with st.expander("📖 查看：操盤判讀邏輯 & 交易心法 (點擊展開)", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        ### 🔍 數據判讀 (🔴多/強 | 🟢空/弱):
        1. **AI 資金雷達**：監控 AI 巨頭。平均離差 < 0 即為資金退潮。
        2. **台股戰略**：費半與中小指標皆紅代表內外資同步做多。
        3. **風險雷達**：日圓跌破季線(60MA) = **Carry Trade 平倉警報**。
        4. **Z-Score**：衡量擁擠度。> +1.5 過度擁擠；< -1.5 過度悲觀。
        """)
    with c2:
        st.markdown("""
        ### 🛡️ 2026 交易心法:
        * **部位控管**：流動性指標（日圓/利率）亮綠燈時，持倉降至 **3~5 成**。
        * **拒絕 FOMO**：融漲末端暴漲多為誘多，須配合 Z-Score 觀察擁擠度。
        * **稽核邏輯**：千金股門檻設為 800 元，低於門檻者自動濾除至稽核中心。
        """)

# ==========================================
# 3. 數據下載與快取 (Period="5y" 確保 Z-Score 穩定)
# ==========================================

@st.cache_data(ttl=3600)
def fetch_all_data(tickers):
    # 下載 5 年數據以確保兩年回測 (504天) 絕對穩定
    try:
        data = yf.download(tickers, period="5y", progress=False)
        return data
    except:
        return pd.DataFrame()

# 中英文映射與追蹤清單
name_map = {
    "NVDA": "輝達", "AAPL": "蘋果", "MSFT": "微軟", "GOOGL": "Google", "AMZN": "亞馬遜", 
    "META": "Meta", "TSLA": "特斯拉", "AVGO": "博通", "SPY": "標普 500", "QQQ": "納指 ETF",
    "SOXX": "費半 ETF", "2330.TW": "台積電", "2454.TW": "聯發科", "00733.TW": "富邦中小",
    "DX-Y.NYB": "美元指數", "^TNX": "美債10年", "JPY=X": "美元/日圓", "ZQ=F": "利率期貨",
    "^VIX": "VIX 恐慌", "BTC-USD": "比特幣", "GC=F": "黃金", "HG=F": "期貨銅", "CL=F": "原油",
    "^IXIC": "納斯達克", "SMH": "半導體ETF", "^SOX": "費半指數", "^TWII": "台灣加權", "^TWO": "櫃買指數"
}

# 擴大版高價股 (30檔)
high_price_track = [
    "5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "5269.TWO", "3443.TW", "2454.TW", 
    "2059.TW", "3533.TW", "3131.TWO", "3653.TW", "3293.TWO", "6409.TW", "8454.TW", "6643.TW", 
    "6415.TW", "8299.TWO", "8464.TW", "1590.TW", "2327.TW", "2330.TW", "3034.TW", "4966.TWO",
    "6641.TW", "6805.TW", "9910.TW", "3680.TW", "6679.TW", "3017.TW"
]

mag_7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "AVGO"]
risk_list = ["^VIX", "BTC-USD", "GC=F", "HG=F", "CL=F", "DX-Y.NYB"]
all_tickers = list(set(list(name_map.keys()) + high_price_track + ["SPY", "ZQ=F"]))

raw_data = fetch_all_data(all_tickers)

# ==========================================
# 4. 數據處理引擎 (包含 Z-Score 與 稽核)
# ==========================================

def process_data(ticker_list, df_source, threshold=0):
    processed, filtered, failed = [], [], []
    data_close = df_source['Close'] if 'Close' in df_source.columns else df_source
    
    for tk in ticker_list:
        if tk not in data_close.columns or data_close[tk].dropna().empty:
            failed.append(tk)
            continue
            
        series = data_close[tk].fillna(method='ffill').dropna()
        price = series.iloc[-1]
        
        # 門檻過濾 (針對千金股)
        if threshold > 0 and price < threshold:
            filtered.append({"代號": tk, "現價": round(price, 2)})
            continue
            
        # 乖離率與 Z-Score (固定兩年回測 504 天)
        ma20 = series.rolling(20).mean().iloc[-1]
        bias = (price - ma20) / ma20 * 100
        
        window = series.tail(504)
        if len(window) >= 30: # 確保有足夠數據計算標準差
            z = (price - window.mean()) / window.std() if window.std() != 0 else 0
        else:
            z = 0
            
        processed.append({
            "代號": tk, "資產名稱": name_map.get(tk, tk), 
            "趨勢": "🔴強勢" if bias > 0 else "🟢弱勢", 
            "現價": round(price, 2), "乖離率": round(bias, 2), "Z-Score": round(z, 2)
        })
    return pd.DataFrame(processed), pd.DataFrame(filtered), failed

# ==========================================
# 5. 分頁佈局 (保證所有分頁內容完整)
# ==========================================
tabs = st.tabs(["💀 AI 資金", "🇹🇼 台股戰略", "🚀 風險雷達", "💎 半導體", "📈 趨勢圖", "⚖️ 法人估值"])
tab_ai, tab_tw, tab_risk, tab_semi, tab_chart, tab_valuation = tabs

# --- Tab 1: AI 資金 ---
with tab_ai:
    df_ai, _, _ = process_data(mag_7 + ["^IXIC", "SMH"], raw_data)
    if not df_ai.empty:
        c1, c2 = st.columns([1, 2])
        with c1:
            avg_bias = df_ai['乖離率'].mean()
            label = "🔴 資金湧入" if avg_bias > 0 else "🟢 資金退潮"
            st.error(f"### {label}\n平均離差: {round(avg_bias, 2)}%") if avg_bias > 0 else st.success(f"### {label}\n平均離差: {round(avg_bias, 2)}%")
            st.metric("整體擁擠度 (Z-Score)", round(df_ai['Z-Score'].mean(), 2))
        with c2:
            st.dataframe(df_ai[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("乖離率", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 2: 台股戰略 (包含整體數據與稽核) ---
with tab_tw:
    st.subheader("🇹🇼 台股戰略領先指標")
    df_lead, _, _ = process_data(["SOXX", "00733.TW", "DX-Y.NYB", "^TNX"], raw_data)
    if not df_lead.empty:
        m1, m2, m3, m4 = st.columns(4)
        def draw_m(col, ticker, name, inv=False):
            r = df_lead[df_lead['代號']==ticker]
            if not r.empty: col.metric(name, f"{r['現價'].values[0]}", f"{r['乖離率'].values[0]}%", delta_color="normal" if not inv else "inverse")
        draw_m(m1, "SOXX", "費半 ETF")
        draw_m(m2, "00733.TW", "富邦中小")
        draw_m(m3, "DX-Y.NYB", "美元指數", inv=True)
        draw_m(m4, "^TNX", "美債10Y", inv=True)

    st.divider()
    st.subheader("👑 千金股與高價股觀察池")
    df_king, df_filt, fail_tk = process_data(high_price_track, raw_data, threshold=800)
    
    if not df_king.empty:
        # --- 恢復整體統計數據卡片 ---
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("當前監控檔數", f"{len(df_king)} 檔")
        s2.metric("強勢佔比", f"{int(len(df_king[df_king['乖離率']>0])/len(df_king)*100)}%")
        s3.metric("低於門檻 (濾除)", f"{len(df_filt)} 檔")
        s4.metric("族群平均 Z-Score", round(df_king['Z-Score'].mean(), 2))
        
        st.dataframe(df_king[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("現價", ascending=False), hide_index=True, use_container_width=True)
    
    with st.expander("🔍 數據稽核與診斷中心"):
        ac1, ac2 = st.columns(2)
        with ac1: st.write("**🛡️ 已濾除名單 (價格 < 800)**"); st.dataframe(df_filt, hide_index=True)
        with ac2: st.write("**❌ 下載失敗名單**"); st.write(fail_tk if fail_tk else "無失敗項")

# --- Tab 3: 風險雷達 ---
with tab_risk:
    st.subheader("🚀 市場風險雷達 (流動性)")
    risk_raw = raw_data['Close'] if 'Close' in raw_data.columns else raw_data
    c1, c2 = st.columns(2)
    with c1:
        if 'JPY=X' in risk_raw.columns:
            p, ma60 = risk_raw['JPY=X'].iloc[-1], risk_raw['JPY=X'].rolling(60).mean().iloc[-1]
            st.metric("日圓匯率 (JPY=X)", f"{round(p, 2)}", "🔴 安全" if p > ma60 else "🟢 警戒", delta_color="normal" if p > ma60 else "inverse")
    with c2:
        if 'ZQ=F' in risk_raw.columns:
            rate = round(100 - risk_raw['ZQ=F'].iloc[-1], 2)
            st.metric("短端利率 (ZQ=F)", f"{rate}%", "🔴 穩定" if rate < 5.2 else "🟢 緊繃")
    
    st.divider()
    st.markdown("##### 🔍 全球風險資產 Z-Score 掃描")
    df_risk_z, _, _ = process_data(risk_list, raw_data)
    st.dataframe(df_risk_z[["資產名稱", "Z-Score", "趨勢", "現價"]], hide_index=True, use_container_width=True)

# --- Tab 4: 半導體相對強度 (確保巨頭全在) ---
with tab_semi:
    st.subheader("💎 科技巨頭與半導體強度 (vs SPY)")
    if 'SPY' in risk_raw.columns:
        bench_ret = (risk_raw['SPY'].iloc[-1] - risk_raw['SPY'].iloc[-60]) / risk_raw['SPY'].iloc[-60]
        # 合併 Mag 7 + 核心半導體
        semi_mag_list = ["SOXX", "2330.TW"] + mag_7
        res_rs = []
        for t in semi_mag_list:
            if t in risk_raw.columns:
                tgt_s = risk_raw[t].dropna()
                if len(tgt_s) > 60:
                    ret_s = (tgt_s.iloc[-1] - tgt_s.iloc[-60]) / tgt_s.iloc[-60]
                    rs_val = (1 + ret_s) / (1 + bench_ret)
                    clr_rs = "background-color: rgba(255, 50, 50, 0.15)" if rs_val > 1 else "background-color: rgba(50, 255, 50, 0.15)"
                    res_rs.append({"名稱": name_map.get(t,t), "強度(RS)": round(rs_val,4), "_c": clr_rs})
        
        if res_rs:
            df_rs = pd.DataFrame(res_rs).sort_values("強度(RS)", ascending=False)
            st.dataframe(df_rs.style.apply(lambda x: [x['_c']]*len(x), axis=1), column_config={"_c":None}, hide_index=True, use_container_width=True)
        else:
            st.warning("數據不足，無法計算強度。")

# --- 其餘分頁 ---
with tab_chart:
    sel_tk = st.selectbox("選擇商品：", all_tickers, format_func=lambda x: f"{name_map.get(x,x)} ({x})")
    if sel_tk: st.line_chart(risk_raw[sel_tk].dropna())

with tab_valuation:
    v_tk = st.text_input("輸入代號", value="2330.TW").upper()
    if v_tk:
        try:
            info = yf.Ticker(v_tk).info
            st.write(f"### {info.get('longName')} | 現價: ${info.get('currentPrice')}")
            g_val = st.slider("預估成長率 (%)", 1, 50, 15)
            peg_val = info.get('trailingPE', 0)/g_val if g_val else 0
            st.metric("PEG 估值", round(peg_val, 2), "🟢 低估" if peg_val < 1.2 else "🔴 高估", delta_color="inverse")
        except: st.error("數據獲取失敗")
