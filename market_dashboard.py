import streamlit as st
import yfinance as yf
import pandas as pd

# === 設定網頁格式 ===
st.set_page_config(page_title="全球資金雷達 (AI戰情版)", layout="wide")
st.title("🌏 全球資金流向雷達 (AI戰情版)")

# 顯示沛然的觀點
st.info("""
**💡 沛然量化觀點：20 兆美元警訊** 當 Tech Index (納斯達克、費半、台股上市櫃...) 的 **「平均離差」** 開始小於零，代表 20 兆美元的資金正在同步撤出。
這是「趨勢團結」的力量，一旦形成很難逆轉。這不是預測，是讀取數據後的「預知」。
""")

st.markdown("---")

# === 1. 建立中文翻譯對照表 ===
name_map = {
    "^SOX": "費城半導體",
    "^IXIC": "納斯達克",
    "^TWII": "台股加權 (上市)",
    "^TWO": "台股櫃買 (上櫃)",  # 注意：Yahoo Finance 的櫃買資料有時會有延遲
    "SMH": "全球半導體 ETF",
    "NVDA": "輝達 (AI 指標)",
    
    "BTC-USD": "比特幣",
    "HG=F": "銅期貨",
    "AUDJPY=X": "澳幣/日圓",
    "DX-Y.NYB": "美元指數",
    "GC=F": "黃金期貨",
    "JPY=X": "美元/日圓",
    "^VIX": "VIX 恐慌指數",
    "0050.TW": "元大台灣50",
    "^TNX": "美國10年債殖利率",
    "HYG": "高收益債",
    "TLT": "美債20年"
}

# === 2. 定義資產分類 (新增 AI 科技組合) ===
assets = {
    "0. 💀 AI 科技指數 (20兆美元組合)": ["^IXIC", "^SOX", "^TWII", "^TWO", "SMH", "NVDA"],
    "1. 🚀 領先指標 (聰明錢)": ["BTC-USD", "HG=F", "AUDJPY=X"],
    "2. 🛡️ 避險資產 (資金避風港)": ["DX-Y.NYB", "GC=F", "JPY=X", "^VIX"],
    "3. 📉 其他市場": ["0050.TW", "HYG", "TLT"]
}

# === 核心運算函數 ===
def get_data(ticker_list):
    results = []
    total_bias = 0
    count = 0
    
    for ticker in ticker_list:
        try:
            df = yf.download(ticker, period="3mo", progress=False)
            if not df.empty:
                price = df['Close'].iloc[-1]
                if isinstance(price, pd.Series): price = price.item()
                
                ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
                if isinstance(ma20, pd.Series): ma20 = ma20.item()
                
                if ma20 == 0 or pd.isna(ma20): ma20 = price 
                
                bias = (price - ma20) / ma20 * 100
                
                # 累加平均離差用
                if not pd.isna(bias):
                    total_bias += bias
                    count += 1
                
                status = "🔴 強勢" if bias > 0 else "🟢 弱勢"
                ch_name = name_map.get(ticker, ticker)
                
                results.append({
                    "商品名稱": ch_name,
                    "狀態": status,
                    "現價": round(price, 2),
                    "乖離率(%)": round(bias, 2)
                })
        except:
            pass
            
    # 計算平均離差
    avg_bias = total_bias / count if count > 0 else 0
    return pd.DataFrame(results), avg_bias

# === 戰情室：AI 科技指數監控 (最上方重點) ===
st.subheader("💀 AI 科技指數監控 (沛然核心指標)")
df_tech, avg_tech_bias = get_data(assets["0. 💀 AI 科技指數 (20兆美元組合)"])

# 顯示平均離差大數字
c1, c2 = st.columns([1, 2])
with c1:
    # 判斷整體狀態
    if avg_tech_bias < 0:
        st.error(f"⚠️ **警報：全面翻負**")
        st.metric("Tech 平均離差 (關鍵)", f"{round(avg_tech_bias, 2)}%", "空方趨勢確立", delta_color="inverse")
    else:
        st.success(f"🔴 **多頭支撐**")
        st.metric("Tech 平均離差 (關鍵)", f"{round(avg_tech_bias, 2)}%", "多方趨勢", delta_color="normal")
        
    st.caption("根據貼文邏輯：若此數值轉為負數 (綠色)，且持續一段時間，即為「三同風險」確認。")

with c2:
    st.dataframe(df_tech, hide_index=True, use_container_width=True)

st.divider()

# === 一般儀表板 ===
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("🚀 領先指標")
    df1, _ = get_data(assets["1. 🚀 領先指標 (聰明錢)"])
    st.dataframe(df1, hide_index=True, use_container_width=True)

with col2:
    st.subheader("🛡️ 避險資產")
    df2, _ = get_data(assets["2. 🛡️ 避險資產 (資金避風港)"])
    st.dataframe(df2, hide_index=True, use_container_width=True)

with col3:
    st.subheader("📉 資金流向")
    # 這裡手動加上殖利率跟風險胃口
    try:
        tnx = yf.download("^TNX", period="5d", progress=False)['Close'].iloc[-1]
        if isinstance(tnx, pd.Series): tnx = tnx.item()
        st.metric("美債10年殖利率", f"{round(tnx, 2)}%")
        
        # 簡單顯示 HYG/TLT 狀態
        hyg = yf.download("HYG", period="5d", progress=False)['Close'].iloc[-1].item()
        tlt = yf.download("TLT", period="5d", progress=False)['Close'].iloc[-1].item()
        ratio = hyg/tlt
        st.metric("風險胃口 (HYG/TLT)", round(ratio, 4))
    except:
        st.write("讀取中...")

# === 互動圖表 ===
st.divider()
st.subheader("📈 趨勢檢視器")
all_tickers = [item for sublist in assets.values() for item in sublist] + ["^TNX"]
options_display = [f"{name_map.get(t, t)} ({t})" for t in all_tickers]
selected = st.selectbox("選擇商品：", options_display)

if selected:
    ticker = selected.split("(")[-1].replace(")", "")
    try:
        data = yf.download(ticker, period="6mo", progress=False)['Close']
        st.line_chart(data)
    except:
        st.error("無法顯示圖表")
