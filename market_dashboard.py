import streamlit as st
import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime, timedelta
import numpy as np
import requests
import json
import zipfile
import io
import re
from deep_translator import GoogleTranslator
import altair as alt

# ==========================================
# 1. 系統設定
# ==========================================
st.set_page_config(page_title="全球金融戰情室 (AI週線旗艦版)", layout="wide")
st.title("🌐 全球金融戰情室 (AI週線旗艦版)")

tw_tz = pytz.timezone('Asia/Taipei')
current_time = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
st.caption(f"🕒 最後更新時間 (台灣): {current_time} | 📡 每週戰略決策模式已啟動")

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
        5. **極端背離**：監控 RSI 超買、廣度失衡與機構滿倉風險。
        """)
    with c2:
        st.markdown("""
        ### 🛡️ 交易心法:
        * **避開擁擠**：Z-Score > +1.5 時需分批獲利。
        * **流動性警報**：當日圓匯率跌破季線，代表平倉潮隨時啟動。
        * **黑天鵝防禦**：當 Tab 7 出現 3 項以上極端數值，應啟動尾部風險避險。
        * **歷史週期**：利用 Tab 8 與 Tab 9 掌握大選週期與地緣政治百年大循環，提前部署避險資產。
        """)

# ==========================================
# 2. 數據下載 ENGINE
# ==========================================
@st.cache_data(ttl=3600)
def fetch_raw_data(tickers):
    data = yf.download(tickers, period="5y", progress=False)
    if 'Close' in data.columns:
        return data['Close']
    return data

@st.cache_data(ttl=86400)
def fetch_long_term_index(ticker):
    """專為 Tab 8 設計的長期歷史大數據下載引擎"""
    data = yf.download(ticker, period="max", progress=False)
    if 'Close' in data.columns:
        series = data['Close']
        if isinstance(series, pd.DataFrame):
            return series.squeeze()
        return series
    return pd.Series()

SHILLER_XLS_FALLBACK_URL = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"

def _parse_shiller_xls(content_bytes):
    """解析 Shiller ie_data.xls（sheet='Data'，前 8 列為標題/說明）。
    Date 欄格式為 YYYY.MM（如 1871.1 代表 1871年10月），以字串格式化避免浮點誤差（1871.1 - 1871 != 0.1）誤判月份。
    CAPE 欄為第 13 欄（index=12）。並建構「標普總報酬指數」TR：
        TR_t = TR_{t-1} * (P_t + D_t/12) / P_{t-1}
    （Shiller 慣例：D 為年化股利率的月配版，每月依比例攤提再投入）。
    """
    raw = pd.read_excel(io.BytesIO(content_bytes), sheet_name="Data", header=None, skiprows=8, engine="xlrd")
    if raw.shape[1] < 13:
        return pd.DataFrame()

    df = raw.iloc[:, [0, 1, 2, 4, 12]].copy()
    df.columns = ["DateRaw", "P", "D", "CPI", "CAPE"]
    df = df[pd.to_numeric(df["DateRaw"], errors="coerce").notna()].copy()
    df["DateRaw"] = df["DateRaw"].astype(float)

    def _parse_ym(v):
        s = f"{v:.2f}"          # 1871.1 -> "1871.10"，避免浮點誤差
        y_s, m_s = s.split(".")
        return int(y_s), int(m_s)

    parsed = df["DateRaw"].apply(_parse_ym)
    df["Year"] = parsed.apply(lambda t: t[0])
    df["Month"] = parsed.apply(lambda t: t[1])
    df["Date"] = pd.to_datetime(dict(year=df["Year"], month=df["Month"], day=1))
    df = df.set_index("Date").drop(columns=["DateRaw", "Year", "Month"])
    for c in ["P", "D", "CPI", "CAPE"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_index()

    gross = (df["P"] + df["D"].fillna(0.0) / 12.0) / df["P"].shift(1)
    gross = gross.fillna(1.0)
    df["TR"] = 100.0 * gross.cumprod()
    return df

@st.cache_data(ttl=86400)
def fetch_shiller_data():
    """下載並解析 Robert Shiller（耶魯）長期股市資料庫，月頻，1871年起。
    來源優先順序：
      1. 動態解析 https://shillerdata.com/ 首頁中目前的 ie_data.xls 下載連結
         （Squarespace 代管，連結雜湊會不定期更動，故用正規表示式即時擷取而非寫死路徑；
          實測 2026-07 可正常取得，資料延伸至最新月份）。
      2. 退回舊版穩定網址 http://www.econ.yale.edu/~shiller/data/ie_data.xls
         （實測 2026-07 仍可下載，但曾觀察到資料停留在較舊月份，視耶魯站台當時是否同步而定）。
    欄位：P（名目股價）、D（股利，年化月配版）、CPI、CAPE（席勒本益比）、TR（自建標普總報酬指數）。
    失敗時回傳空 DataFrame，由呼叫端顯示友善提示並優雅降級。
    """
    candidate_urls = []
    try:
        home = requests.get("https://shillerdata.com/", timeout=15)
        m = re.search(r'"(//img1\.wsimg\.com/[^"]*?ie_data\.xls[^"]*)"', home.text)
        if m:
            candidate_urls.append("https:" + m.group(1))
    except Exception:
        pass
    candidate_urls.append(SHILLER_XLS_FALLBACK_URL)

    for url in candidate_urls:
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            df = _parse_shiller_xls(resp.content)
            if not df.empty:
                return df
        except Exception:
            continue
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def fetch_naaim_official_csv():
    try:
        url = "https://www.naaim.org/wp-content/uploads/naaim_data.csv"
        df = pd.read_csv(url, timeout=10)
        if not df.empty and 'NAAIM Number' in df.columns:
            latest_val = df['NAAIM Number'].iloc[-1]
            return float(latest_val)
        return None
    except:
        return None

# ==========================================
# 2.5 Ken French 49 Industry Portfolios (供「🏭 週期×產業」分頁使用)
# ==========================================
FRENCH_49_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/49_Industry_Portfolios_CSV.zip"

INDUSTRY_NAME_MAP_49 = {
    "Agric": "農業", "Food": "食品", "Soda": "糖果與汽水", "Beer": "啤酒與烈酒",
    "Smoke": "菸草", "Toys": "休閒娛樂用品", "Fun": "娛樂服務", "Books": "出版印刷",
    "Hshld": "家用消費品", "Clths": "服飾", "Hlth": "醫療保健服務", "MedEq": "醫療器材",
    "Drugs": "製藥", "Chems": "化學", "Rubbr": "橡膠與塑膠製品", "Txtls": "紡織",
    "BldMt": "建築材料", "Cnstr": "營建工程", "Steel": "鋼鐵", "FabPr": "金屬加工製品",
    "Mach": "機械", "ElcEq": "電機設備", "Autos": "汽車與卡車", "Aero": "飛機航太",
    "Ships": "造船與鐵路設備", "Guns": "國防軍工", "Gold": "貴金屬（黃金礦業）", "Mines": "金屬礦業",
    "Coal": "煤炭", "Oil": "石油天然氣", "Util": "公用事業", "Telcm": "電信通訊",
    "PerSv": "個人服務", "BusSv": "商業服務", "Hardw": "電腦硬體", "Softw": "軟體",
    "Chips": "半導體與電子設備", "LabEq": "精密儀器設備", "Paper": "商業用紙製品", "Boxes": "包裝容器",
    "Trans": "運輸物流", "Whlsl": "批發", "Rtail": "零售", "Meals": "餐飲旅宿",
    "Banks": "銀行", "Insur": "保險", "RlEst": "不動產", "Fin": "金融交易服務",
    "Other": "其他未分類",
}

@st.cache_data(ttl=86400)
def fetch_french_49_industries():
    """下載並解析 Ken French Data Library「49 Industry Portfolios」Value-Weighted 月報酬（%）。
    Zip 內單一 CSV 含多個區段（Value-Weighted / Equal-Weighted / 年報酬...），僅取第一段 Value-Weighted 月報酬。
    失敗時回傳空 DataFrame，由呼叫端顯示友善提示。"""
    try:
        resp = requests.get(FRENCH_49_URL, timeout=30)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(('.csv', '.txt'))] or zf.namelist()
            raw_text = zf.read(names[0]).decode('utf-8', errors='ignore')

        lines = raw_text.splitlines()
        start_idx = next((i for i, l in enumerate(lines) if 'Average Value Weighted Returns' in l), None)
        if start_idx is None:
            return pd.DataFrame()

        # 標題後的下一個非空白行即為欄位標頭
        j = start_idx + 1
        while j < len(lines) and lines[j].strip() == '':
            j += 1
        header_line = lines[j]

        # 資料列以 YYYYMM (6碼數字) 開頭；遇到空白行（且已收集到資料）代表本區段結束
        data_lines = []
        k = j + 1
        while k < len(lines):
            l = lines[k]
            token = l.split(',', 1)[0].strip()
            if len(token) == 6 and token.isdigit():
                data_lines.append(l)
                k += 1
            elif l.strip() == '':
                if data_lines:
                    break
                k += 1
            else:
                break

        csv_text = header_line + "\n" + "\n".join(data_lines)
        df = pd.read_csv(io.StringIO(csv_text))
        df.columns = [str(c).strip() for c in df.columns]
        df = df.rename(columns={df.columns[0]: 'YYYYMM'})
        df['YYYYMM'] = df['YYYYMM'].astype(int)
        df = df.set_index('YYYYMM')
        df = df.apply(pd.to_numeric, errors='coerce')
        df = df.replace([-99.99, -999, -999.0], np.nan)
        return df
    except Exception:
        return pd.DataFrame()

# ==========================================
# 2.6 NBER 衰退指標 (FRED USREC，供「🗓️ 歷史週期」與「🏭 週期×產業」分頁共用)
# ==========================================
NBER_USREC_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=USREC"

@st.cache_data(ttl=86400)
def fetch_nber_recession_years():
    """下載 FRED USREC（NBER 衰退月頻 0/1 指標，1854年起），回傳「衰退年」集合。
    定義：該年度含 ≥2 個 NBER 衰退月（USREC=1）即為衰退年。
    （門檻取 2 而非 3 的原因：2020 COVID 衰退為史上最短、僅 2 個月，
    ≥3 會把 2020 排除，對使用者是明顯的可信度問題；2026-07-19 裁決。）
    失敗時回傳空集合，由呼叫端優雅降級（自動隱藏過濾選項），不影響其餘功能運作。"""
    try:
        resp = requests.get(NBER_USREC_URL, timeout=15)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = [str(c).strip() for c in df.columns]
        if df.shape[1] < 2:
            return set()
        date_col, val_col = df.columns[0], df.columns[1]
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df[val_col] = pd.to_numeric(df[val_col], errors='coerce')
        df = df.dropna(subset=[date_col, val_col])
        if df.empty:
            return set()
        df['year'] = df[date_col].dt.year
        recession_month_counts = df[df[val_col] >= 1].groupby('year').size()
        return set(recession_month_counts[recession_month_counts >= 2].index.astype(int))
    except Exception:
        return set()

name_map = {
    "NVDA": "輝達", "AAPL": "蘋果", "MSFT": "微軟", "GOOGL": "Google", "AMZN": "亞馬遜", 
    "META": "Meta", "TSLA": "特斯拉", "AVGO": "博通", "SPY": "標普 500", "QQQ": "納指 ETF",
    "SOXX": "費半 ETF", "2330.TW": "台積電", "2454.TW": "聯發科", "00733.TW": "富邦中小",
    "0050.TW": "台灣50", "DX-Y.NYB": "美元指數", "^TNX": "美債10年", "^TYX": "美債30年", "JPY=X": "美元/日圓", "ZQ=F": "利率期貨",
    "^VIX": "VIX 恐慌", "BTC-USD": "比特幣", "GC=F": "黃金", "HG=F": "期貨銅", "CL=F": "原油",
    "^IXIC": "納斯達克", "SMH": "半導體ETF", "^SOX": "費半指數", "^TWII": "台灣加權", "^TWO": "櫃買指數",
    "ITA": "美國軍工ETF", "GLD": "黃金ETF", "TLT": "20年美債ETF", "DIA": "道瓊工業"
}

high_price_list = [
    "5274.TWO", "3008.TW", "3661.TW", "3529.TWO", "6669.TW", "5269.TWO", "3443.TW", "2454.TW", 
    "2059.TW", "3533.TW", "3131.TWO", "3653.TW", "3293.TWO", "6409.TW", "8454.TW", "6643.TW", 
    "6415.TW", "8299.TWO", "8464.TW", "1590.TW", "2327.TW", "2330.TW", "3034.TW", "4966.TWO"
]

mag_7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "AVGO"]
all_tk = list(set(list(name_map.keys()) + high_price_list + ["SPY", "QQQ", "ZQ=F", "^SOX", "ITA", "GLD", "TLT", "DIA", "0050.TW"]))

raw_df = fetch_raw_data(all_tk)

sp500_hist_df = fetch_long_term_index("^GSPC")
nasdaq_hist_df = fetch_long_term_index("^IXIC")
shiller_df = fetch_shiller_data()
shiller_tr_series = shiller_df["TR"].dropna() if not shiller_df.empty else pd.Series(dtype=float)
shiller_cape_series = shiller_df["CAPE"] if not shiller_df.empty else pd.Series(dtype=float)

nber_recession_years = fetch_nber_recession_years()

ECON_FILTER_ALL = "全部年份"
ECON_FILTER_EX_RECESSION = "排除衰退年"
ECON_FILTER_ONLY_RECESSION = "僅衰退年"

def _apply_recession_filter(years_list, filter_choice):
    """依景氣環境過濾年份清單（NBER 衰退年）。與其他過濾（如 CAPE 估值）疊加時皆為集合交集，順序無關結果相同。"""
    if filter_choice == ECON_FILTER_EX_RECESSION:
        return [y for y in years_list if y not in nber_recession_years]
    elif filter_choice == ECON_FILTER_ONLY_RECESSION:
        return [y for y in years_list if y in nber_recession_years]
    return years_list

# ==========================================
# 3. 處理引擎 & 量化公式
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

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_sharpe(series, period=252):
    returns = series.pct_change().tail(period)
    if returns.std() == 0: return 0
    return (returns.mean() / returns.std()) * np.sqrt(period)

def calculate_hurst_exponent(time_series, max_lag=100):
    """(舊版常數指標：目前保留於底層，已由綜合波取代)"""
    try:
        if len(time_series) < max_lag * 2:
            return 0.5
        lags = range(2, max_lag)
        tau = []
        for lag in lags:
            diff = np.subtract(time_series[lag:].values, time_series[:-lag].values)
            std = np.std(diff)
            tau.append(std if std > 0 else 1e-8)
        reg = np.polyfit(np.log(lags), np.log(tau), 1)
        return reg[0]
    except Exception as e:
        return 0.5

# ==========================================
# 4. 介面分頁 (依大至小宏觀視野重組)
# ==========================================
t_cycle, t_ind, t_war, t_hurst, t1, t3, t5, t_crash, t2, t4, t_poly = st.tabs([
    "🗓️ 歷史週期", "🏭 週期×產業", "⚔️ 戰爭週期雷達", "📊 赫斯特循環", "💀 AI 資金", "🚀 風險雷達",
    "📈 主要市場", "🚨 極端背離雷達", "🇹🇼 台股戰略", "💎 半導體", "🔮 真金白銀"
])

# --- Tab 1: 🗓️ 歷史週期 (原 Tab 8) ---
with t_cycle:
    st.error("## 🗓️ 總統大選週期與月度歷史地圖")
    st.caption("由本地量化引擎自動分析 **標普 500**、**那斯達克** 與 **Shiller 長期總報酬（1871起）** 大數據庫，支援自訂觀測基準、時空、回溯區間與估值環境過濾。")
    st.divider()

    current_year = datetime.now(tw_tz).year
    SHILLER_BASIS_LABEL = "標普總報酬 Shiller (1871起, 含股利)"

    c_idx, c_year, c_lookback, c_month = st.columns([1, 1, 1, 1])

    with c_idx:
        index_dict = {
            "標普 500 (^GSPC)": sp500_hist_df,
            "那斯達克 (^IXIC)": nasdaq_hist_df,
            SHILLER_BASIS_LABEL: shiller_tr_series,
        }
        selected_idx_str = st.selectbox("1️⃣ 選擇觀測基準：", list(index_dict.keys()), index=0)
        active_hist_df = index_dict[selected_idx_str]
        is_shiller_basis = (selected_idx_str == SHILLER_BASIS_LABEL)

    with c_year:
        selected_cycle_year = st.selectbox("2️⃣ 選擇觀測年份：", [current_year, current_year + 1, current_year + 2], index=0)

    with c_lookback:
        if is_shiller_basis:
            lookback_options = {"30年": 30, "40年": 40, "50年": 50, "80年": 80, "全部 (最長至1871)": 200}
        else:
            lookback_options = {"30年": 30, "40年": 40, "50年": 50, "全部 (最長至1927)": 100}
        selected_lookback_str = st.selectbox(
            "3️⃣ 選擇歷史回溯區間：", list(lookback_options.keys()), index=2,
            key=f"cycle_lookback_sel_{is_shiller_basis}"
        )
        lookback_years = lookback_options[selected_lookback_str]

    with c_month:
        months_list = [f"{i}月" for i in range(1, 13)]
        default_month_index = datetime.now(tw_tz).month - 1
        selected_month_str = st.selectbox("4️⃣ 選擇深度分析月份：", months_list, index=default_month_index)
        selected_month_num = int(selected_month_str.replace("月", ""))

    VALUATION_ALL = "全部年份"
    VALUATION_LOW = "低估值年 (CAPE後1/3)"
    VALUATION_MID = "中等估值年 (CAPE中1/3)"
    VALUATION_HIGH = "高估值年 (CAPE前1/3)"

    c_valuation, c_econ = st.columns([1, 1])
    with c_valuation:
        selected_valuation = st.selectbox(
            "5️⃣ 估值環境過濾（CAPE三分位）：",
            [VALUATION_ALL, VALUATION_LOW, VALUATION_MID, VALUATION_HIGH],
            index=0
        )
    with c_econ:
        if nber_recession_years:
            selected_econ_filter = st.selectbox(
                "6️⃣ 景氣環境過濾（NBER 衰退年）：",
                [ECON_FILTER_ALL, ECON_FILTER_EX_RECESSION, ECON_FILTER_ONLY_RECESSION],
                index=0, key="cycle_econ_filter"
            )
        else:
            selected_econ_filter = ECON_FILTER_ALL
    st.caption("💡 CAPE 三分位以當前回溯樣本計算，屬描述性歷史地圖非交易訊號。")
    if nber_recession_years:
        st.caption("💡 衰退年＝該年 ≥2 個 NBER 衰退月（USREC，含 2020 COVID 短衰退）；描述性歷史地圖非交易訊號。")
    else:
        st.caption("⚠️ 衰退資料載入失敗，景氣環境過濾暫時無法套用。")

    cycle_index = (selected_cycle_year - 2025) % 4
    cycle_names = ["第一年 (選後/重新定調)", "第二年 (期中選舉/通常最震盪)", "第三年 (選前/通常最強勁)", "第四年 (大選/波動後迎慶祝)"]
    current_cycle_name = cycle_names[cycle_index]

    min_year_floor = 1871 if is_shiller_basis else 1927
    start_eval_year = max(min_year_floor, current_year - lookback_years)
    base_history_years = [y for y in range(start_eval_year, current_year) if (y - 2025) % 4 == cycle_index]
    base_history_years.sort(reverse=True)

    # --- 估值環境過濾：以每個對照年份「1月CAPE」在目前回溯樣本內的三分位歸類 ---
    if selected_valuation != VALUATION_ALL:
        if not shiller_cape_series.empty:
            cape_by_year = {}
            for y in base_history_years:
                jan_ts = pd.Timestamp(year=y, month=1, day=1)
                if jan_ts in shiller_cape_series.index and pd.notna(shiller_cape_series.loc[jan_ts]):
                    cape_by_year[y] = float(shiller_cape_series.loc[jan_ts])
            if len(cape_by_year) >= 3:
                vals = pd.Series(cape_by_year)
                q1, q2 = vals.quantile(1/3), vals.quantile(2/3)
                def _cape_tier(v):
                    if v <= q1:
                        return VALUATION_LOW
                    elif v <= q2:
                        return VALUATION_MID
                    else:
                        return VALUATION_HIGH
                tiers = vals.apply(_cape_tier)
                base_history_years = sorted([y for y in vals.index if tiers[y] == selected_valuation], reverse=True)
            else:
                base_history_years = []
                st.warning("⚠️ 目前回溯樣本內可分類 CAPE 的年份不足 3 年，無法計算三分位，過濾結果為空集合。")
        else:
            base_history_years = []
            st.warning("⚠️ Shiller CAPE 資料無法載入，估值過濾暫時無法套用。")

    # --- 景氣環境過濾：排除或僅保留 NBER 衰退年（與估值過濾疊加，皆為集合交集，順序無關結果相同） ---
    if selected_econ_filter != ECON_FILTER_ALL and nber_recession_years:
        base_history_years = _apply_recession_filter(base_history_years, selected_econ_filter)

    st.markdown(f"### 🧭 戰略時空定位：{selected_cycle_year} 年 | 週期屬性：{current_cycle_name}")
    _valuation_note = "" if selected_valuation == VALUATION_ALL else f"（並符合估值過濾「{selected_valuation}」）"
    _econ_note = "" if selected_econ_filter == ECON_FILTER_ALL else f"（並符合景氣過濾「{selected_econ_filter}」）"
    st.info(f"🔍 **本地量化引擎已啟動**：正在計算基準 **{selected_idx_str}** 在過去 **{selected_lookback_str}** 內，符合該週期{_valuation_note}{_econ_note}的歷史年份\n\n對照年份：**{', '.join(map(str, base_history_years))}**")

    if not active_hist_df.empty:
        active_monthly = active_hist_df.resample('ME').last() if pd.__version__ >= '2.2.0' else active_hist_df.resample('M').last()
        active_monthly_ret = active_monthly.pct_change() * 100
        
        matched_rets = active_monthly_ret[active_monthly_ret.index.year.isin(base_history_years)]
        if not matched_rets.empty:
            avg_rets_by_month = matched_rets.groupby(matched_rets.index.month).mean()
            
            rets_array = [avg_rets_by_month.get(m, 0.0) for m in range(1, 13)]
            months_labels = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"]
            
            seasonality_df = pd.DataFrame({
                "月份": pd.Categorical(months_labels, categories=months_labels, ordered=True),
                "歷史平均報酬率 (%)": rets_array
            })
            
            st.markdown(f"#### 📊 {selected_cycle_year} 年 (週期{cycle_index+1})：全年度 1-12 月歷史平均漲跌規律")
            
            bar_chart = alt.Chart(seasonality_df).mark_bar().encode(
                x=alt.X('月份', sort=months_labels, axis=alt.Axis(labelAngle=0)),
                y='歷史平均報酬率 (%)',
                color=alt.condition(
                    alt.datum['歷史平均報酬率 (%)'] > 0,
                    alt.value('#FF3333'),  
                    alt.value('#00C000')   
                ),
                tooltip=['月份', alt.Tooltip('歷史平均報酬率 (%)', format='.2f')]
            ).properties(height=350).configure_axis(
                labelFontSize=14, titleFontSize=16
            )
            st.altair_chart(bar_chart, use_container_width=True)
            st.divider()

        monthly_returns = []
        monthly_trends = pd.DataFrame()

        if is_shiller_basis:
            # Shiller 為月頻資料，無日內序列可疊加；本月統計改用月度總報酬（TR）報酬率
            month_rets_series = matched_rets[matched_rets.index.month == selected_month_num].dropna() if not matched_rets.empty else pd.Series(dtype=float)
            monthly_returns = month_rets_series.tolist()
        else:
            for hist_year in base_history_years:
                try:
                    month_daily = active_hist_df[(active_hist_df.index.year == hist_year) & (active_hist_df.index.month == selected_month_num)]
                    if len(month_daily) > 1:
                        first_price = float(month_daily.iloc[0])
                        last_price = float(month_daily.iloc[-1])
                        ret_percent = ((last_price - first_price) / first_price) * 100
                        monthly_returns.append(ret_percent)

                        normalized_trend = (month_daily / first_price) * 100
                        trend_df = pd.DataFrame({f"{hist_year}年": normalized_trend.values})
                        monthly_trends = pd.concat([monthly_trends, trend_df], axis=1)
                except Exception as e:
                    pass

        if monthly_returns:
            avg_return = np.mean(monthly_returns)
            win_count = sum(1 for r in monthly_returns if r > 0)
            win_rate = (win_count / len(monthly_returns)) * 100
            
            if avg_return > 0:
                ret_color = "inverse"
                status_text = "多頭強勢月"
            else:
                ret_color = "normal"
                status_text = "季節性回調月 (十字路口)"

            sample_n = len(monthly_returns)

            c_stat1, c_stat2, c_stat3, c_stat4 = st.columns(4)
            with c_stat1:
                st.metric(f"歷史 {selected_month_str} 平均報酬", f"{avg_return:.2f}%", delta=f"{avg_return:.2f}", delta_color=ret_color)
            with c_stat2:
                st.metric(f"歷史 {selected_month_str} 上漲勝率", f"{win_rate:.0f}%", delta="偏多" if win_rate >= 50 else "偏空", delta_color="inverse" if win_rate >= 50 else "normal")
            with c_stat3:
                st.metric("季節性慣性判定", status_text, delta="0", delta_color="off")
            with c_stat4:
                st.metric("樣本年數", f"{sample_n} 年")
            if sample_n < 5:
                st.caption(f"⚠️ 樣本僅 {sample_n} 年，統計結果不具穩健性，僅供參考。")

            st.markdown(f"#### 📈 歷史 {selected_month_str} 內部每日走勢疊加與基準預測線")
            if is_shiller_basis:
                st.info("ℹ️ Shiller 為月頻資料，逐日疊加僅支援 ^GSPC/^IXIC 基準。")
            elif not monthly_trends.empty:
                monthly_trends['平均基準線 (Avg Base)'] = monthly_trends.mean(axis=1)
                monthly_trends['交易日 (Day)'] = range(1, len(monthly_trends) + 1)
                
                chart_data = monthly_trends.melt(id_vars=['交易日 (Day)'], var_name='年份', value_name='標準化點位 (基準100)')
                
                lines = alt.Chart(chart_data).mark_line().encode(
                    x=alt.X('交易日 (Day):O', axis=alt.Axis(labelAngle=0)),
                    y=alt.Y('標準化點位 (基準100):Q', scale=alt.Scale(zero=False)),
                    color=alt.condition(
                        alt.datum.年份 == '平均基準線 (Avg Base)',
                        alt.value('#deff9a'), 
                        alt.Color('年份:N', legend=alt.Legend(title="歷史疊加")) 
                    ),
                    size=alt.condition(
                        alt.datum.年份 == '平均基準線 (Avg Base)',
                        alt.value(4), 
                        alt.value(1)  
                    ),
                    opacity=alt.condition(
                        alt.datum.年份 == '平均基準線 (Avg Base)',
                        alt.value(1.0), 
                        alt.value(0.4) 
                    ),
                    tooltip=['交易日 (Day)', '年份', alt.Tooltip('標準化點位 (基準100)', format='.2f')]
                ).properties(height=400)
                
                st.altair_chart(lines, use_container_width=True)
                st.caption(f"💡 圖表判讀：若當前市場 ({selected_cycle_year}年 {selected_month_str}) 的實際走勢強於黃綠色的「平均基準線」，代表『近期強勢資金』成功抵銷歷史魔咒；反之則需提防技術修正。")
        else:
            st.warning(f"在所選的歷史區間內，無足夠的 {selected_month_str} 數據樣本進行疊加計算。")
    else:
        st.warning(f"無法載入 {selected_idx_str} 歷史大數據庫，請確認網路連線。")

# --- Tab 1.5: 🏭 週期×產業 (Ken French 49 Industry Portfolios) ---
with t_ind:
    st.error("## 🏭 總統大選週期 × 產業輪動地圖")
    st.caption("資料源：Ken French Data Library「49 Industry Portfolios」美股產業月報酬（Value-Weighted，1926年7月起近百年樣本）。週期定位邏輯與「🗓️ 歷史週期」分頁完全一致。")
    st.divider()

    current_year_ind = datetime.now(tw_tz).year

    ci_year, ci_lookback, ci_mode, ci_month = st.columns([1, 1, 1, 1])

    with ci_year:
        selected_ind_year = st.selectbox("1️⃣ 選擇觀測年份：", [current_year_ind, current_year_ind + 1, current_year_ind + 2], index=0, key="ind_year")

    with ci_lookback:
        ind_lookback_options = {"30年": 30, "50年": 50, "全部 (最長至1926)": 999}
        selected_ind_lookback_str = st.selectbox("2️⃣ 選擇歷史回溯區間：", list(ind_lookback_options.keys()), index=2, key="ind_lookback")
        ind_lookback_years = ind_lookback_options[selected_ind_lookback_str]

    with ci_mode:
        ind_view_mode = st.selectbox("3️⃣ 檢視模式：", ["📅 全年模式", "🗓️ 單月模式"], index=0, key="ind_mode")

    with ci_month:
        if ind_view_mode == "🗓️ 單月模式":
            ind_months_list = [f"{i}月" for i in range(1, 13)]
            ind_default_month_index = datetime.now(tw_tz).month - 1
            selected_ind_month_str = st.selectbox("4️⃣ 選擇月份：", ind_months_list, index=ind_default_month_index, key="ind_month")
            selected_ind_month_num = int(selected_ind_month_str.replace("月", ""))
        else:
            st.markdown("4️⃣ 月份：")
            st.caption("（全年模式不需選擇月份）")
            selected_ind_month_num = None
            selected_ind_month_str = ""

    ci_econ, _ci_econ_spacer = st.columns([1, 3])
    with ci_econ:
        if nber_recession_years:
            selected_ind_econ_filter = st.selectbox(
                "5️⃣ 景氣環境過濾（NBER 衰退年）：",
                [ECON_FILTER_ALL, ECON_FILTER_EX_RECESSION, ECON_FILTER_ONLY_RECESSION],
                index=0, key="ind_econ_filter"
            )
        else:
            selected_ind_econ_filter = ECON_FILTER_ALL
    if nber_recession_years:
        st.caption("💡 衰退年＝該年 ≥2 個 NBER 衰退月（USREC，含 2020 COVID 短衰退）；描述性歷史地圖非交易訊號。")
    else:
        st.caption("⚠️ 衰退資料載入失敗，景氣環境過濾暫時無法套用。")

    # 週期定位邏輯：與「🗓️ 歷史週期」分頁（t_cycle）同一套公式，不可自創不同定義
    ind_cycle_index = (selected_ind_year - 2025) % 4
    ind_cycle_names = ["第一年 (選後/重新定調)", "第二年 (期中選舉/通常最震盪)", "第三年 (選前/通常最強勁)", "第四年 (大選/波動後迎慶祝)"]
    ind_current_cycle_name = ind_cycle_names[ind_cycle_index]

    ind_start_eval_year = max(1926, current_year_ind - ind_lookback_years)
    ind_base_history_years = [y for y in range(ind_start_eval_year, current_year_ind) if (y - 2025) % 4 == ind_cycle_index]
    ind_base_history_years.sort(reverse=True)

    # --- 景氣環境過濾：排除或僅保留 NBER 衰退年 ---
    if selected_ind_econ_filter != ECON_FILTER_ALL and nber_recession_years:
        ind_base_history_years = _apply_recession_filter(ind_base_history_years, selected_ind_econ_filter)

    st.markdown(f"### 🧭 戰略時空定位：{selected_ind_year} 年 | 週期屬性：{ind_current_cycle_name}")
    _ind_econ_note = "" if selected_ind_econ_filter == ECON_FILTER_ALL else f"（並符合景氣過濾「{selected_ind_econ_filter}」）"
    st.info(f"🔍 **本地量化引擎已啟動**：正在計算過去 **{selected_ind_lookback_str}** 內，符合該週期{_ind_econ_note}的歷史年份\n\n對照年份：**{', '.join(map(str, ind_base_history_years))}**")

    df_ind_raw = fetch_french_49_industries()

    if df_ind_raw.empty:
        st.warning("⚠️ 無法下載或解析 Ken French 49 Industry Portfolios 資料，請確認網路連線後重新整理頁面。")
    else:
        df_ind = df_ind_raw.copy()
        df_ind['year'] = df_ind.index // 100
        df_ind['month'] = df_ind.index % 100
        industry_cols = [c for c in df_ind.columns if c not in ('year', 'month')]

        n_years = len(ind_base_history_years)

        if n_years == 0:
            st.warning("所選區間內無符合週期的歷史對照年份。")
        else:
            if ind_view_mode == "📅 全年模式":
                annual_records = []
                for y in ind_base_history_years:
                    year_slice = df_ind[df_ind['year'] == y]
                    if len(year_slice) < 10:
                        continue
                    for col in industry_cols:
                        vals = year_slice[col].dropna()
                        if len(vals) < 10:
                            continue
                        compounded = (np.prod(1 + vals.values / 100.0) - 1) * 100
                        annual_records.append({"industry": col, "year": y, "annual_return": compounded})

                annual_df = pd.DataFrame(annual_records)
                if annual_df.empty:
                    st.warning("所選對照年份內，產業資料樣本不足。")
                else:
                    grp = annual_df.groupby("industry")["annual_return"]
                    summary = grp.mean().rename("平均報酬")
                    win_rates = (grp.apply(lambda s: (s > 0).mean() * 100)).rename("上漲勝率")
                    counts = grp.count().rename("樣本數")

                    result_df = pd.concat([summary, win_rates, counts], axis=1).reset_index()
                    result_df = result_df.rename(columns={"industry": "代碼"})
                    result_df["產業"] = result_df["代碼"].map(lambda c: f"{INDUSTRY_NAME_MAP_49.get(c, c)} ({c})")
                    result_df = result_df.sort_values("平均報酬", ascending=False)

                    top3 = result_df.head(3)
                    bottom3 = result_df.tail(3).iloc[::-1]

                    st.markdown(f"#### 🏆 {selected_ind_year} 年 (週期{ind_cycle_index+1})：最強／最弱三大產業（全年度平均報酬）")
                    mc1, mc2, mc3 = st.columns(3)
                    for col_m, (_, row) in zip([mc1, mc2, mc3], top3.iterrows()):
                        col_m.metric(f"🔴 {row['產業']}", f"{row['平均報酬']:.2f}%", f"勝率 {row['上漲勝率']:.0f}%", delta_color="off")
                    mc4, mc5, mc6 = st.columns(3)
                    for col_m, (_, row) in zip([mc4, mc5, mc6], bottom3.iterrows()):
                        col_m.metric(f"🟢 {row['產業']}", f"{row['平均報酬']:.2f}%", f"勝率 {row['上漲勝率']:.0f}%", delta_color="off")

                    st.markdown("#### 📊 49 產業歷史平均年度報酬排行")
                    bar = alt.Chart(result_df).mark_bar().encode(
                        y=alt.Y('產業:N', sort='-x', title=None),
                        x=alt.X('平均報酬:Q', title='歷史平均年度報酬 (%)'),
                        color=alt.condition(
                            alt.datum['平均報酬'] > 0,
                            alt.value('#FF3333'),
                            alt.value('#00C000')
                        ),
                        tooltip=[alt.Tooltip('產業:N'), alt.Tooltip('平均報酬:Q', format='.2f'), alt.Tooltip('上漲勝率:Q', format='.0f', title='上漲勝率(%)'), alt.Tooltip('樣本數:Q')]
                    ).properties(height=1000)
                    st.altair_chart(bar, use_container_width=True)
                    st.caption(f"📐 對照年份 {n_years} 年（樣本有限，僅供歷史先驗參考，非交易訊號）。")
            else:
                month_slice = df_ind[(df_ind['year'].isin(ind_base_history_years)) & (df_ind['month'] == selected_ind_month_num)]
                if month_slice.empty:
                    st.warning(f"所選對照年份內，無 {selected_ind_month_str} 的產業資料樣本。")
                else:
                    means = month_slice[industry_cols].mean().rename("平均報酬")
                    win_rates_m = ((month_slice[industry_cols] > 0).mean() * 100).rename("上漲勝率")
                    counts_m = month_slice[industry_cols].count().rename("樣本數")

                    result_df = pd.concat([means, win_rates_m, counts_m], axis=1).reset_index()
                    result_df = result_df.rename(columns={"index": "代碼"})
                    result_df["產業"] = result_df["代碼"].map(lambda c: f"{INDUSTRY_NAME_MAP_49.get(c, c)} ({c})")
                    result_df = result_df.sort_values("平均報酬", ascending=False)

                    top3 = result_df.head(3)
                    bottom3 = result_df.tail(3).iloc[::-1]

                    st.markdown(f"#### 🏆 {selected_ind_year} 年 {selected_ind_month_str} (週期{ind_cycle_index+1})：最強／最弱三大產業")
                    mc1, mc2, mc3 = st.columns(3)
                    for col_m, (_, row) in zip([mc1, mc2, mc3], top3.iterrows()):
                        col_m.metric(f"🔴 {row['產業']}", f"{row['平均報酬']:.2f}%", f"勝率 {row['上漲勝率']:.0f}%", delta_color="off")
                    mc4, mc5, mc6 = st.columns(3)
                    for col_m, (_, row) in zip([mc4, mc5, mc6], bottom3.iterrows()):
                        col_m.metric(f"🟢 {row['產業']}", f"{row['平均報酬']:.2f}%", f"勝率 {row['上漲勝率']:.0f}%", delta_color="off")

                    st.markdown(f"#### 📊 {selected_ind_month_str}：49 產業歷史平均月報酬排行")
                    bar = alt.Chart(result_df).mark_bar().encode(
                        y=alt.Y('產業:N', sort='-x', title=None),
                        x=alt.X('平均報酬:Q', title=f'{selected_ind_month_str}歷史平均報酬 (%)'),
                        color=alt.condition(
                            alt.datum['平均報酬'] > 0,
                            alt.value('#FF3333'),
                            alt.value('#00C000')
                        ),
                        tooltip=[alt.Tooltip('產業:N'), alt.Tooltip('平均報酬:Q', format='.2f'), alt.Tooltip('上漲勝率:Q', format='.0f', title='上漲勝率(%)'), alt.Tooltip('樣本數:Q')]
                    ).properties(height=1000)
                    st.altair_chart(bar, use_container_width=True)
                    st.caption(f"📐 對照年份 {n_years} 年（樣本有限，僅供歷史先驗參考，非交易訊號）。")

# --- Tab 2: ⚔️ 戰爭週期雷達 (原 Tab 9) ---
with t_war:
    st.error("## ⚔️ 三大戰爭週期共振雷達 (2027-2032)")
    st.caption("源自 Dewey、Mogey 與 Wheeler 百年量化學派。透過正弦波演算法追蹤太陽活動、地緣衝突與霸權重組的歷史共振節點。")
    st.divider()

    current_year_for_war = datetime.now(tw_tz).year
    selected_year = st.slider("時間觀測儀 (模擬年份推演)", min_value=2000, max_value=2050, value=current_year_for_war, step=1)
    
    years_array = np.arange(2000, 2051)
    
    dewey_wave = (np.sin(2 * np.pi * (years_array - 2026) / 16) + 1) * 50
    mogey_wave = (np.sin(2 * np.pi * (years_array - 2023.5) / 26) + 1) * 50
    long_wave = (np.sin(2 * np.pi * (years_array - 2014.25) / 63) + 1) * 50
    danger_index_array = (dewey_wave + mogey_wave + long_wave) / 3
    idx = np.where(years_array == selected_year)[0][0]
    current_danger = round(danger_index_array[idx], 1)

    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown("### 🌡️ 宏觀地緣風險指數")
        if 2027 <= selected_year <= 2032:
            alert_color = "inverse"
            alert_text = "💀 極端紅區：三大週期波峰交會"
        elif 2024 <= selected_year < 2027:
            alert_color = "off"
            alert_text = "⚠️ 醞釀期：危機正在升溫 (太陽極大期)"
        else:
            alert_color = "normal"
            alert_text = "🟢 衰退期：進入秩序重組"
            
        st.metric(label=f"{selected_year} 年共振強度 (0-100)", value=f"{current_danger}", delta=alert_text, delta_color=alert_color)
        
        st.markdown("---")
        st.markdown("#### 🔭 週期解析")
        st.write("**1. 16年 Dewey 週期：** 短期區域衝突爆發規律。")
        st.write("**2. 26年 Mogey 週期：** 國家級地緣政治板塊碰撞。")
        st.write("**3. 63年 長波週期：** 全球霸權與法幣系統的歷史更迭。")

    with c2:
        st.markdown("### 📈 百年戰爭週期共振矩陣圖")
        war_df = pd.DataFrame({
            "年份": years_array,
            "16年 Dewey": dewey_wave,
            "26年 Mogey": mogey_wave,
            "63年 長波": long_wave,
            "共振危險指數": danger_index_array
        })
        war_df_melted = war_df.melt(id_vars=["年份"], var_name="週期類型", value_name="能量強度")
        
        war_chart = alt.Chart(war_df_melted).mark_line(strokeWidth=2).encode(
            x=alt.X('年份:O', axis=alt.Axis(values=[2000, 2010, 2020, 2027, 2032, 2040, 2050], labelAngle=0)),
            y=alt.Y('能量強度:Q', scale=alt.Scale(domain=[0, 100])),
            color=alt.Color('週期類型:N', scale=alt.Scale(
                domain=['16年 Dewey', '26年 Mogey', '63年 長波', '共振危險指數'],
                range=['#5bc0de', '#f0ad4e', '#d9534f', '#ffffff']
            )),
            tooltip=['年份', '週期類型', alt.Tooltip('能量強度', format='.1f')]
        ).properties(height=350)
        
        rect_df = pd.DataFrame([{"start": 2027, "end": 2032}])
        danger_zone = alt.Chart(rect_df).mark_rect(color='red', opacity=0.15).encode(
            x='start:O', x2='end:O'
        )
        
        rule_df = pd.DataFrame([{"year": selected_year}])
        vline = alt.Chart(rule_df).mark_rule(color='#deff9a', strokeWidth=2, strokeDash=[5, 5]).encode(
            x='year:O'
        )
        
        st.altair_chart(war_chart + danger_zone + vline, use_container_width=True)

    st.divider()

    st.markdown("### 🛡️ 戰略避險矩陣 (Strategic Asset Shield)")
    st.caption("當時間軸進入 2027-2032 共振紅區時，傳統法幣與科技股將面臨估值重估，資金將流向以下實體硬資產與避險核心。")
    
    df_shield, _, _ = get_stats(["GC=F", "CL=F", "TLT", "ITA", "DX-Y.NYB"], raw_df)
    
    if not df_shield.empty:
        s1, s2, s3, s4 = st.columns(4)
        def draw_shield(col, ticker, name, purpose):
            r = df_shield[df_shield['代號']==ticker]
            if not r.empty: 
                col.metric(f"🪙 {name} ({purpose})", f"{r['現價'].values[0]}", f"{r['乖離率'].values[0]}%", delta_color="inverse")
        
        draw_shield(s1, "GC=F", "黃金期貨", "抗通膨與法幣貶值")
        draw_shield(s2, "CL=F", "原油期貨", "供應鏈地緣溢價")
        draw_shield(s3, "TLT", "20年美債", "終極無風險避風港")
        draw_shield(s4, "ITA", "美國軍工", "國防預算擴張受惠")
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.dataframe(df_shield[["資產名稱", "趨勢", "現價", "乖離率", "Z-Score"]], hide_index=True, use_container_width=True)
    else:
        st.warning("避險資產數據載入中...")

# --- Tab 3: 📊 赫斯特能量循環儀 (原 Tab 10) ---
with t_hurst:
    st.error("## 📊 赫斯特能量循環儀 (綜合重力波升級版)")
    st.caption("基於 J.M. Hurst 疊加原理 (Principle of Summation)。真實計算 40週、20週、80天 三大主導循環的動能，合成為「綜合循環能量波」，秒判大趨勢重力。")
    st.divider()

    # 對照字典
    hurst_tickers = ["0050.TW", "2330.TW", "QQQ", "SPY", "DIA"]
    asset_map_reverse = {name_map.get(t, t): t for t in hurst_tickers}
    
    # 1. 頂層互動選單
    selected_hurst_asset = st.selectbox("1️⃣ 選擇核心監控資產", list(asset_map_reverse.keys()), index=0)
    target_tk = asset_map_reverse[selected_hurst_asset]

    # --- 真實數據運算核心 ---
    target_series = raw_df[target_tk].dropna() if target_tk in raw_df.columns else pd.Series()
    
    if len(target_series) > 250:
        # === 計算綜合循環能量波 (Composite Cyclic Wave) ===
        # 利用平滑動量近似各週期的諧波相位，並轉為 Z-Score 進行等權重疊加
        roc_40w = target_series.pct_change(100).rolling(20).mean() # 40週 (約200天) -> 半週期 100 天
        roc_20w = target_series.pct_change(50).rolling(10).mean()  # 20週 (約100天) -> 半週期 50 天
        roc_80d = target_series.pct_change(20).rolling(5).mean()   # 80天 (約40天) -> 半週期 20 天
        
        z_40w = (roc_40w - roc_40w.rolling(504).mean()) / roc_40w.rolling(504).std()
        z_20w = (roc_20w - roc_20w.rolling(504).mean()) / roc_20w.rolling(504).std()
        z_80d = (roc_80d - roc_80d.rolling(504).mean()) / roc_80d.rolling(504).std()
        
        # 合成波 (Summation Wave)
        comp_wave = (z_40w + z_20w + z_80d) / 3
        comp_wave = comp_wave.dropna()
        
        if len(comp_wave) > 10:
            current_wave = comp_wave.iloc[-1]
            prev_wave = comp_wave.iloc[-5] # 對比5天前的斜率確認方向
            wave_slope = current_wave - prev_wave

            # 判定真實重力狀態
            if current_wave > 0 and wave_slope > 0:
                gravity_status = "🔴 向上強重力 (多頭共振)"
                strategy_text = "時間與價格雙多頭。若價格在 20MA 之上或突破 FLD，積極順勢作多。"
                gravity_color = "inverse"
            elif current_wave < 0 and wave_slope < 0:
                gravity_status = "🟢 向下強重力 (空頭共振)"
                strategy_text = "時間重力向下拖拽。跌破 20MA 是玩真的，空手觀望或防禦避險。"
                gravity_color = "normal"
            elif current_wave < 0 and wave_slope > 0:
                gravity_status = "🟡 谷底翻揚 (同步谷底醞釀)"
                strategy_text = "重力剛從底部反轉。密切尋找價格突破 FLD 或站上 20MA 的第一買點。"
                gravity_color = "off"
            else:
                gravity_status = "⚠️ 高檔拐頭 (波峰衰退)"
                strategy_text = "重力動能開始減弱。逢高分批獲利了結，切忌追高。"
                gravity_color = "off"

            c_info1, c_info2 = st.columns([1, 2])
            with c_info1:
                st.metric("當前綜合循環重力值", f"{current_wave:.2f}", delta=gravity_status, delta_color=gravity_color)
            with c_info2:
                st.info(f"**💡 戰情室操盤對策：** {strategy_text}")

            st.divider()

            # === 2. 上圖：真實 FLD 時空投影 ===
            st.markdown(f"### 🎯 空間維度：真實 FLD 疊加交戰圖")
            st.caption("當前價格由下往上『實質穿越』黃綠色的 40W FLD 線時，代表波段多頭空間確認展開。")
            
            clean_target = target_series.dropna()
            fld_40w = clean_target.shift(100)
            fld_20w = clean_target.shift(50)

            # 加入 dropna(how='all') 徹底解決資料對齊錯誤
            fld_df = pd.DataFrame({
                "真實收盤價": clean_target,
                "40週 FLD (平移100天)": fld_40w,
                "20週 FLD (平移50天)": fld_20w
            }).dropna(how='all').tail(500)

            plot_df = fld_df.reset_index().melt(id_vars='Date', var_name='Line', value_name='Price').dropna()

            fld_chart = alt.Chart(plot_df).mark_line().encode(
                x=alt.X('Date:T', axis=alt.Axis(title='')),
                y=alt.Y('Price:Q', scale=alt.Scale(zero=False)),
                color=alt.Color('Line:N', scale=alt.Scale(
                    domain=['真實收盤價', '40週 FLD (平移100天)', '20週 FLD (平移50天)'],
                    range=['#ffffff', '#deff9a', '#5bc0de']
                ), legend=alt.Legend(title="指標圖例", orient="top-left")),
                strokeWidth=alt.condition(
                    alt.datum.Line == '真實收盤價',
                    alt.value(2.5),
                    alt.value(1.5)
                ),
                tooltip=['Date:T', 'Line:N', alt.Tooltip('Price:Q', format='.2f')]
            ).properties(height=350)

            st.altair_chart(fld_chart, use_container_width=True)

            # === 3. 下圖：綜合循環能量波 ===
            st.markdown(f"### 🌊 時間維度：綜合循環能量波 (Composite Cyclic Wave)")
            st.caption("三大主導循環疊加合力。紅色區塊代表時間重力向上推升；綠色區塊代表時間重力向下拖拽。")
            
            wave_df = pd.DataFrame({
                "Date": comp_wave.index,
                "綜合重力波": comp_wave.values
            }).tail(500)

            base_line = alt.Chart(wave_df).mark_line(color='white', strokeWidth=2).encode(
                x=alt.X('Date:T', axis=alt.Axis(title='日期')),
                y=alt.Y('綜合重力波:Q'),
                tooltip=['Date:T', alt.Tooltip('綜合重力波:Q', format='.2f')]
            )

            bull_area = alt.Chart(wave_df).transform_filter(
                alt.datum['綜合重力波'] > 0
            ).mark_area(color='red', opacity=0.3).encode(
                x='Date:T',
                y='綜合重力波:Q',
                y2=alt.datum(0)
            )

            bear_area = alt.Chart(wave_df).transform_filter(
                alt.datum['綜合重力波'] < 0
            ).mark_area(color='green', opacity=0.3).encode(
                x='Date:T',
                y='綜合重力波:Q',
                y2=alt.datum(0)
            )

            wave_chart = (bull_area + bear_area + base_line).properties(height=250)
            st.altair_chart(wave_chart, use_container_width=True)

    else:
        st.warning(f"無法獲取足夠的 {selected_hurst_asset} 歷史數據以計算赫斯特循環模型。")

# --- Tab 4: 💀 AI 資金 (原 Tab 1) ---
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

# --- Tab 5: 🚀 風險雷達 (原 Tab 3) ---
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
        else: ct_label, ct_delta, ct_status_msg = "🛡️ 穩定套利 (Carry)", "normal", "💡 **正常：** 匯率平穩。"

        c1, c2, c3 = st.columns(3)
        with c1: st.metric("名目匯率 (JPY=X)", f"{round(p_jpy, 2)}", f"{'🔴 貶值趨勢' if p_jpy > ma60_jpy else '🟢 日圓轉強'}"); st.caption(f"適應基準: {adaptive_threshold}")
        with c2: st.metric("10日變動斜率", f"{round(slope_10, 2)}", "⚠️ 急速" if slope_10 > 0.5 else "✅ 平穩", delta_color="inverse" if slope_10 > 0.5 else "normal")
        with c3: st.metric("Carry Trade 壓力", f"{stress_score}%", ct_label, delta_color=ct_delta); st.progress(stress_score / 100)

    st.divider()
    df_rz, _, _ = get_stats(["^VIX", "BTC-USD", "GC=F", "HG=F", "CL=F", "DX-Y.NYB"], raw_df)
    st.dataframe(df_rz[["資產名稱", "Z-Score", "趨勢", "現價"]], hide_index=True, use_container_width=True)

# --- Tab 6: 📈 主要市場 (原 Tab 5) ---
with t5:
    st.subheader("📈 全球資產趨勢與動態基準")
    sel = st.selectbox("選擇商品：", all_tk, format_func=lambda x: f"{name_map.get(x,x)} ({x})", key="main_trend_selector")
    if sel:
        plot_data = raw_df[sel].ffill().dropna()
        if not plot_data.empty:
            chart_df = pd.DataFrame({"現價": plot_data})
            if sel == "JPY=X":
                ma60 = plot_data.rolling(60).mean()
                chart_df["動態適應基準 (DAT)"] = ma60 * 1.05
            st.line_chart(chart_df)

# --- Tab 7: 🚨 極端背離雷達 (原 Tab 7) ---
with t_crash:
    st.error("## 🚨 黑天鵝雷達：系統性反轉與流動性枯竭預警")
    st.caption("專為每週複盤設計的宏觀風險控制台。結合即時量化運算與機構籌碼面。")
    st.divider()

    naaim_auto_val = fetch_naaim_official_csv()

    st.subheader("🛠️ 每週核心籌碼數據校正（動態響應面板）")
    col_in1, col_in2, col_in3 = st.columns(3)
    
    with col_in1:
        default_naaim = naaim_auto_val if naaim_auto_val is not None else 110.0
        naaim_input = st.slider("1. NAAIM 機構經理人曝險 (%)", 0.0, 200.0, float(default_naaim), step=5.0)
        if naaim_auto_val is not None:
            st.success(f"✅ 自動同步 NAAIM 最新數據: {naaim_auto_val}%")
        else:
            st.caption("💡 提示：可手動拉動滑桿校正")
            
    with col_in2:
        gex_input = st.number_input("2. 當前 GEX 曝險 (十億, B)", value=21.5, step=1.0)
        st.caption("💡 提示：> +10B 安全區；< 0 多殺多區")
        
    with col_in3:
        breadth_select = st.selectbox("3. RAY (羅素3000) 內部廣度", ["嚴重背離 (指數高、個股破底)", "正常同步", "極度健康"])
        sma200_input = st.slider("4. S&P500 高於年線比例 (%)", 0.0, 100.0, 42.0, step=1.0)

    st.divider()

    sox_rsi_val = 0
    if '^SOX' in raw_df.columns:
        sox_data = raw_df['^SOX'].ffill().dropna()
        if not sox_data.empty:
            sox_rsi_val = round(calculate_rsi(sox_data).iloc[-1], 2)

    ndx_sharpe_val = 0
    if 'QQQ' in raw_df.columns:
        qqq_data = raw_df['QQQ'].ffill().dropna()
        if not qqq_data.empty:
            ndx_sharpe_val = round(calculate_sharpe(qqq_data), 2)

    _sox = float(sox_rsi_val) if sox_rsi_val is not None else 50.0
    _gex = float(gex_input) if gex_input is not None else 0.0
    _naaim = float(naaim_input) if naaim_input is not None else 50.0

    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.markdown("#### 📈 價格與波動極端值")
        st.metric("SOX (費半) RSI", f"{_sox:.1f}", delta=f"{_sox - 50:.1f}", delta_color="inverse")
        st.caption("警示: 極端超買" if _sox > 86 else "狀態: 正常")
        
        st.metric("NDX (納指) Sharpe", f"{ndx_sharpe_val:.2f}x", delta=f"{ndx_sharpe_val - 1.0:.2f}", delta_color="inverse")
        st.caption("警示: 極端高風險" if ndx_sharpe_val >= 1.6 else "狀態: 正常")

    with c2:
        st.markdown("#### 🏦 機構動能警報窗")
        st.metric("GEX (造市商曝險)", f"{_gex:.1f} B", delta=f"{_gex:.1f}", delta_color="inverse")
        st.caption("狀態: " + ("崩盤引信啟動" if _gex < 0 else ("安全區" if _gex > 10 else "屏障消失區")))
        
        st.metric("NAAIM 經理人曝險", f"{_naaim:.0f}%", delta=f"{_naaim - 60:.0f}", delta_color="inverse")
        st.caption("狀態: " + ("買盤枯竭 (滿倉)" if _naaim >= 110 else ("子彈充足" if _naaim < 60 else "穩定運行")))

    with c3:
        st.markdown("#### 📉 結構與廣度失衡")
        st.metric("RAY 廣度健康度", "數據就緒", delta="0", delta_color="inverse")
        st.caption("狀態: 結構惡化" if "嚴重背離" in breadth_select else "狀態: 結構穩健")
        
        st.metric("成份股高於年線比例", f"{sma200_input:.0f}%", delta=f"{sma200_input - 50:.0f}", delta_color="inverse")
        st.caption("狀態: " + ("掏空風險 (巨頭撐盤)" if sma200_input < 50 else "健康普漲"))

    st.divider()
    st.markdown("### 📝 本週大局觀：量化防禦筆記")
    
    danger_count = 0
    if _sox > 86: danger_count += 1
    if ndx_sharpe_val >= 1.6: danger_count += 1
    if _gex < 0: danger_count += 1
    if _naaim >= 110: danger_count += 1
    if "嚴重背離" in breadth_select: danger_count += 1
    if sma200_input < 50: danger_count += 1
    
    if danger_count >= 4:
        st.error(f"🚨 **紅色警戒：當前 6 大指標中有 {danger_count} 項陷入極端背離！** 市場流動性極度擁擠、且內部結構嚴重掏空。強烈建議提高現金水位，或買入防禦型 VIX 避險。")
    elif danger_count >= 2:
        st.warning(f"⚠️ **中度戒備：當前有 {danger_count} 項指標異常。** 市場多頭動能主要由少數大型股維繫。暫不開新多單，靜待市場廣度回溫。")
    else:
        st.info(f"✅ **宏觀環境安全：當前異常指標僅 {danger_count} 項。** 機構子彈正常，大盤拉回皆為健康修正，可繼續執行多頭台股選股策略。")

# --- Tab 8: 🇹🇼 台股戰略 (原 Tab 2) ---
with t2:
    df_tw_l, _, _ = get_stats(["SOXX", "00733.TW", "DX-Y.NYB", "^TNX", "^TYX"], raw_df)
    m1, m2, m3, m4, m5 = st.columns(5)
    
    def draw_m(col, ticker, name):
        r = df_tw_l[df_tw_l['代號']==ticker]
        if not r.empty: 
            col.metric(name, f"{r['現價'].values[0]}", f"{r['乖離率'].values[0]}%", delta_color="inverse")
            
    draw_m(m1, "SOXX", "費半 ETF")
    draw_m(m2, "00733.TW", "富邦中小")
    draw_m(m3, "DX-Y.NYB", "美元指數")
    draw_m(m4, "^TNX", "美債10Y")
    draw_m(m5, "^TYX", "美債30Y")
    
    st.divider()
    df_king, df_filt, _ = get_stats(high_price_list, raw_df, threshold=800)
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("當前監控檔數", f"{len(df_king)} 檔")
    s2.metric("強勢佔比", f"{int(len(df_king[df_king['乖離率']>0])/len(df_king)*100)}%" if not df_king.empty else "0%")
    s3.metric("低於門檻 (濾除)", f"{len(df_filt)} 檔")
    s4.metric("族群平均 Z-Score", round(df_king['Z-Score'].mean(), 2) if not df_king.empty else 0)
    st.dataframe(df_king[["資產名稱", "趨勢", "乖離率", "Z-Score", "現價"]].sort_values("現價", ascending=False), hide_index=True, use_container_width=True)

# --- Tab 9: 💎 半導體 (原 Tab 4) ---
with t4:
    st.subheader("💎 科技巨頭與半導體強度 (vs SPY)")
    bench_s = raw_df['SPY'].ffill().dropna()
    if len(bench_s) > 60:
        bench_ret = (bench_s.iloc[-1] - bench_s.iloc[-60]) / bench_s.iloc[-60]
        res_rs = []
        for t in ["SOXX", "2330.TW"] + mag_7:
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

# --- Tab 10: 🔮 真金白銀 (原 Tab 6) ---
with t_poly:
    st.subheader("🔮 真金白銀下注預測")
    @st.cache_data(ttl=300)
    def fetch_manifold_events_filtered():
        try:
            url = "https://api.manifold.markets/v0/search-markets?term=&sort=volume&filter=open&limit=100"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if res.status_code != 200:
                url = "https://api.manifold.markets/v0/markets?limit=500"
                res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if res.status_code == 200:
                markets = res.json()
                noise = ["coin", "flip", "heads", "tails", "random", "test"]
                filtered = [m for m in markets if m.get('outcomeType') == 'BINARY' and m.get('volume', 0) > 3000 and not any(kw in m.get('question', '').lower() for kw in noise)]
                return sorted(filtered, key=lambda x: x.get('volume', 0), reverse=True)[:5]
            return []
        except: return []

    events_data = fetch_manifold_events_filtered()
    if events_data:
        translator = GoogleTranslator(source='en', target='zh-TW')
        for event in events_data:
            title_en = event.get('question', '未知事件')
            prob_yes = event.get('probability', 0)
            vol = int(event.get('volume', 0))
            if prob_yes is None: continue
            try: title_zh = translator.translate(title_en)
            except: title_zh = title_en
            st.markdown(f"#### 🏷️ {title_zh}")
            st.caption(f"原文: {title_en} | 💰 總量: ${vol:,}")
            
            c1, c2 = st.columns([1, 4])
            with c1: st.metric("Yes", f"{round(prob_yes*100, 1)}%", delta_color="off")
            with c2: st.progress(min(1.0, max(0.0, prob_yes)))
            
            c3, c4 = st.columns([1, 4])
            with c3: st.metric("No", f"{round((1-prob_yes)*100, 1)}%", delta_color="off")
            with c4: st.progress(min(1.0, max(0.0, 1-prob_yes)))
            st.write("---")
