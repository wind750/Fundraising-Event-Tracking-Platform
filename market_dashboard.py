import streamlit as st
import yfinance as yf
import pandas as pd

# === 設定網頁格式 ===
st.set_page_config(page_title="全球資金雷達 (中文精簡版)", layout="wide")
st.title("🌏 全球資金流向雷達 (中文精簡版)")
st.markdown("""
**紅色** 🔴 = 強勢/上漲/資金湧入 | **綠色** 🟢 = 弱勢/下跌/資金撤出  
新增指標：**美國10年債殖利率** (地心引力) & **HYG/TLT 比率** (風險胃口)
""")

# === 1. 建立中文翻譯對照表 ===
name_map = {
    "^SOX": "費城半導體",
    "BTC-USD": "比特幣",
    "HG=F": "銅期貨 (實體經濟)",
    "AUDJPY=X": "澳幣/日圓 (風險情緒)",
    "DX-Y.NYB": "美元指數",
    "GC=F": "黃金期貨",
    "JPY=X": "美元/日圓 (匯率)",
    "^VIX": "VIX 恐慌指數",
    "^TWII": "台灣加權指數",
    "0050.TW": "元大台灣50",
    "^GSPC": "S&P 500",
    "^N225": "日經 225 指數",
    "^TNX": "美國10年公債殖利率",
    "HYG": "高收益債",
    "TLT": "美債20年"
}

# === 定義資產分類 ===
assets = {
    "1. 領先指標 (聰明錢)": ["^SOX", "BTC-USD", "HG=F", "AUDJPY=X"],
    "2. 避險資產 (資金避風港)": ["DX-Y.NYB", "GC=F", "JPY=X", "^VIX"],
    "3. 風險資產 (股市)": ["^TWII", "0050.TW", "^GSPC", "^N225"]
}

# === 核心運算函數 (優化欄位順序) ===
def get_data(ticker_list):
    results = []
    for ticker in ticker_list:
        try:
            df = yf.download(ticker, period="3mo", progress=False)
            if not df.empty:
                price = df['Close'].iloc[-1]
                if isinstance(price, pd.Series): price = price.item()
                
                ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
                if isinstance(ma20, pd.Series): ma20 = ma20.item()
                if ma20 == 0: ma20 = price 
                
                bias = (price - ma20) / ma20 * 100
                
                # 狀態判斷
                status = "🔴 強勢" if bias > 0 else "🟢 弱勢"
                
                # 翻譯名稱
                ch_name = name_map.get(ticker, ticker)
                
                results.append({
                    "商品名稱": ch_name,
                    "狀態": status,           # <--- 把狀態移到第二欄
                    "現價": round(price, 2),
                    "乖離率(%)": round(bias, 2)
                    # 移除了「原始代號」欄位以節省空間
                })
        except:
            pass
    return pd.DataFrame(results)

# === 介面佈局 ===
col1, col2, col3 = st.columns(3)

# 這次我們不顯示 index，也不顯示多餘欄位，讓紅綠燈緊貼著名稱
with col1:
    st.subheader("🚀 領先指標")
    df1 = get_data(assets["1. 領先指標 (聰明錢)"])
    st.dataframe(df1, hide_index=True, use_container_width=True)

with col2:
    st.subheader("🛡️ 避險資產")
    df2 = get_data(assets["2. 避險資產 (資金避風港)"])
    st.dataframe(df2, hide_index=True, use_container_width=True)

with col3:
    st.subheader("📉 股市現況")
    df3 = get_data(assets["3. 風險資產 (股市)"])
    st.dataframe(df3, hide_index=True, use_container_width=True)

# === 深層資金流向 ===
st.divider()
st.subheader("🧠 法人視野：深層資金流向")
c1, c2 = st.columns(2)

with c1:
    st.info("📊 **美國10年債殖利率** - 股市的地心引力")
    try:
        tnx_df = yf.download("^TNX", period="5d", progress=False)
        if not tnx_df.empty:
            tnx_val = tnx_df['Close'].iloc[-1]
            if isinstance(tnx_val, pd.Series): tnx_val = tnx_val.item()
            tnx_prev = tnx_df['Close'].iloc[0]
            if isinstance(tnx_prev, pd.Series): tnx_prev = tnx_prev.item()
            tnx_change = tnx_val - tnx_prev
            st.metric("目前殖利率 (越高越不利)", f"{round(tnx_val, 2)}%", f"{round(tnx_change, 2)}", delta_color="inverse")
    except:
        st.write("資料讀取中...")

with c2:
    st.info("🦁 **風險胃口指標 (HYG / TLT)** - 資金敢不敢衝")
    try:
        data = yf.download(["HYG", "TLT"], period="3mo", progress=False)
        if not data.empty:
            closes = data['Close'].dropna()
            if 'HYG' in closes.columns and 'TLT' in closes.columns:
                ratio_series = closes['HYG'] / closes['TLT']
                curr_ratio = ratio_series.iloc[-1]
                ma20_ratio = ratio_series.rolling(window=20).mean().iloc[-1]
                delta = curr_ratio - ma20_ratio
                status_text = "🔴 資金貪婪 (利多)" if delta > 0 else "🟢 資金恐慌 (利空)"
                st.metric("風險胃口比率", round(curr_ratio, 4), status_text)
    except:
        st.error("計算錯誤")

# === 趨勢檢視器 ===
st.divider()
st.subheader("📈 趨勢檢視器")
all_tickers = assets["1. 領先指標 (聰明錢)"] + assets["2. 避險資產 (資金避風港)"] + assets["3. 風險資產 (股市)"] + ["^TNX", "HYG", "TLT"]
options_display = [f"{name_map.get(t, t)} ({t})" for t in all_tickers]
selected_option = st.selectbox("選擇你想查看走勢的商品：", options_display, index=0)

if selected_option:
    selected_ticker = selected_option.split("(")[-1].replace(")", "")
    selected_name = selected_option.split("(")[0]
    st.write(f"正在顯示 **{selected_name}** 過去 3 個月的走勢...")
    try:
        chart_df = yf.download(selected_ticker, period="3mo", progress=False)
        if not chart_df.empty:
            st.line_chart(chart_df['Close'])
    except:
        st.write("無法顯示圖表")