import streamlit as st
import yfinance as yf
import pandas as pd

# === 設定網頁格式 ===
st.set_page_config(page_title="全球宏觀資產配置", layout="wide")
st.title("🌐 全球宏觀資產配置 (Q4 展望版)")
st.markdown("""
**設計邏輯**：依據 2025 Q4 全球展望報告  
🔴 **紅燈** = 趨勢強勢 (站上月線) | 🟢 **綠燈** = 趨勢弱勢 (跌破月線)  
🌊 **季動能** = 過去 3 個月漲跌幅
""")

# === 1. 中文對照表 ===
name_map = {
    # 強勢區
    "VTI": "美股全市場 (巴菲特指標代理)",
    "DBB": "工業金屬 (銅/鋁/鋅)",
    "XLE": "能源類股 ETF",
    "GC=F": "黃金期貨",
    
    # 弱勢區
    "DBA": "農產品 ETF (黃豆/玉米)",
    "BTC-USD": "比特幣",
    "DOG": "放空道瓊 (反向指標代理)",
    
    # 核心市場
    "^TWII": "台灣加權指數",
    "0050.TW": "元大台灣50",
    "^GSPC": "S&P 500 (美股)",
    "000001.SS": "上證指數 (A股)",
    
    # 利率債券
    "^TNX": "美國10年債殖利率",
    "TLT": "美國20年公債 ETF",
    "LQD": "投資級公司債" 
}

# === 2. 資產分類 (移除報告點名等字眼) ===
assets = {
    "1. 🔥 強勢動能區": ["VTI", "DBB", "XLE", "GC=F"],
    "2. ❄️ 弱勢動能區": ["DBA", "BTC-USD", "DOG"],
    "3. 🌏 核心市場 (美/中/台)": ["^GSPC", "000001.SS", "^TWII", "0050.TW"],
    "4. 🏦 利率與債券": ["^TNX", "TLT", "LQD"]
}

# === 3. 核心運算 ===
def get_data(ticker_list):
    results = []
    for ticker in ticker_list:
        try:
            # 下載 4 個月的資料
            df = yf.download(ticker, period="4mo", progress=False)
            if not df.empty:
                price = df['Close'].iloc[-1]
                if isinstance(price, pd.Series): price = price.item()
                
                # 1. 趨勢信號
                ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
                if isinstance(ma20, pd.Series): ma20 = ma20.item()
                bias = (price - ma20) / ma20 * 100
                trend_status = "🔴多頭" if bias > 0 else "🟢空頭"
                
                # 2. 季動能 (3個月漲跌幅)
                if len(df) > 60:
                    price_q_ago = df['Close'].iloc[-60]
                    if isinstance(price_q_ago, pd.Series): price_q_ago = price_q_ago.item()
                    q_momentum = (price - price_q_ago) / price_q_ago * 100
                else:
                    q_momentum = 0
                
                # 顯示顏色
                mom_str = f"{round(q_momentum, 2)}%"
                if q_momentum > 0: mom_str = f"🔴 +{mom_str}"
                else: mom_str = f"🟢 {mom_str}"

                ch_name = name_map.get(ticker, ticker)
                
                results.append({
                    "資產名稱": ch_name,
                    "趨勢 (月線)": trend_status,
                    "季動能 (3個月)": mom_str,
                    "現價": round(price, 2)
                })
        except:
            pass
    return pd.DataFrame(results)

# === 介面佈局 ===
# 上半部
c1, c2 = st.columns(2)
with c1:
    st.subheader("🔥 強勢動能選股")
    st.caption("金屬、能源、巴菲特指標")
    st.dataframe(get_data(assets["1. 🔥 強勢動能區"]), hide_index=True, use_container_width=True)

with c2:
    st.subheader("❄️ 弱勢動能避雷")
    st.caption("農產品、比特幣、反向指標")
    st.dataframe(get_data(assets["2. ❄️ 弱勢動能區"]), hide_index=True, use_container_width=True)

st.divider()

# 下半部
c3, c4 = st.columns(2)
with c3:
    st.subheader("🌏 核心市場監控")
    st.caption("美股、陸股、台股")
    st.dataframe(get_data(assets["3. 🌏 核心市場 (美/中/台)"]), hide_index=True, use_container_width=True)

with c4:
    st.subheader("🏦 利率與債券")
    st.caption("殖利率與債市")
    st.dataframe(get_data(assets["4. 🏦 利率與債券"]), hide_index=True, use_container_width=True)

# === 走勢圖 ===
st.divider()
st.subheader("📈 資產趨勢檢視")
all_tickers = []
for k in assets: all_tickers += assets[k]
opts = [f"{name_map.get(t,t)} ({t})" for t in all_tickers]
sel = st.selectbox("選擇商品：", opts)

if sel:
    try:
        code = sel.split("(")[-1].replace(")", "")
        st.write(f"正在顯示 **{sel}** 過去半年的走勢...")
        df = yf.download(code, period="6mo", progress=False)
        st.line_chart(df['Close'])
    except: st.write("無法顯示圖表")