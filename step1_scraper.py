import cloudscraper # 【第 4 版 新增】
import pandas as pd
from io import StringIO
import datetime
import sqlite3
# import requests (第 4 版不再需要 requests)
# import time (第 4 版不再需要 time)

# --- 資料庫設定 (不變) ---
DB_FILE = "mops_news.db"
TABLE_NAME = "realtime_news"

def fetch_mops_realtime_news():
    """
    抓取公開資訊觀測站的「本日即時重大訊息」。
    (版本 4：使用 'cloudscraper' 嘗試繞過 10054 錯誤)
    """
    print("...[系統] 正在連線至公開資訊觀測站 (使用 v4 終極偽裝模式)...")

    url = "https://mops.twse.com.tw/mops/web/ajax_t05sr01_1"
    today = datetime.date.today()
    
    form_data = {
        "encodeURIComponent": "1",
        "step": "1",
        "firstin": "1",
        "off": "1",
        "TYPEK": "all",
        "year": str(today.year - 1911),
        "month": str(today.month).zfill(2),
        "day": str(today.day).zfill(2),
    }

    # 【第 4 版 更新】 cloudscraper 不需要我們手動給這麼多標頭
    # 它會自己產生最適合的標頭
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
        "Referer": "https://mops.twse.com.tw/mops/web/t05sr01_1",
        "Origin": "https://mops.twse.com.tw",
        "Host": "mops.twse.com.tw",
    }

    try:
        # --- 【第 4 版 更新：使用 cloudscraper 建立連線】 ---
        # 它會自動處理 cookies 和複雜的標頭
        session = cloudscraper.create_scraper() 
        
        # --- 【第 4 版 更新：使用 session.post】 ---
        response = session.post(url, data=form_data, headers=headers)
        response.raise_for_status()

        if '查無資料' in response.text:
            print("...[系統] 查無本日重大訊息。 (MOPS 網站顯示 '查無資料')")
            return None
        
        try:
            dfs = pd.read_html(StringIO(response.text))
        except ValueError as e:
            if 'No tables found' in str(e):
                print("...[系統] 查無本日重大訊息。(Pandas 找不到可解析的表格)")
                return None
            else:
                raise e

        # ... (以下資料清理的部分完全不變) ...
        
        if not dfs:
            print("...[系統] 找不到任何表格資料。")
            return None

        df = dfs[0]

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(-1)
        
        if df.shape[1] > 1:
            df = df.iloc[:, :-1]

        useful_cols = ['公司代號', '公司名稱', '發言日期', '發言時間', '主旨']
        cols_to_keep = [col for col in useful_cols if col in df.columns]

        if not cols_to_keep:
            print(f"...[系統] 回傳的表格欄位不符預期: {df.columns}")
            return None

        df = df[cols_to_keep]

        print(f"...[系統] 成功抓取 {len(df)} 筆「本日」重大訊息。")
        return df

    # 【第 4 版 更新】 我們要捕捉的錯誤類型可能不同
    except requests.exceptions.RequestException as e:
        print(f"...[系統] 連線錯誤: {e}") 
        return None
    except Exception as e:
        print(f"...[系統] 發生未預期的錯誤: {e}")
        if 'response' in locals():
             print("原始回傳內容 (前500字元):", response.text[:500])
        return None

# --- 資料庫函式 (init_db, save_news_to_db, read_all_data_from_db) ---
# --- (這 3 個函式完全不變，所以直接複製貼上即可) ---
def init_db(db_file, table_name):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        "公司代號" TEXT,
        "公司名稱" TEXT,
        "發言日期" TEXT,
        "發言時間" TEXT,
        "主旨" TEXT,
        UNIQUE("公司代號", "發言日期", "發言時間", "主旨")
    );
    """
    cursor.execute(create_table_sql)
    conn.commit()
    conn.close()
    print(f"...[資料庫] 已確認資料庫 '{db_file}' 與資料表 '{table_name}' 準備就緒。")

def save_news_to_db(df, db_file, table_name):
    if df is None or df.empty:
        print("...[資料庫] 沒有新資料需要儲存。")
        return

    conn = sqlite3.connect(db_file)
    try:
        df.to_sql(table_name, conn, if_exists='append', index=False)
        print(f"...[資料庫] 成功將 {len(df)} 筆資料寫入資料庫。")
    except sqlite3.IntegrityError:
        print("...[資料庫] 偵測到重複資料，已自動忽略。")
    finally:
        conn.close()

def read_all_data_from_db(db_file, table_name):
    print(f"...[資料庫] 正在讀取 '{db_file}' 中的所有歷史資料...")
    conn = sqlite3.connect(db_file)
    try:
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
        print(f"...[資料庫] 成功讀取 {len(df)} 筆「歷史」公告。")
        return df
    except pd.errors.DatabaseError:
        print(f"...[資料庫] 尚無歷史資料。")
        return pd.DataFrame()
    finally:
        conn.close()

# --- 主要執行區 (完全不變) ---
if __name__ == "__main__":
    
    init_db(DB_FILE, TABLE_NAME)
    
    today_news_df = fetch_mops_realtime_news()
    
    save_news_to_db(today_news_df, DB_FILE, TABLE_NAME)
    
    print("\n--- 執行 PTT 作者策略 ---")
    
    all_historical_df = read_all_data_from_db(DB_FILE, TABLE_NAME)

    if all_historical_df is not None and not all_historical_df.empty:
        
        print("\n--- 篩選『所有歷史』募資相關公告 ---")
        
        keywords = ['現金增資', '公司債', '可轉換公司債', '購置', '擴廠', '不動產']
        
        mask = all_historical_df['主旨'].str.contains('|'.join(keywords), na=False)
        
        filtered_df = all_historical_df[mask]
        
        if not filtered_df.empty:
            print(f"在 {len(all_historical_df)} 筆「總歷史資料」中，找到 {len(filtered_df)} 筆相關公告：")
            print(filtered_df.sort_values(by="發言日期"))
        else:
            print(f"在 {len(all_historical_df)} 筆「總歷史資料」中，尚無相關的募資公告。")
    else:
        print("\n資料庫中尚無任何歷史重大訊息。")