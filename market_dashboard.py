import streamlit as st
import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime
import numpy as np
import requests
import json

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
        4. **Z-Score**：基於兩年統計，衡量籌碼擁擠度。
        """)
    with c2:
        st.markdown("""
        ### 🛡️ 2026 交易心法:
        * **避開擁擠**：Z-Score > +1.5 時需分批獲利。
        * **流動性警報**：當日圓匯率跌破季線，代表平倉潮隨時啟動。
        * **預測市場機率**：當極端事件（如戰爭、降息）的預測機率達 90% 以上，代表華爾街已完全定價 (Priced In)。
        """)

# ==========================================
# 2. 數據下載
# ==========================================

@st.cache_data(ttl=3600)
def fetch_global_data(tickers):
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
    "RSP": "S&P500 等權重", "HYG": "高收益債", "LQD": "投資級債", "AUDJPY=X": "澳幣/日圓", 
    "0050.TW": "台灣50", "^GSPC": "S&P 500", "^N225": "日經225"
}

high_price_pool = [
    "5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "5269.TWO", "3443.TW", "2454.TW", 
    "2059.TW", "3533.TW", "3131.TWO", "3653.TW", "3293.TWO", "6409.TW", "8454.TW", "6643.TW", 
    "6415.TW", "8299.TWO", "8464.TW", "1590.TW", "2327.TW", "2330.TW", "3034.TW", "4966.TWO"
]

mag_7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "AVGO"]

radar_list = ["^SOX", "BTC-USD", "HG=F", "AUDJPY=X", "DX-Y.NYB", "GC=F", "JPY=X", "^VIX", "^TWII", "0050.TW", "^GSPC", "^N225"]
breadth_list = ["RSP", "HYG", "LQD"]

all_tk = list(set(list(name_map.keys()) + high_price_pool + radar_list + breadth_list + ["SPY", "ZQ=F"]))
raw_df = fetch_global_data(all_tk)

def get_clean_stats(tk_list, source_df, threshold=0):
    processed, filtered, failed = [], [], []
    for tk in tk_list:
        if tk not in source_df.columns:
            failed.append(tk)
            continue
        series = source_df[tk].ffill().dropna()
        if series.empty:
            failed.append(tk)
            continue
            
        p = series.iloc[-1]
        if threshold > 0 and p < threshold:
            filtered.append({"代號": tk, "現價": round(p, 2)})
            continue
            
        ma20 = series.rolling(20).mean().iloc[-1]
        bias = (p - ma20) / ma20 * 100
        win = series.tail(504)
        z = (p - win.mean()) / win.std() if len(win) > 30 and win.std() != 0 else 0
        
        processed.append({
            "代號": tk, "資產名稱": name_map.get(tk, tk), 
            "趨勢": "🔴強勢" if bias > 0 else "🟢弱勢", 
            "現價": round(p, 2), "乖離率": round(bias, 2), "Z-Score": round(z, 2)
        })
    return pd.DataFrame(processed), pd.DataFrame(filtered), failed

# ==========================================
# 4. 分頁佈局
# ==========================================
t_ai, t_tw, t_risk, t_semi, t_chart, t_poly = st.tabs(["💀 AI 資金", "🇹🇼 台股戰略", "🚀 風險雷達", "💎 半導體", "📈 趨勢圖", "🔮 預測市場"])

# --- Tab 1 ---
with t_ai:
    df_ai, _, _ = get_clean_stats(mag_7 + ["^IXIC", "SMH"], raw_df)
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
with t_tw:
    st.subheader("🇹🇼 台股領先指標")
    df_l, _, _ = get_clean_stats(["SOXX", "00733.TW", "DX-Y.NYB", "^TNX"], raw_df)
    m_cols = st.columns(4)
    def m_draw(col, ticker, name, inv=False):
        r = df_l[df_l['代號']==ticker]
        if not r.empty: col.metric(name, f"{r['現價'].values[0]}", f"{r['乖離率'].values[0]}%", delta_color="normal" if not inv else "inverse")
    m_draw(m_cols[0], "SOXX", "費半 ETF")
    m_draw(m_cols[1], "00733.TW", "富邦中小")
    m_draw(m_cols[2], "DX-Y.NYB", "美元指數", inv=True)
    m_draw(m_cols[3], "^TNX", "美債10Y", inv=True)
    
    st.divider()
    df_king, df_f, failed = get_clean_stats(high_price_pool, raw_df, threshold=800)
    s_cols = st.columns(4)
    s_cols[0].metric("達標監控檔數", f"{len(df_king)} 檔")
    if not df_king.empty:
        s_cols[1].metric("強勢佔比", f"{int(len(df_king[df_king['乖離率']>0])/len(df_king)*100)}%")
        s_cols[3].metric("平均 Z-Score", round(df_king['Z-Score'].mean(), 2))
    s_cols[2].metric("已濾除 (低價)", f"{len(df_f)} 檔")
    st.dataframe(df_king[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("現價", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 3 ---
with t_risk:
    st.subheader("🚀 市場風險雷達")
    st.markdown("##### 🌊 流動性劇本監控 (Carry Trade & 資金成本)")
    
    c1, c2 = st.columns(2)
    with c1:
        jpy = raw_df['JPY=X'].ffill().dropna()
        if not jpy.empty:
            now_j, ma60_j = jpy.iloc[-1], jpy.rolling(60).mean().iloc[-1]
            safe = now_j > ma60_j
            st.metric("1. 日圓套利指標 (JPY=X)", f"{round(now_j, 2)}", f"{'🔴 安全' if safe else '🟢 警戒'} (季線:{round(ma60_j, 2)})", delta_color="normal" if safe else "inverse")
    with c2:
        zq = raw_df['ZQ=F'].ffill().dropna()
        if not zq.empty:
            rate = round(100 - zq.iloc[-1], 2)
            st.metric("2. 短端資金成本 (ZQ=F)", f"{rate}%", "🔴 穩定" if rate < 5.2 else "🟢 緊繃")
            
    st.divider()
    st.markdown("##### 🦁 市場廣度 & 信用風險")
    b_msg, b_desc, c_msg, c_desc = "---", "數據不足", "---", "數據不足"
    if 'RSP' in raw_df.columns and 'SPY' in raw_df.columns:
        rsp_s, spy_s = raw_df['RSP'].ffill().dropna(), raw_df['SPY'].ffill().dropna()
        if not rsp_s.empty and not spy_s.empty:
            c_idx = rsp_s.index.intersection(spy_s.index)
            if len(c_idx) > 20:
                rsp_ret = (rsp_s.loc[c_idx][-1] - rsp_s.loc[c_idx][-20]) / rsp_s.loc[c_idx][-20]
                spy_ret = (spy_s.loc[c_idx][-1] - spy_s.loc[c_idx][-20]) / spy_s.loc[c_idx][-20]
                b_msg = "🔴 廣度佳" if rsp_ret > spy_ret else "🟢 廣度差"
                b_desc = f"RSP({round(rsp_ret*100,2)}%) vs SPY({round(spy_ret*100,2)}%)"
                
    if 'HYG' in raw_df.columns and 'LQD' in raw_df.columns:
        hyg_s, lqd_s = raw_df['HYG'].ffill().dropna(), raw_df['LQD'].ffill().dropna()
        if not hyg_s.empty and not lqd_s.empty:
            c_idx = hyg_s.index.intersection(lqd_s.index)
            if len(c_idx) > 20:
                hyg_ret = (hyg_s.loc[c_idx][-1] - hyg_s.loc[c_idx][-20]) / hyg_s.loc[c_idx][-20]
                lqd_ret = (lqd_s.loc[c_idx][-1] - lqd_s.loc[c_idx][-20]) / lqd_s.loc[c_idx][-20]
                c_msg = "🔴 追逐風險" if hyg_ret > lqd_ret else "🟢 趨避風險"
                c_desc = f"HYG({round(hyg_ret*100,2)}%) vs LQD({round(lqd_ret*100,2)}%)"

    cb1, cb2 = st.columns(2)
    with cb1: st.info(f"📊 **市場廣度**：**{b_msg}**\n\n{b_desc}")
    with cb2: st.info(f"🦁 **信用風險**：**{c_msg}**\n\n{c_desc}")

    st.divider()
    r1, r2, r3 = st.columns(3)
    df_radar1, _, _ = get_clean_stats(["^SOX", "BTC-USD", "HG=F", "AUDJPY=X"], raw_df)
    df_radar2, _, _ = get_clean_stats(["DX-Y.NYB", "GC=F", "JPY=X", "^VIX"], raw_df)
    df_radar3, _, _ = get_clean_stats(["^TWII", "0050.TW", "^GSPC", "^N225"], raw_df)
    
    with r1: st.write("**1. 領先指標**"); st.dataframe(df_radar1[["資產名稱", "趨勢", "現價"]], hide_index=True, use_container_width=True)
    with r2: st.write("**2. 避險資產**"); st.dataframe(df_radar2[["資產名稱", "趨勢", "現價"]], hide_index=True, use_container_width=True)
    with r3: st.write("**3. 股市現況**"); st.dataframe(df_radar3[["資產名稱", "趨勢", "現價"]], hide_index=True, use_container_width=True)
    
    st.divider()
    st.markdown("##### 🔍 關鍵風險資產擁擠度 (Z-Score)")
    df_rz, _, _ = get_clean_stats(["^VIX", "BTC-USD", "GC=F", "HG=F", "CL=F", "DX-Y.NYB"], raw_df)
    st.dataframe(df_rz[["資產名稱", "Z-Score", "趨勢", "乖離率", "現價"]], hide_index=True, use_container_width=True)

# --- Tab 4 ---
with t_semi:
    st.subheader("💎 科技巨頭與半導體強度 (vs SPY)")
    bench = raw_df['SPY'].ffill().dropna()
    if len(bench) > 60:
        b_ret = (bench.iloc[-1] - bench.iloc[-60]) / bench.iloc[-60]
        comp_list = ["SOXX", "2330.TW"] + mag_7
        res_rs = []
        for t in comp_list:
            if t in raw_df.columns:
                target = raw_df[t].ffill().dropna()
                common = target.index.intersection(bench.index)
                if len(common) > 60:
                    t_aligned = target.loc[common]
                    ret_t = (t_aligned.iloc[-1] - t_aligned.iloc[-60]) / t_aligned.iloc[-60]
                    rs = (1 + ret_t) / (1 + b_ret)
                    clr = "background-color: rgba(255, 50, 50, 0.15)" if rs > 1 else "background-color: rgba(50, 255, 50, 0.15)"
                    res_rs.append({"名稱": name_map.get(t,t), "強度(RS)": round(rs,4), "_c": clr})
        if res_rs:
            df_rs = pd.DataFrame(res_rs).sort_values("強度(RS)", ascending=False)
            st.dataframe(df_rs.style.apply(lambda x: [x['_c']]*len(x), axis=1), column_config={"_c":None}, hide_index=True, use_container_width=True)

# --- Tab 5 ---
with t_chart:
    sel = st.selectbox("選擇商品：", all_tk, format_func=lambda x: f"{name_map.get(x,x)} ({x})")
    if sel: st.line_chart(raw_df[sel].dropna())

# --- Tab 6: 預測市場 (切換至開放且權威的 Manifold Markets) ---
with t_poly:
    st.subheader("🔮 預測市場 (全球 Top 5 焦點事件)")
    st.caption("數據來源：Manifold Markets (全球最大預測社群) | API 完全開放，即時掌握資金對地緣政治與宏觀事件的判斷。")
    
    @st.cache_data(ttl=300)
    def fetch_manifold_events():
        try:
            # 抓取交易量最大的開放事件，並直接獲取 15 筆來過濾
            url = "https://api.manifold.markets/v0/search-markets?sort=volume&filter=open&limit=15"
            headers = {"User-Agent": "Mozilla/5.0"}
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                markets = res.json()
                # 只篩選出 Yes/No 類型的事件，取前 5 大
                binary_markets = [m for m in markets if m.get('outcomeType') == 'BINARY'][:5]
                return binary_markets
            return []
        except Exception as e:
            st.error(f"連線異常 ({e})")
            return []

    events_data = fetch_manifold_events()
    st.divider()
    
    if events_data:
        for event in events_data:
            title = event.get('question', '未知事件')
            volume = event.get('volume', 0)
            
            # Manifold 直接給出 Yes 的機率 (0~1)
            prob_yes = event.get('probability', 0)
            p1_val = prob_yes * 100
            p2_val = (1 - prob_yes) * 100
            
            st.markdown(f"#### {title}")
            st.write(f"💰 **總交易量**: ${int(volume):,}")
            
            # Yes 機率進度條
            c1, c2 = st.columns([1, 4])
            with c1: st.metric("Yes", f"{round(p1_val, 1)}%", delta_color="off")
            with c2: st.progress(min(1.0, max(0.0, prob_yes)))
            
            # No 機率進度條
            c3, c4 = st.columns([1, 4])
            with c3: st.metric("No", f"{round(p2_val, 1)}%", delta_color="off")
            with c4: st.progress(min(1.0, max(0.0, 1 - prob_yes)))
            
            st.write("---")
    else:
        st.info("目前無資料，API 擷取中...")
