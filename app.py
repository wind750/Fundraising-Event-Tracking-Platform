import streamlit as st
import cloudscraper
import pandas as pd
from io import StringIO
import datetime
import sqlite3
import time

# --- 資料庫設定 (不變) ---
DB_FILE = "mops_news.db"
TABLE_NAME = "realtime_news"

# --- PTT 作者策略的關鍵字 (不變) ---
KEYWORDS = ['現金增資', '公司債', '可轉換公司債', '購置', '擴廠', '不動產']

# --- 以下 4 個後端函式 (init_db, fetch..., save..., read...) ---
# --- (和 V5 腳本完全相同，故折疊) ---
def init_db(db_file, table_name):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        "公司代號" TEXT, "公司名稱" TEXT, "發言日期" TEXT,
        "發言時間" TEXT, "主旨" TEXT,
        UNIQUE("公司代號", "發言日期", "發言時間", "主旨")
    );
    """
    cursor.execute(create_table_sql)
    conn.commit()
    conn.close()

def fetch_mops_realtime_news():
    url = "https://mops.twse.com.tw/mops/web/ajax_t05sr01_1"
    today = datetime.date.today()
    form_data = {
        "encodeURIComponent": "1", "step": "1", "firstin": "1", "off": "1",
        "TYPEK": "all", "year": str(today.year - 1911),
        "month": str(today.month).zfill(2), "day": str(today.day).zfill(2),
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
        "Referer": "https://mops.twse.com.tw/mops/web/t05sr01_1",
        "Origin": "https://mops.twse.com.tw", "Host": "mops.twse.com.tw",
    }
    try:
        session = cloudscraper.create_scraper()
        response = session.post(url, data=form_data, headers=headers)
        response.raise_for_status()
        if '查無資料' in response.text: return None
        try:
            dfs = pd.read_html(StringIO(response.text))
        except ValueError as e:
            if 'No tables found' in str(e): return None
            else: raise e
        if not dfs: return None
        df = dfs[0]
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(-1)
        if df.shape[1] > 1:
            df = df.iloc[:, :-1]
        useful_cols = ['公司代號', '公司名稱', '發言日期', '發言時間', '主旨']
        cols_to_keep = [col for col in useful_cols if col in df.columns]
        if not cols_to_keep: return None
        df = df[cols_to_keep]
        return df
    except Exception as e:
        return None

def save_news_to_db(df, db_file, table_name):
    if df is None or df.empty:
        return 0
    conn = sqlite3.connect(db_file)
    try:
        df.to_sql(table_name, conn, if_exists='append', index=False)
        return len(df)
    except sqlite3.IntegrityError:
        return -1
    finally:
        conn.close()

def read_all_data_from_db(db_file, table_name):
    conn = sqlite3.connect(db_file)
    try:
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
        return df
    except pd.errors.DatabaseError:
        return pd.DataFrame()
    finally:
        conn.close()


# --- 【Streamlit 網頁介面主體】 ---

st.set_page_config(page_title="募資事件追蹤平台", layout="wide")

st.title("📈 募資事件追蹤平台")
st.caption("一個自動追蹤公開資訊觀測站「募資」相關公告的工具。")

st.divider()

# --- 1. 按鈕 (不變) ---
st.header("1. 更新資料庫")
# (此區塊不變)
if st.button("🚀 立即更新今日公告", type="primary", help="點我執行爬蟲"):
    with st.status("正在執行更新...", expanded=True) as status:
        st.write("...[資料庫] 正在確認資料庫結構...")
        init_db(DB_FILE, TABLE_NAME)
        st.write("...[系統] 正在連線至公開資訊觀測站 (使用 v4 偽裝模式)...")
        today_news_df = fetch_mops_realtime_news()
        if today_news_df is None:
            st.warning("...[系統] 查無本日重大訊息，或連線失敗。")
        else:
            st.success(f"...[系統] 成功抓取 {len(today_news_df)} 筆「本日」新公告。")
        st.write("...[資料庫] 正在儲存新資料...")
        save_count = save_news_to_db(today_news_df, DB_FILE, TABLE_NAME)
        if save_count > 0:
            st.success(f"...[資料庫] 成功將 {save_count} 筆新資料寫入資料庫。")
        elif save_count == -1:
            st.info("...[資料庫] 偵測到重複資料，已自動忽略。")
        else:
            st.info("...[資料庫] 沒有新資料需要儲存。")
        status.update(label="更新完成！", state="complete")
    st.success("資料庫更新完畢！下方表格已自動刷新。")

st.divider()

# --- 2. 顯示結果 (不變) ---
st.header("2. 歷史『募資相關』公告")
# (此區塊不變)
all_historical_df = read_all_data_from_db(DB_FILE, TABLE_NAME)
if all_historical_df is not None and not all_historical_df.empty:
    st.info(f"目前資料庫中共有 {len(all_historical_df)} 筆歷史公告。")
    mask = all_historical_df['主旨'].str.contains('|'.join(KEYWORDS), na=False)
    filtered_df = all_historical_df[mask]
    if not filtered_df.empty:
        st.write(f"在所有歷史資料中，共找到 {len(filtered_df)} 筆相關公告：")
        display_df = filtered_df.sort_values(by="發言日期", ascending=False)
        cols_to_display = ['發言日期', '公司代號', '公司名稱', '主旨']
        final_cols = [col for col in cols_to_display if col in display_df.columns]
        st.dataframe(display_df[final_cols], use_container_width=True, hide_index=True)
    else:
        st.warning(f"在 {len(all_historical_df)} 筆歷史資料中，尚無相關的募資公告。")
else:
    st.warning("資料庫 (`mops_news.db`) 中尚無任何歷史重大訊息。請點擊上方按鈕開始抓取。")

st.divider()

# --- 【第 6 版 更新功能】 ---
st.header("3. PTT 作者分析工具 (手動)")
st.markdown("請參考上方「歷史公告」表格中的數字，手動輸入下方欄位進行估算。")

col1, col2 = st.columns(2)

with col1:
    st.subheader("A. 簡易財務缺口計算機")
    st.markdown("`(同 PTT 作者: 30 億 - 15 億 = 缺 15 億)`")
    
    # (此區塊不變)
    target_amount = st.number_input("1. 募資目標（或購買資產金額）（億）", min_value=0.0, step=0.1, format="%.1f")
    current_cash = st.number_input("2. 最新財報現金（億）", min_value=0.0, step=0.1, format="%.1f")
    
    if st.button("計算資金缺口", key="calc_gap"):
        gap = target_amount - current_cash
        st.metric(label="預估資金缺口 (億)", value=f"{gap:.1f} 億")
        if gap <= 0:
            st.success("公司現金充足，沒有立即的資金缺口。")
        else:
            st.warning(f"公司尚有 {gap:.1f} 億的資金缺口！")

with col2:
    st.subheader("B. 募資股數定價推估")
    # --- 【第 6 版 更新】 ---
    st.markdown("`(同 PTT 作者: 16.4 億 / 12000 張 = 136.67 元/股)`")
    
    # --- 【第 6 版 更新】 讓使用者輸入「億」---
    gap_amount_yi = st.number_input("1. 預估資金缺口 (億)", min_value=0.0, step=0.1, format="%.1f", help="範例：請輸入 16.4")
    
    # --- (此欄位不變) ---
    shares_zhang = st.number_input("2. 預計發行張數 (張)", min_value=0, step=1000, format="%d", help="範例：12000 張")
    
    if st.button("計算預估定價", key="calc_price"):
        if shares_zhang > 0 and gap_amount_yi > 0:
            
            # --- 【第 6 版 更新】 自動換算 ---
            gap_amount_yuan = gap_amount_yi * 100_000_000 # 1 億 = 100,000,000
            shares_gu = shares_zhang * 1000 # 1 張 = 1000 股
            
            estimated_price = gap_amount_yuan / shares_gu
            st.metric(label="推估每股定價 (元)", value=f"{estimated_price:.2f} 元")
            st.markdown(f"**推估邏輯**：公司需籌 {gap_amount_yi} 億元，\n\n發行 {shares_zhang:,} 張（= {shares_gu:,} 股）。\n\n因此每股定價需為 {estimated_price:.2f} 元。")
        else:
            st.error("「資金缺口」和「發行張數」都必須大於 0")