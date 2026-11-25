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

import seasonal_lib as sl
import gold_silver_ratio as gsr
import extreme_divergence as ed
from ptt_sentiment import thermometer as ptt_th


def _fresh_module(mod):
    """本地模組檔案比記憶體中的版本新就重新載入。

    Streamlit Cloud 拉到新 commit 後只重跑主檔，已匯入的本地模組仍是舊版留在記憶體；
    2026-11-24 事故：extreme_divergence.py 新增函數後，雲端版噴 AttributeError（找不到新函數）。
    """
    import importlib
    import os
    try:
        mtime = os.path.getmtime(mod.__file__)
        if getattr(mod, "_loaded_mtime", None) != mtime:
            mod = importlib.reload(mod)
            mod._loaded_mtime = mtime
    except Exception:  # noqa: BLE001 — 重載失敗就沿用現有模組，不讓整頁掛掉
        pass
    return mod


sl = _fresh_module(sl)
gsr = _fresh_module(gsr)
ed = _fresh_module(ed)
ptt_th = _fresh_module(ptt_th)

# ==========================================
# 1. 系統設定
# ==========================================
st.set_page_config(page_title="全球金融戰情室 (AI週線旗艦版)", layout="wide")

# 禁止瀏覽器自動翻譯：Streamlit 把整頁標成英文（<html lang="en">），Chrome 會把中文「再翻一次」並改壞語意
# （2026-11-23 使用者截圖：「100＝最樂觀」被翻成「100＝最悲觀」）。Streamlit 不能直接改 <head>，
# 改由同源的零高度元件在父頁面補上語言標記與 notranslate。
import streamlit.components.v1 as _components  # noqa: E402

_components.html(
    """<script>
    const d = window.parent.document;
    d.documentElement.lang = "zh-Hant-TW";
    d.documentElement.setAttribute("translate", "no");
    d.documentElement.classList.add("notranslate");
    if (!d.querySelector('meta[name="google"]')) {
      const m = d.createElement("meta"); m.name = "google"; m.content = "notranslate"; d.head.appendChild(m);
      // 把本元件所在的格子收起來，免得多出一行間距
      const s = d.createElement("style");
      s.textContent = '[data-testid="stElementContainer"]:has(iframe[srcdoc*="notranslate"]){display:none}';
      d.head.appendChild(s);
    }
    </script>""",
    height=0,
)
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

@st.cache_data(ttl=3600)
def fetch_gold_silver_history():
    """下載完整黃金／白銀期貨日線；明訂不自動調整，避免 yfinance 預設值變動造成口徑漂移。"""
    data = yf.download(["GC=F", "SI=F"], period="max", auto_adjust=False, progress=False)
    if data.empty or 'Close' not in data.columns:
        return pd.DataFrame()
    close = data['Close']
    if not isinstance(close, pd.DataFrame) or not {"GC=F", "SI=F"}.issubset(close.columns):
        return pd.DataFrame()
    return close[["GC=F", "SI=F"]].dropna(how="all")

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

    df = raw.iloc[:, [0, 1, 2, 4, 6, 12]].copy()
    df.columns = ["DateRaw", "P", "D", "CPI", "GS10", "CAPE"]
    # 第16欄 Excess CAPE Yield 為後期才加入的欄位，舊版檔案可能沒有，故條件取用。
    if raw.shape[1] >= 17:
        df["ECY"] = raw.iloc[:, 16].values
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
    for c in [c for c in ["P", "D", "CPI", "GS10", "CAPE", "ECY"] if c in df.columns]:
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
    欄位：P（名目股價）、D（股利，年化月配版）、CPI、GS10（10年期公債殖利率）、CAPE（席勒本益比）、
          ECY（Excess CAPE Yield，舊檔可能缺）、TR（自建標普總報酬指數）。
    GS10 於 2026-11-07 加入，供「🌊 長波環境儀」計算實質利率；原有欄位名稱與順序不變。
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

# ==========================================
# 2.5b 長波環境（Regime）：實質利率 × 通膨方向
#   目的：用「可量測的總體環境」取代固定年份的康波周期表。
#   資料全部來自上方已下載的 Shiller ie_data.xls（月頻，1871 起），
#   沒有任何假設週期、正弦波或人工訂定的轉折年。
#   實質利率採「事後實質利率」(ex-post) = 名目10年期公債殖利率(GS10) − CPI年增率，
#   與 TIPS 隱含的「事前」(ex-ante) 實質利率定義不同，通膨急轉期兩者可能明顯背離。
# ==========================================
REGIME_RR_POS, REGIME_RR_NEG = "實質利率正", "實質利率負"
REGIME_INF_UP, REGIME_INF_DN = "通膨升", "通膨降"
REGIME_ORDER = [
    f"{REGIME_RR_POS} / {REGIME_INF_DN}",
    f"{REGIME_RR_POS} / {REGIME_INF_UP}",
    f"{REGIME_RR_NEG} / {REGIME_INF_UP}",
    f"{REGIME_RR_NEG} / {REGIME_INF_DN}",
]
# 顏色沿用本站既有慣例「紅＝強 / 綠＝弱」（見產業輪動、季節性長條圖的 #FF3333 / #00C000），
# 並依 REGIME_ORDER 的強弱順序做色階：①最強紅 → ④最弱綠。
# 先前版本誤用西方慣例（綠＝好、紅＝壞），與本站其他分頁相反，使用者實測反映看不懂，2026-11-07 修正。
REGIME_COLORS = ["#FF3333", "#FF9E80", "#9CCC65", "#00A000"]
REGIME_RANK = ["①", "②", "③", "④"]                     # REGIME_ORDER 已依報酬/波動由強到弱排列
REGIME_LABELS = [f"{r} {n}" for r, n in zip(REGIME_RANK, REGIME_ORDER)]
REGIME_LABEL_MAP = dict(zip(REGIME_ORDER, REGIME_LABELS))
REGIME_COLOR_MAP = dict(zip(REGIME_ORDER, REGIME_COLORS))
REGIME_TREND_MONTHS = 36
REGIME_MIN_RUN = 6   # 環境最短持續月數：撐不到半年的穿越視為雜訊，不算一次環境切換

def _enforce_min_run(labels, min_run):
    """把撐不滿 min_run 個月的環境段併入較長的鄰段（在 run-length 編碼上做，不掃原序列）。

    動機：實質利率在零軸附近會逐月來回穿越，未過濾時 151 年會碎成數百段，
    既畫不出可讀的色帶，也不符合「環境」這個概念——撐一個月的不叫環境。
    例外：**最後一段永不併入**。最新的環境本來就還在進行中（右側censored），
    把它併進前一段會讓「目前所在環境」報錯；改由呼叫端在未滿 min_run 時標示為暫定。
    """
    runs = []
    for v in labels.tolist():
        if runs and runs[-1][0] == v:
            runs[-1][1] += 1
        else:
            runs.append([v, 1])

    changed = True
    while changed and len(runs) > 1:
        changed = False
        for i in range(len(runs) - 1):          # 不含最後一段
            if runs[i][1] >= min_run:
                continue
            left = runs[i - 1] if i > 0 else None
            right = runs[i + 1] if i < len(runs) - 1 else None
            if left and right:
                tgt = left if left[1] >= right[1] else right
            else:
                tgt = left or right
            if tgt is None:
                continue
            tgt[1] += runs[i][1]
            runs.pop(i)
            j = 0
            while j < len(runs) - 1:            # 併完後相鄰同標籤要再合併
                if runs[j][0] == runs[j + 1][0]:
                    runs[j][1] += runs[j + 1][1]
                    runs.pop(j + 1)
                else:
                    j += 1
            changed = True
            break

    out = []
    for lab, n in runs:
        out.extend([lab] * n)
    return pd.Series(out, index=labels.index)

@st.cache_data(ttl=86400)
def build_long_wave_regime(src_df, trend_months=REGIME_TREND_MONTHS, min_run=REGIME_MIN_RUN):
    """由 Shiller 月頻資料建構長波環境表。

    通膨方向＝CPI年增率相對 trend_months 個月前的變化（預設36個月，抓中期趨勢而非單月噪音）。
    月報酬在「完整時序」上先算好再供分組使用——若先 groupby 再差分，同一象限內不連續的兩段
    會跨越時間缺口相減，報酬會被誇大到數百％（本專案 2026-11-07 原型實測踩過）。

    分類後再過 _enforce_min_run(min_run)：撐不滿 min_run 個月的穿越不算環境切換。
    regime_raw 保留未過濾的原始分類供稽核；統計與色帶一律用過濾後的 regime，兩者定義一致。
    """
    if src_df is None or src_df.empty or "GS10" not in src_df.columns:
        return pd.DataFrame()
    d = src_df.copy()
    d["CPI年增率"] = d["CPI"].pct_change(12) * 100
    d["實質利率"] = d["GS10"] - d["CPI年增率"]
    d["通膨趨勢"] = d["CPI年增率"] - d["CPI年增率"].shift(trend_months)
    d["月報酬"] = np.log(d["TR"]).diff()
    d = d.dropna(subset=["實質利率", "通膨趨勢", "TR"])
    if d.empty:
        return pd.DataFrame()
    rr = pd.Series(np.where(d["實質利率"] >= 0, REGIME_RR_POS, REGIME_RR_NEG), index=d.index)
    inf = pd.Series(np.where(d["通膨趨勢"] >= 0, REGIME_INF_UP, REGIME_INF_DN), index=d.index)
    d["regime_raw"] = rr + " / " + inf
    d["regime"] = _enforce_min_run(d["regime_raw"], min_run)
    return d

def regime_stats(d):
    """各象限的名目總報酬年化、年化波動與報酬/波動比（固定輸出 4 列，無樣本者填 0/NaN）。"""
    rows = []
    total = len(d) if len(d) else 1
    for name in REGIME_ORDER:
        s = d[d["regime"] == name]
        m = s["月報酬"].dropna()
        rows.append({
            "環境": name,
            "月數": len(s),
            "佔比(%)": len(s) / total * 100,
            "年化報酬(%)": (np.exp(m.mean() * 12) - 1) * 100 if len(m) else np.nan,
            "年化波動(%)": m.std() * np.sqrt(12) * 100 if len(m) > 1 else np.nan,
        })
    out = pd.DataFrame(rows)
    out["報酬/波動"] = out["年化報酬(%)"] / out["年化波動(%)"]
    return out

def regime_segments(d):
    """把月頻 regime 壓成連續區段（供長波圖畫背景色帶）。"""
    if d.empty:
        return pd.DataFrame(columns=["起", "迄", "環境"])
    grp = (d["regime"] != d["regime"].shift()).cumsum()
    segs = [{"起": g.index[0],
             "迄": g.index[-1] + pd.offsets.MonthEnd(1),
             "環境": g["regime"].iloc[0]} for _, g in d.groupby(grp)]
    return pd.DataFrame(segs)

@st.cache_data(ttl=21600, show_spinner=False)
def fetch_cftc_radar_metric():
    try:
        return ed.fetch_cftc_positioning()
    except Exception as exc:
        return ed.unavailable_metric("CFTC 機構淨曝險", f"同步失敗：{type(exc).__name__}")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_market_proxy_radar_metrics():
    try:
        return ed.fetch_market_proxy_metrics()
    except Exception as exc:
        detail = f"同步失敗：{type(exc).__name__}"
        return (
            ed.unavailable_metric("VIX 期限結構", detail),
            ed.unavailable_metric("等權廣度", detail),
        )


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_sp500_breadth_radar_metric():
    try:
        return ed.fetch_sp500_sma200_breadth()
    except Exception as exc:
        return ed.unavailable_metric("S&P 500 年線廣度", f"同步失敗：{type(exc).__name__}")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_sentiment_extremes_block():
    try:
        return ed.fetch_sentiment_extremes()
    except Exception as exc:
        result = ed.build_sentiment_extremes(None, None, pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float))
        result["errors"] = [f"同步失敗：{type(exc).__name__}"]
        return result

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
    "^VIX": "VIX 恐慌", "BTC-USD": "比特幣", "GC=F": "黃金", "SI=F": "白銀", "HG=F": "期貨銅", "CL=F": "原油",
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
gold_silver_history_df = fetch_gold_silver_history()

sp500_hist_df = fetch_long_term_index("^GSPC")
nasdaq_hist_df = fetch_long_term_index("^IXIC")
twii_hist_df = fetch_long_term_index("^TWII")
twii_start_year = int(twii_hist_df.index.min().year) if not twii_hist_df.empty else 1997
shiller_df = fetch_shiller_data()
shiller_tr_series = shiller_df["TR"].dropna() if not shiller_df.empty else pd.Series(dtype=float)
shiller_cape_series = shiller_df["CAPE"] if not shiller_df.empty else pd.Series(dtype=float)
long_wave_df = build_long_wave_regime(shiller_df)

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

def calculate_ivp(series, window=253):
    """IV Percentile：每日定義為「過去 252 個交易日（不含當日）中，收盤低於當日收盤的天數比例 ×100」。
    window=253 代表含當日共 253 筆（前 252 筆為歷史比較基準）；暖機期自然回傳 NaN。"""
    return series.rolling(window).apply(lambda w: (w[:-1] < w[-1]).mean() * 100, raw=True)

def classify_ivp_state(ivp, vix):
    """依 IVP（252日相對位置）與 VIX 絕對值判定狀態標籤，優先順序由上而下。"""
    if pd.isna(ivp) or pd.isna(vix):
        return "資料暖機中"
    if ivp >= 95 and vix < 20:
        return "🔥 極端擠壓（風暴前夕）"
    if ivp >= 95:
        return "🚨 恐慌極端高位"
    if ivp >= 80:
        return "⚠️ 相對高位"
    if ivp <= 20:
        return "🟢 相對低位（自滿區）"
    return "中性"

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
t_cycle, t_wave, t_ind, t_war, t_hurst, t1, t3, t5, t_crash, t2, t_ptt, t4, t_poly = st.tabs([
    "🗓️ 歷史週期", "🌊 長波環境儀", "🏭 週期×產業", "⚔️ 戰爭週期雷達", "📊 赫斯特循環", "💀 AI 資金",
    "🚀 風險雷達", "📈 主要市場", "🚨 極端背離雷達", "🇹🇼 台股戰略", "🌡️ 股民溫度計", "💎 半導體", "🔮 真金白銀"
])

# --- Tab 1: 🗓️ 歷史週期 (原 Tab 8) ---
with t_cycle:
    st.error("## 🗓️ 總統大選週期與月度歷史地圖")
    st.caption("由本地量化引擎自動分析 **標普 500**、**那斯達克** 與 **Shiller 長期總報酬（1871起）** 大數據庫，支援自訂觀測基準、時空、回溯區間與估值環境過濾。")
    st.divider()

    current_year = datetime.now(tw_tz).year
    SHILLER_BASIS_LABEL = "標普總報酬 Shiller (1871起, 含股利)"
    TWII_BASIS_LABEL = "台灣加權 (^TWII)"

    c_idx, c_year, c_lookback, c_month = st.columns([1, 1, 1, 1])

    with c_idx:
        index_dict = {
            "標普 500 (^GSPC)": sp500_hist_df,
            "那斯達克 (^IXIC)": nasdaq_hist_df,
            SHILLER_BASIS_LABEL: shiller_tr_series,
            TWII_BASIS_LABEL: twii_hist_df,
        }
        selected_idx_str = st.selectbox("1️⃣ 選擇觀測基準：", list(index_dict.keys()), index=0)
        active_hist_df = index_dict[selected_idx_str]
        is_shiller_basis = (selected_idx_str == SHILLER_BASIS_LABEL)
        is_twii_basis = (selected_idx_str == TWII_BASIS_LABEL)

    with c_year:
        selected_cycle_year = st.selectbox("2️⃣ 選擇觀測年份：", [current_year, current_year + 1, current_year + 2], index=0)

    with c_lookback:
        if is_shiller_basis:
            lookback_options = {"30年": 30, "40年": 40, "50年": 50, "80年": 80, "全部 (最長至1871)": 200}
        elif is_twii_basis:
            lookback_options = {"10年": 10, "20年": 20, f"全部 (最長至{twii_start_year})": 200}
        else:
            lookback_options = {"30年": 30, "40年": 40, "50年": 50, "全部 (最長至1927)": 100}
        selected_lookback_str = st.selectbox(
            "3️⃣ 選擇歷史回溯區間：", list(lookback_options.keys()), index=2,
            key=f"cycle_lookback_sel_{is_shiller_basis}_{is_twii_basis}"
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
    if is_twii_basis:
        st.caption(f"💡 台灣自 1996 起總統大選與美國同年（皆四年一屆），本週期定位對台股同樣適用；^TWII 資料自 {twii_start_year} 起，樣本較少請注意。")
        if selected_econ_filter != ECON_FILTER_ALL:
            st.caption("⚠️ 景氣過濾採美國 NBER 衰退年定義；台股高度連動美國景氣，但此切片屬參考性質。")

    cycle_index = (selected_cycle_year - 2025) % 4
    cycle_names = ["第一年 (選後/重新定調)", "第二年 (期中選舉/通常最震盪)", "第三年 (選前/通常最強勁)", "第四年 (大選/波動後迎慶祝)"]
    current_cycle_name = cycle_names[cycle_index]

    if is_shiller_basis:
        min_year_floor = 1871
    elif is_twii_basis:
        min_year_floor = twii_start_year
    else:
        min_year_floor = 1927
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
        # 月報酬與逐月平均改走 seasonal_lib（與 seasonal_export.py 共用同一套算法，
        # 兩邊數字保證一致；2026-08-29 抽出）。
        _monthly_seasonality = sl.monthly_avg_returns(active_hist_df, base_history_years)
        matched_rets = _monthly_seasonality["matched_rets"]
        if not matched_rets.empty:
            rets_array = [_monthly_seasonality["by_month"][m] for m in range(1, 13)]
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

        # 月報酬定義統一為「月對月」（前月底收盤→本月底收盤），與上方季節性長條圖同一套 matched_rets；
        # 若前月資料不存在（樣本年首月），該年份樣本會因 pct_change() 產生 NaN 而由 dropna() 剔除。
        month_rets_series = matched_rets[matched_rets.index.month == selected_month_num].dropna() if not matched_rets.empty else pd.Series(dtype=float)
        monthly_returns = month_rets_series.tolist()

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
            else:
                OVERLAY_SCOPE_CYCLE = "同週期年份（預設）"
                OVERLAY_SCOPE_ALL = "全部年度"
                OVERLAY_SCOPE_MIDTERM = "期中選舉年"
                c_overlay, _c_overlay_spacer = st.columns([1, 3])
                with c_overlay:
                    selected_overlay_scope = st.selectbox(
                        "疊加樣本範圍：",
                        [OVERLAY_SCOPE_CYCLE, OVERLAY_SCOPE_ALL, OVERLAY_SCOPE_MIDTERM],
                        index=0, key="cycle_overlay_scope"
                    )

                # 期中選舉年＝總統週期第二年，(y-2025)%4==1（2026、2022、2018…）
                if selected_overlay_scope == OVERLAY_SCOPE_CYCLE:
                    overlay_years = list(base_history_years)
                else:
                    overlay_years = list(range(start_eval_year, current_year))
                    if selected_overlay_scope == OVERLAY_SCOPE_MIDTERM:
                        overlay_years = [y for y in overlay_years if (y - 2025) % 4 == 1]
                    overlay_years.sort(reverse=True)
                    st.caption("💡 「全部年度／期中選舉年」模式只依年份取樣，不套用上方估值（CAPE）與景氣（NBER）過濾。")

                # 日內走勢疊加圖僅供視覺化，非月報酬統計，以當月首個交易日為基準 100 正規化；
                # 圖例以 ★ 標記期中選舉年，讓線條可直接分辨週期屬性。
                # 正規化與平均基準線改走 seasonal_lib.daily_path_overlay（與 seasonal_export.py
                # 共用，2026-08-29 抽出）；本區塊只做圖例標籤與 DataFrame 組裝。
                _overlay_result = sl.daily_path_overlay(active_hist_df, selected_month_num, overlay_years)
                monthly_trends = pd.DataFrame()
                midterm_labels = set()
                for hist_year in _overlay_result["years"]:
                    if sl.is_midterm_year(hist_year):
                        year_label = f"{hist_year}年★期中"
                        midterm_labels.add(year_label)
                    else:
                        year_label = f"{hist_year}年"
                    monthly_trends[year_label] = _overlay_result["daily_paths"][str(hist_year)]

                if not monthly_trends.empty:
                    monthly_trends['平均基準線 (Avg Base)'] = _overlay_result["avg_baseline"]
                    monthly_trends['交易日 (Day)'] = range(1, len(monthly_trends) + 1)

                    chart_data = monthly_trends.melt(id_vars=['交易日 (Day)'], var_name='年份', value_name='標準化點位 (基準100)')

                    # 全部年度模式下把期中年線條加粗突顯，其餘年份淡化；其他模式維持原本樣式
                    _emphasize_midterm = (selected_overlay_scope == OVERLAY_SCOPE_ALL)
                    def _line_width(name):
                        if name == '平均基準線 (Avg Base)':
                            return 4.0
                        if _emphasize_midterm and name in midterm_labels:
                            return 2.2
                        return 1.0
                    def _line_opacity(name):
                        if name == '平均基準線 (Avg Base)':
                            return 1.0
                        if _emphasize_midterm:
                            return 0.9 if name in midterm_labels else 0.25
                        return 0.4
                    def _cycle_tag(name):
                        if name == '平均基準線 (Avg Base)':
                            return '平均基準線'
                        return '期中選舉年' if name in midterm_labels else '其他年度'
                    chart_data['線寬'] = chart_data['年份'].map(_line_width)
                    chart_data['不透明度'] = chart_data['年份'].map(_line_opacity)
                    chart_data['週期屬性'] = chart_data['年份'].map(_cycle_tag)

                    lines = alt.Chart(chart_data).mark_line().encode(
                        x=alt.X('交易日 (Day):O', axis=alt.Axis(labelAngle=0)),
                        y=alt.Y('標準化點位 (基準100):Q', scale=alt.Scale(zero=False)),
                        color=alt.condition(
                            alt.datum.年份 == '平均基準線 (Avg Base)',
                            alt.value('#deff9a'),
                            alt.Color('年份:N', legend=alt.Legend(title="歷史疊加（★＝期中選舉年）"))
                        ),
                        size=alt.Size('線寬:Q', scale=None, legend=None),
                        opacity=alt.Opacity('不透明度:Q', scale=None, legend=None),
                        tooltip=['交易日 (Day)', '年份', '週期屬性', alt.Tooltip('標準化點位 (基準100)', format='.2f')]
                    ).properties(height=400)

                    st.altair_chart(lines, use_container_width=True)
                    st.caption(f"💡 圖表判讀：若當前市場 ({selected_cycle_year}年 {selected_month_str}) 的實際走勢強於黃綠色的「平均基準線」，代表『近期強勢資金』成功抵銷歷史魔咒；反之則需提防技術修正。圖例年份帶 ★ 者為期中選舉年。")
                else:
                    st.caption("ℹ️ 所選疊加樣本範圍內，該月份無可用的日線資料。")
        else:
            st.warning(f"在所選的歷史區間內，無足夠的 {selected_month_str} 數據樣本進行疊加計算。")
    else:
        st.warning(f"無法載入 {selected_idx_str} 歷史大數據庫，請確認網路連線。")

# --- Tab 1.2: 🌊 長波環境儀 ---
with t_wave:
    st.error("## 🌊 長波環境儀：實質利率 × 通膨方向")
    st.caption(
        "康波（康德拉季耶夫長波）在網路上多半被畫成固定年份表，但那是算術產物、不是資料。"
        "本分頁改用 Shiller 月頻實測資料重建長波環境：名目10年期公債殖利率、CPI年增率、實質利率，"
        "每一點都是量測值，沒有任何假設週期或正弦波。目的不是預測哪一年崩盤，而是回答「現在是哪種世界、"
        "我的回測樣本踩過幾種世界」。"
    )
    st.divider()

    if long_wave_df.empty:
        st.warning("⚠️ Shiller 長期資料載入失敗，或檔案缺少 GS10 利率欄位，長波環境儀暫時無法計算。")
    else:
        lw = long_wave_df
        lw_stats = regime_stats(lw)
        cur_row = lw.iloc[-1]
        cur_regime = cur_row["regime"]
        lw_asof = lw.index[-1]

        # ---------- 現況 ----------
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("名目 10Y 殖利率", f"{cur_row['GS10']:.2f}%")
        s2.metric("CPI 年增率", f"{cur_row['CPI年增率']:.1f}%")
        s3.metric("實質利率 (事後)", f"{cur_row['實質利率']:.2f}%")
        s4.metric("CAPE", f"{cur_row['CAPE']:.1f}" if pd.notna(cur_row.get("CAPE")) else "—")
        _tail_run = int((lw["regime"] != lw["regime"].shift()).cumsum().eq(
            (lw["regime"] != lw["regime"].shift()).cumsum().iloc[-1]).sum())
        if _tail_run < REGIME_MIN_RUN:
            st.info(f"📍 **目前所在環境（{lw_asof:%Y-%m}）：{REGIME_LABEL_MAP[cur_regime]}　⚠️ 暫定**　"
                    f"——此環境才持續 {_tail_run} 個月，尚未滿 {REGIME_MIN_RUN} 個月的確認門檻，可能回彈。")
        else:
            st.info(f"📍 **目前所在環境（{lw_asof:%Y-%m}）：{REGIME_LABEL_MAP[cur_regime]}**　"
                    f"——已持續 {_tail_run} 個月。")
        st.caption(
            f"💡 實質利率＝GS10 − CPI年增率，屬「事後」(ex-post) 定義，與 TIPS 隱含的事前實質利率不同。"
            f"通膨方向以 CPI年增率相對 {REGIME_TREND_MONTHS} 個月前的變化判定；"
            f"撐不滿 {REGIME_MIN_RUN} 個月的穿越不算一次環境切換（避免零軸附近逐月跳動）。"
            "Shiller 檔案最新 1～2 個月的 CPI 為該站估計值，最新一點請視為暫估。"
        )
        st.divider()

        # ---------- 區塊 A：實質利率長波圖 ----------
        st.markdown("#### 📉 實質利率長波（全部為實測資料）")
        _lb_map = {"全部 (最長至1875)": None, "近 100 年": 100, "近 60 年 (約一個康波)": 60, "近 30 年": 30}
        wave_lookback = st.selectbox("觀測區間：", list(_lb_map.keys()), index=0, key="wave_lookback")
        _lb = _lb_map[wave_lookback]
        lw_view = lw if _lb is None else lw.loc[lw.index >= (lw.index[-1] - pd.DateOffset(years=_lb))]

        plot_df = (lw_view[["GS10", "CPI年增率", "實質利率"]]
                   .rename(columns={"GS10": "名目10Y殖利率"})
                   .reset_index()
                   .melt(id_vars="Date", var_name="項目", value_name="百分比")
                   .dropna(subset=["百分比"]))
        seg_df = regime_segments(lw_view)
        seg_df["環境標籤"] = seg_df["環境"].map(REGIME_LABEL_MAP)

        # 環境色帶改放在圖表「底部專屬的一條」，不再當成整張圖的背景。
        # 原因：滿版背景色帶會跟三條折線搶同一塊畫布，色塊一濃線就看不清、一淡色帶就認不出
        #（2026-11-07 使用者實測反映「看了很久、不夠直覺」）。
        # 作法是沿用同一個 y 軸，把最下面約 6% 的值域讓給色帶，如此座標軸天然對齊，
        # 又能維持 use_container_width 的自適應寬度（vconcat 無法吃容器寬度）。
        _y_lo, _y_hi = float(plot_df["百分比"].min()), float(plot_df["百分比"].max())
        _span = max(_y_hi - _y_lo, 1.0)
        _strip_h, _pad = _span * 0.06, _span * 0.035
        _y_bottom = _y_lo - _pad - _strip_h          # 整張圖的最底（＝色帶底緣）
        _strip_top = _y_bottom + _strip_h            # 色帶頂緣，折線一律在此之上

        strip = alt.Chart(seg_df).mark_rect().encode(
            x=alt.X("起:T", title=None),
            x2="迄:T",
            y=alt.datum(_y_bottom),
            y2=alt.datum(_strip_top),
            color=alt.Color("環境標籤:N",
                            scale=alt.Scale(domain=REGIME_LABELS, range=REGIME_COLORS),
                            legend=alt.Legend(title="底部色帶＝當時總體環境｜顏色＝該環境的歷史股市報酬（① 紅＝最優 → ④ 綠＝最劣）",
                                              orient="bottom", columns=2,
                                              symbolType="square", symbolSize=300,
                                              labelFontSize=12, titleFontSize=12,
                                              titleLimit=0, labelLimit=0)),
            tooltip=[alt.Tooltip("環境標籤:N", title="環境"), alt.Tooltip("起:T", format="%Y-%m", title="起"),
                     alt.Tooltip("迄:T", format="%Y-%m", title="迄")],
        )
        zero_rule = alt.Chart(pd.DataFrame({"零軸": [0.0]})).mark_rule(
            color="#999999", strokeDash=[4, 4]).encode(y="零軸:Q")
        lines = alt.Chart(plot_df).mark_line(strokeWidth=1.7).encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y("百分比:Q", title="%",
                    scale=alt.Scale(domain=[_y_bottom, _y_hi + _pad], nice=False)),
            color=alt.Color("項目:N",
                            scale=alt.Scale(domain=["名目10Y殖利率", "CPI年增率", "實質利率"],
                                            range=["#4FC3F7", "#FF8A65", "#FFD54F"]),
                            legend=alt.Legend(title="指標", orient="bottom", labelFontSize=12)),
            tooltip=[alt.Tooltip("Date:T", format="%Y-%m", title="月份"), alt.Tooltip("項目:N"),
                     alt.Tooltip("百分比:Q", format=".2f")],
        )
        st.altair_chart(
            alt.layer(strip, zero_rule, lines).resolve_scale(color="independent").properties(height=440),
            use_container_width=True)
        st.caption("💡 **象限本身不是股市報酬**，只由兩個總體變數定義：實質利率正負 × 通膨升降。"
                   "**顏色與 ①→④ 編號才是股市**——依標普含股利總報酬在該環境下的歷史表現，"
                   "由優（紅）排到劣（綠），同本站紅漲綠跌慣例，與下方四象限卡的圓點同色。"
                   "這是 151 年的**事後描述統計，不是預測**：落在 ② 不代表今年會有 ② 的報酬。")
        st.caption("💡 上方三條線是實測的名目殖利率、通膨與實質利率。看 1981→2021 那條 40 年的"
                   "實質利率下行長波——那才是康波想描述的東西，而它在 2022 年結束了。")
        st.divider()

        # ---------- 區塊 B：四象限 ----------
        st.markdown("#### 🧭 四象限：同一個市場，四種世界")
        st.caption("↓ **上下＝實質利率正負，左右＝通膨方向（左降・右升）**，是真的 2×2 象限矩陣。"
                   "**格子怎麼分跟股市無關**，格子裡的報酬數字才是股市在該環境下的歷史表現；"
                   "①→④ 是依歷史報酬優劣排的名次，所以不照矩陣位置順著走。")
        st.caption(f"統計區間 {lw.index[0]:%Y-%m} ~ {lw_asof:%Y-%m}（{len(lw)} 個月，約 {len(lw)//12} 年，"
                   f"環境最短持續 {REGIME_MIN_RUN} 個月）。"
                   "報酬為標普含股利總報酬（名目），屬描述性歷史統計非交易訊號。")
        # 卡片依「真正的 2×2 象限矩陣」排版，不照 REGIME_ORDER 的名次順序：
        #   上排＝實質利率正、下排＝實質利率負；左欄＝通膨降、右欄＝通膨升。
        # REGIME_ORDER 是 [正/降, 正/升, 負/升, 負/降]（名次順序），直接鋪會讓左右欄的通膨方向不一致
        #（左欄變成 ①通膨降 + ③通膨升），所以下排對調成 ④、③。
        _grid_order = [REGIME_ORDER[0], REGIME_ORDER[1], REGIME_ORDER[3], REGIME_ORDER[2]]
        _cells = list(st.columns(2)) + list(st.columns(2))
        for _col, _name in zip(_cells, _grid_order):
            _r = lw_stats[lw_stats["環境"] == _name].iloc[0]
            with _col:
                with st.container(border=True):
                    _is_cur = (_name == cur_regime)
                    st.markdown(
                        f"<span style='color:{REGIME_COLOR_MAP[_name]};font-size:1.25rem'>●</span> "
                        f"<b>{REGIME_LABEL_MAP[_name]}</b>"
                        f"{'　<b>← 目前所在</b>' if _is_cur else ''}",
                        unsafe_allow_html=True)
                    if _r["月數"] == 0:
                        st.caption("此樣本內無觀測")
                    else:
                        m1, m2, m3 = st.columns(3)
                        m1.metric("年化報酬", f"{_r['年化報酬(%)']:.1f}%")
                        m2.metric("年化波動", f"{_r['年化波動(%)']:.1f}%")
                        m3.metric("報酬/波動", f"{_r['報酬/波動']:.2f}")
                        st.caption(f"歷史佔比 {_r['佔比(%)']:.0f}%（{int(_r['月數'])} 個月）")
        st.divider()

        # ---------- 區塊 C：回測樣本環境覆蓋度 ----------
        st.markdown("#### 🧪 回測樣本環境覆蓋度檢查")
        st.caption("本分頁唯一會改變你行為的區塊：檢查一段回測樣本到底踩過幾種世界。"
                   "只涵蓋單一環境的參數，等於完全沒有跨環境的樣本外驗證。")

        _presets = {
            "台指期 William（2015-01 起）": datetime(2015, 1, 1).date(),
            "台指期 shioaji 逐筆（2020-03 起）": datetime(2020, 3, 1).date(),
            "個股逐筆（2024-08 起）": datetime(2024, 8, 1).date(),
            "自訂…": None,
        }
        pc1, pc2 = st.columns([1.4, 1])
        with pc1:
            _preset = st.selectbox("選擇回測樣本起點：", list(_presets.keys()), index=0, key="wave_preset")
        with pc2:
            if _presets[_preset] is None:
                _start_date = st.date_input("自訂起始日", value=datetime(2020, 1, 1).date(),
                                            min_value=lw.index[0].date(), max_value=lw_asof.date(),
                                            key="wave_start")
            else:
                _start_date = _presets[_preset]
                st.markdown(f"<div style='padding-top:1.9rem'>起始：<b>{_start_date:%Y-%m-%d}</b></div>",
                            unsafe_allow_html=True)

        sample = lw.loc[pd.Timestamp(_start_date):]
        if len(sample) < 6:
            st.warning("⚠️ 樣本不足 6 個月，無法評估環境覆蓋度。")
        else:
            cov = (sample["regime"].value_counts(normalize=True) * 100).reindex(REGIME_ORDER).fillna(0.0)
            n_cov = int((cov > 0).sum())
            top_name, top_share = cov.idxmax(), float(cov.max())
            _hist_share = {r["環境"]: r["佔比(%)"] for _, r in lw_stats.iterrows()}
            _missing = [n for n in REGIME_ORDER if cov[n] == 0]

            k1, k2, k3 = st.columns(3)
            k1.metric("樣本長度", f"{len(sample)} 個月")
            k2.metric("涵蓋象限", f"{n_cov} / 4")
            k3.metric("最大單一象限佔比", f"{top_share:.0f}%")

            if n_cov <= 2 or top_share > 70:
                st.error(
                    f"🚨 **樣本偏食警告**：這段樣本只踩到 4 個環境中的 {n_cov} 個，"
                    f"其中「{REGIME_LABEL_MAP[top_name]}」就佔了 {top_share:.0f}%"
                    f"（歷史長期佔比僅 {_hist_share.get(top_name, 0):.0f}%）。"
                    "在這段資料上調出來的參數，只在這一種世界被驗證過——環境切換時失效不是策略衰退，是從來沒測過。")
            elif n_cov == 3:
                st.warning(f"⚠️ 這段樣本涵蓋 3 / 4 個環境，缺少「{REGIME_LABEL_MAP[_missing[0]]}」。"
                           "結論可外推的範圍有限，建議在回測報表上標註未覆蓋的環境。")
            else:
                st.success(f"✅ 這段樣本四個環境都踩到了，最大單一象限佔比 {top_share:.0f}%。"
                           "跨環境的樣本外驗證條件成立，但仍請檢查各象限的交易筆數是否足夠。")

            cmp_df = pd.DataFrame({
                "環境": list(REGIME_LABELS),
                "你的樣本": [float(cov[n]) for n in REGIME_ORDER],
                "歷史長期": [float(_hist_share.get(n, 0.0)) for n in REGIME_ORDER],
            }).melt(id_vars="環境", var_name="類別", value_name="佔比")
            cov_bar = alt.Chart(cmp_df).mark_bar().encode(
                y=alt.Y("環境:N", sort=list(REGIME_LABELS), title=None,
                        axis=alt.Axis(labelLimit=240)),
                x=alt.X("佔比:Q", title="佔比 (%)", axis=alt.Axis(tickCount=6)),
                yOffset=alt.YOffset("類別:N"),
                color=alt.Color("類別:N",
                                scale=alt.Scale(domain=["你的樣本", "歷史長期"], range=["#FF3333", "#6E6E6E"]),
                                legend=alt.Legend(title=None, orient="bottom")),
                tooltip=[alt.Tooltip("環境:N"), alt.Tooltip("類別:N"), alt.Tooltip("佔比:Q", format=".1f")],
            ).properties(height=240)
            st.altair_chart(cov_bar, use_container_width=True)
            st.caption("💡 紅條（你的樣本）遠高於灰條（歷史長期）的象限，就是你的回測被過度代表的那種世界。")

        # ---------- 區塊 D：民間康波年份表對照 ----------
        with st.expander("📜 民間「康波周期表」年份對照（非本站計算，僅供辨識社群說法）"):
            st.caption("以下年份出自網路流傳的康波周期表。它是固定算術級數，不是從任何資料擬合而來，也沒有失效條件。"
                       "本站不以此做任何判斷，列出只為讓你辨識社群在傳什麼。")
            st.dataframe(pd.DataFrame({
                "層級": ["長波高點", "中週期節點", "短週期低點"],
                "年份序列": [
                    "1965, 1981, 1999, 2019, 2035, 2053",
                    "1962, 1972, 1980, 1989, 1999, 2007, 2016, 2026, 2034, 2043, 2053",
                    "1969, 1978, 1985, 1996, 2005, 2012, 2023, 2032, 2039, 2050",
                ],
                "間隔": ["16-18-20 無限循環", "10-8-9 無限循環", "9-7-11 無限循環"],
            }), use_container_width=True, hide_index=True)
            st.caption("💡 三層的間隔都完全重複、零例外——這是該表由算術生成而非資料歸納的直接證據。"
                       "真實經濟數據不會這麼整齊。上方的實質利率長波圖才是實測值。")

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
    st.subheader("🥇🥈 金銀比：白銀相對壓力與補漲統計")
    st.caption("固定門檻 80／90／100；持有期固定為 63 個共同交易日。主要判讀採首次穿越＋63 日冷卻的獨立事件，不把連續多日重複計成獨立交易。")

    if gold_silver_history_df.empty:
        st.warning("黃金／白銀完整歷史資料暫時無法取得。")
    else:
        try:
            metals_snapshot = gsr.build_dashboard_snapshot(
                gold_silver_history_df["GC=F"],
                gold_silver_history_df["SI=F"],
                horizon=63,
                rolling_years=10,
            )
            current_ratio = metals_snapshot["current_ratio"]
            current_state = metals_snapshot["current_state"]
            last_price_date = metals_snapshot["last_price_date"]
            maturity_cutoff = metals_snapshot["maturity_cutoff"]

            gr1, gr2, gr3, gr4 = st.columns(4)
            gr1.metric("當前金銀比", f"{current_ratio:.2f}", f"距 80：{current_ratio - 80:+.2f}", delta_color="off")
            gr2.metric("10 年相對位置", f"{metals_snapshot['rolling_percentile']:.1f}%", "百分位", delta_color="off")
            gr3.metric("目前狀態", current_state.label, delta_color="off")
            gr4.metric("已成熟結果截至", pd.Timestamp(maturity_cutoff).strftime("%Y-%m-%d"), "排除最近 63 日", delta_color="off")
            st.caption(f"{current_state.detail}｜價格截至 {pd.Timestamp(last_price_date).strftime('%Y-%m-%d')}。")

            ratio_view = metals_snapshot["frame"].loc[:, ["ratio"]].tail(1260).reset_index()
            ratio_view.columns = ["日期", "金銀比"]
            ratio_low = float(ratio_view["金銀比"].min())
            ratio_high = float(ratio_view["金銀比"].max())
            ratio_pad = max((ratio_high - ratio_low) * 0.08, 2.0)
            threshold_lines = pd.DataFrame({"門檻值": [80.0, 90.0, 100.0], "標籤": ["觀察 80", "極端 90", "稀有 100"]})

            # 疊圖時各層的 y 軸刻度會合併：門檻線那層若不給同一個 scale，
            # 預設含 0 會把範圍整個拉回 0，波動就被壓扁。三層必須共用。
            ratio_scale = alt.Scale(domain=[ratio_low - ratio_pad, ratio_high + ratio_pad], nice=False)
            ratio_line = alt.Chart(ratio_view).mark_line(color="#e03131", strokeWidth=1.6).encode(
                x=alt.X("日期:T", title=None, axis=alt.Axis(format="%Y", tickCount="year", labelAngle=0)),
                y=alt.Y("金銀比:Q", title=None, scale=ratio_scale),
                tooltip=[alt.Tooltip("日期:T", title="日期"), alt.Tooltip("金銀比:Q", format=".2f")],
            )
            ratio_rules = alt.Chart(threshold_lines).mark_rule(
                color="#9aa0a6", strokeDash=[6, 4], strokeWidth=1
            ).encode(y=alt.Y("門檻值:Q", title=None, scale=ratio_scale))
            ratio_labels = alt.Chart(threshold_lines).mark_text(
                align="left", dx=6, dy=-6, color="#9aa0a6", fontSize=11
            ).encode(y=alt.Y("門檻值:Q", title=None, scale=ratio_scale), text="標籤:N", x=alt.value(4))
            st.altair_chart(
                (ratio_rules + ratio_labels + ratio_line).properties(height=300, title="近 5 年金銀比走勢"),
                width="stretch",
            )

            def _format_ratio_table(source_df):
                display = source_df[[
                    "條件", "逐日樣本", "逐日勝率", "逐日平均報酬",
                    "獨立事件數", "事件勝率", "事件平均報酬", "相對基準增益"
                ]].copy()
                for col in ["逐日勝率", "逐日平均報酬", "事件勝率", "事件平均報酬", "相對基準增益"]:
                    display[col] = display[col].map(lambda value: "—" if pd.isna(value) else f"{value:.1%}")
                return display

            ratio_tab_rolling, ratio_tab_full = st.tabs(["10 年滾動視窗（主判讀）", "2000 年起全歷史（影片對照）"])
            with ratio_tab_rolling:
                rolling_table = metals_snapshot["rolling_window"]
                st.dataframe(_format_ratio_table(rolling_table), hide_index=True, width="stretch")
                st.caption("相對基準增益＝同一視窗下的條件平均報酬－全部交易日平均報酬。獨立事件少於 20 筆時只列為觀察，不升格為交易訊號。")
                try:
                    base_row = rolling_table.loc[rolling_table["條件"] == "全部交易日"].iloc[0]
                    thr80_row = rolling_table.loc[rolling_table["條件"] == "金銀比 ≥80"].iloc[0]
                    edge_win = thr80_row["事件勝率"] - base_row["事件勝率"]
                    edge_ret = thr80_row["事件平均報酬"] - base_row["事件平均報酬"]
                    st.info(
                        "**去重疊後讀法**：≥80 的獨立事件勝率 "
                        f"{thr80_row['事件勝率']:.1%}（{int(thr80_row['獨立事件數'])} 筆）對上全部交易日基準 "
                        f"{base_row['事件勝率']:.1%}（{int(base_row['獨立事件數'])} 筆），勝率差 {edge_win:+.1%}、"
                        f"平均報酬差 {edge_ret:+.1%}。逐日欄位的高勝率主要來自重疊樣本，"
                        "獨立事件口徑下的優勢小很多——這一欄才是接近可交易性的數字。"
                    )
                except (IndexError, KeyError):
                    pass
            with ratio_tab_full:
                st.dataframe(_format_ratio_table(metals_snapshot["full_history"]), hide_index=True, width="stretch")
                st.caption("此表用來重現影片，不作當前預測。≥100 即使逐日勝率為 100%，仍只集中於少數危機期間。")

            MIN_EVENTS_FOR_CHART = 5
            stability = metals_snapshot["rolling_stability"].dropna(subset=["事件勝率"]).copy()
            stability = stability[stability["獨立事件數"] >= MIN_EVENTS_FOR_CHART]
            if not stability.empty:
                stability["勝率百分比"] = stability["事件勝率"] * 100.0
                # size 不能掛在 mark_line 上：Vega-Lite 會依「門檻×事件數」再分組，
                # 每組只剩 1 點，線段就畫不出來。線與點必須分兩層。
                stability_base = alt.Chart(stability).encode(
                    x=alt.X(
                        "日期:T",
                        title="滾動統計日期",
                        axis=alt.Axis(format="%Y", tickCount="year", labelAngle=0),
                    ),
                    y=alt.Y(
                        "勝率百分比:Q",
                        title="事件勝率 (%)",
                        scale=alt.Scale(domain=[0, 100]),
                    ),
                    # 預設配色在深色主題下兩條都是藍的，分不出來；沿用面板的語義色：
                    # 觀察區用橘、極端區用紅。
                    color=alt.Color(
                        "門檻:N",
                        title="固定門檻",
                        scale=alt.Scale(domain=["≥80", "≥90"], range=["#f59f00", "#e03131"]),
                    ),
                )
                stability_tooltip = [
                    alt.Tooltip("日期:T", title="日期"),
                    alt.Tooltip("門檻:N", title="門檻"),
                    alt.Tooltip("勝率百分比:Q", title="事件勝率 (%)", format=".1f"),
                    alt.Tooltip("獨立事件數:Q", title="事件數", format=".0f"),
                ]
                stability_chart = (
                    stability_base.mark_line(strokeWidth=1.8)
                    + stability_base.mark_point(filled=True, opacity=0.9).encode(
                        size=alt.Size("獨立事件數:Q", title="該視窗事件數", scale=alt.Scale(range=[30, 220])),
                        tooltip=stability_tooltip,
                    )
                ).properties(height=300, title="10 年視窗滾動穩定度（按季重算）")
                st.altair_chart(stability_chart, width="stretch")
                st.caption(
                    f"只畫事件數 ≥{MIN_EVENTS_FOR_CHART} 的時點；早年視窗常只有 1~2 個事件，"
                    "勝率會固定在 0% 或 100%，那是樣本不足不是穩定。點越大代表該時點背後事件越多。"
                )
        except Exception as exc:
            st.warning(f"金銀比統計暫時無法計算：{exc}")

    st.divider()
    df_rz, _, _ = get_stats(["^VIX", "BTC-USD", "GC=F", "HG=F", "CL=F", "DX-Y.NYB"], raw_df)
    st.dataframe(df_rz[["資產名稱", "Z-Score", "趨勢", "現價"]], hide_index=True, use_container_width=True)

# --- Tab 6: 📈 主要市場 (原 Tab 5) ---
with t5:
    st.subheader("📈 全球資產趨勢與動態基準")
    try:
        _default_sel_idx = all_tk.index("^VIX")
    except ValueError:
        _default_sel_idx = 0
    sel = st.selectbox("選擇商品：", all_tk, index=_default_sel_idx, format_func=lambda x: f"{name_map.get(x,x)} ({x})", key="main_trend_selector")
    if sel:
        plot_data = raw_df[sel].ffill().dropna()
        if not plot_data.empty:
            if sel == "^VIX":
                # raw_df 的聯集日曆含 BTC-USD 的週末列，ffill 會把週末假資料灌進 VIX 序列，
                # 使「252 列」只涵蓋約 8 個月；IVP 與圖表必須以 VIX 真實交易日計算。
                plot_data = raw_df[sel].dropna()
                ivp_window = st.radio("IVP 回看視窗：", [252, 126, 60, 20], horizontal=True,
                                      format_func=lambda d: f"{d} 日", key="ivp_window_sel")
                ivp_series = calculate_ivp(plot_data, window=ivp_window + 1)
                ivp_valid_start = ivp_series.first_valid_index()
                if ivp_valid_start is None:
                    st.warning(f"歷史資料不足 {ivp_window + 1} 個交易日，無法計算 IVP。")
                    st.line_chart(pd.DataFrame({"現價": plot_data}))
                else:
                    vix_view = plot_data.loc[ivp_valid_start:]
                    ivp_view = ivp_series.loc[ivp_valid_start:]

                    vix_now = plot_data.iloc[-1]
                    vix_prev = plot_data.iloc[-2] if len(plot_data) > 1 else vix_now
                    ivp_now = ivp_series.iloc[-1]
                    state_label = classify_ivp_state(ivp_now, vix_now)

                    mc1, mc2, mc3 = st.columns(3)
                    with mc1:
                        st.metric("VIX 現價", f"{vix_now:.2f}", f"{vix_now - vix_prev:+.2f}")
                    with mc2:
                        st.metric(f"IVP（{ivp_window}日）", f"{ivp_now:.1f}%" if pd.notna(ivp_now) else "N/A")
                    with mc3:
                        st.metric("狀態", state_label)

                    st.caption(f"IVP（IV Percentile）＝今日 VIX 高於過去 {ivp_window} 個交易日中多少比例的天數。只看 VIX 絕對值不足：VIX 低但 IVP 極高＝結構性低波環境下的極度擠壓（溫水煮青蛙），歷史上常是風暴前夕。短視窗反映短線擠壓、長視窗反映年度相對位置，兩者可互相對照。")

                    vix_chart_df = pd.DataFrame({
                        "VIX 收盤": vix_view,
                        "恐慌線 (30)": 30,
                    })
                    st.line_chart(vix_chart_df)

                    ivp_chart_df = pd.DataFrame({
                        f"IVP ({ivp_window}日)": ivp_view,
                        "極端高位 (95)": 95,
                        "相對高位 (80)": 80,
                        "相對低位 (20)": 20,
                    })
                    st.line_chart(ivp_chart_df)
            else:
                chart_df = pd.DataFrame({"現價": plot_data})
                if sel == "JPY=X":
                    ma60 = plot_data.rolling(60).mean()
                    chart_df["動態適應基準 (DAT)"] = ma60 * 1.05
                st.line_chart(chart_df)

SENTI_PANIC_COLOR = "#1e88e5"   # 恐慌端：藍
SENTI_GREED_COLOR = "#e53935"   # 過熱端：紅


def _sentiment_line_chart(key, series, start, end, panic_eps, greed_eps):
    """單一情緒指標折線圖：底色＝恐慌／過熱區、虛線＝門檻、直條＝三指標共振期間。"""
    rule = ed.SENTIMENT_RULES[key]
    panic_th = float(rule["panic"][1])
    greed_th = float(rule["greed"][1])
    view = series[(series.index >= start) & (series.index <= end)].dropna()
    if view.empty:
        return None
    if key == "fear_greed":
        lo, hi = 0.0, 100.0
    else:
        span = max(float(view.max()), panic_th, greed_th) - min(float(view.min()), panic_th, greed_th)
        pad = span * 0.08
        lo = min(float(view.min()), panic_th, greed_th) - pad
        hi = max(float(view.max()), panic_th, greed_th) + pad
    y_scale = alt.Scale(domain=[lo, hi], nice=False)
    x_scale = alt.Scale(domain=[start.to_pydatetime(), end.to_pydatetime()])
    # 跨年時只顯示月份會分不出是哪一年，超過 400 天改成「年-月」。
    x_axis = alt.Axis(format="%Y-%m", labelAngle=0) if (end - start).days > 400 else alt.Axis(labelAngle=0)

    # 恐慌區在數值低端（貪婪指數）或高端（PCR、VIX），依規則方向決定色帶範圍。
    panic_low = rule["panic"][0] in ("<", "<=")
    bands = pd.DataFrame([
        {"y": lo if panic_low else panic_th, "y2": panic_th if panic_low else hi, "c": SENTI_PANIC_COLOR},
        {"y": greed_th if panic_low else lo, "y2": hi if panic_low else greed_th, "c": SENTI_GREED_COLOR},
    ])
    band_layer = alt.Chart(bands).mark_rect(opacity=0.10).encode(
        y=alt.Y("y:Q", scale=y_scale), y2="y2:Q", color=alt.Color("c:N", scale=None),
    )
    rules = pd.DataFrame([{"v": panic_th, "c": SENTI_PANIC_COLOR}, {"v": greed_th, "c": SENTI_GREED_COLOR}])
    rule_layer = alt.Chart(rules).mark_rule(strokeDash=[4, 3], strokeWidth=1.2).encode(
        y=alt.Y("v:Q", scale=y_scale), color=alt.Color("c:N", scale=None),
    )

    eps = [dict(e, c=SENTI_PANIC_COLOR) for e in panic_eps] + [dict(e, c=SENTI_GREED_COLOR) for e in greed_eps]
    layers = [band_layer]
    if eps:
        ep = pd.DataFrame(eps)
        ep["x"] = pd.to_datetime(ep["起"])
        ep["x2"] = pd.to_datetime(ep["迄"]) + pd.Timedelta(days=1)  # 單日事件也要有寬度
        ep = ep[(ep["x2"] >= start) & (ep["x"] <= end)]
        if not ep.empty:
            layers.append(alt.Chart(ep).mark_rect(opacity=0.28).encode(
                x=alt.X("x:T", scale=x_scale), x2="x2:T", color=alt.Color("c:N", scale=None),
                tooltip=[alt.Tooltip("起:N", title="共振起"), alt.Tooltip("迄:N", title="共振迄"), alt.Tooltip("天數:Q")],
            ))

    df = view.rename("v").rename_axis("date").reset_index()
    df["zone"] = df["v"].map(lambda v: ed.classify_sentiment(key, v))
    fmt = ".1f" if key == "fear_greed" else (".3f" if key == "pcr5" else ".2f")
    line = alt.Chart(df).mark_line(color="#90a4ae", strokeWidth=1.6).encode(
        x=alt.X("date:T", title=None, scale=x_scale, axis=x_axis),
        y=alt.Y("v:Q", title=None, scale=y_scale, axis=alt.Axis(minExtent=55)),  # 圖上方已有指標名稱，不重複
        tooltip=[alt.Tooltip("date:T", title="日期"), alt.Tooltip("v:Q", title=str(rule["label"]), format=fmt)],
    )
    # 落在恐慌／過熱區的日子加上彩色點，一眼看出哪段時間踩進極端區。
    pts = alt.Chart(df[df["zone"].isin([ed.ZONE_PANIC, ed.ZONE_GREED])]).mark_circle(size=22, opacity=0.9).encode(
        x=alt.X("date:T", scale=x_scale), y=alt.Y("v:Q", scale=y_scale),
        color=alt.Color("zone:N", scale=alt.Scale(domain=[ed.ZONE_PANIC, ed.ZONE_GREED],
                                                   range=[SENTI_PANIC_COLOR, SENTI_GREED_COLOR]), legend=None),
        tooltip=[alt.Tooltip("date:T", title="日期"), alt.Tooltip("v:Q", title=str(rule["label"]), format=fmt)],
    )
    return alt.layer(*layers, rule_layer, line, pts).properties(height=190)


RADAR_REF_COLORS = ["#ffb74d", "#ba68c8"]  # 參考線（均線、滾動 P90）配色


def _radar_history_chart(metric, start, end, value_format=".2f"):
    """黑天鵝雷達單一指標走勢：灰線＝指標、橘虛線＝參考線、紅虛線＝固定門檻、紅點＝當天達紅燈條件。"""
    hist = getattr(metric, "history", None)
    if hist is None or hist.empty:
        return None
    view = hist[(hist.index >= start) & (hist.index <= end)]
    if view["value"].dropna().empty:
        return None
    start = max(start, view.index[0])
    x_scale = alt.Scale(domain=[start.to_pydatetime(), end.to_pydatetime()])
    x_axis = alt.Axis(format="%Y-%m", labelAngle=0) if (end - start).days > 400 else alt.Axis(labelAngle=0)
    refs = [c for c in view.columns if c not in ("value", "danger")]
    lo_vals = [view["value"].min()] + [view[c].min() for c in refs]
    hi_vals = [view["value"].max()] + [view[c].max() for c in refs]
    if metric.threshold is not None:
        lo_vals.append(metric.threshold)
        hi_vals.append(metric.threshold)
    lo, hi = float(np.nanmin(lo_vals)), float(np.nanmax(hi_vals))
    pad = (hi - lo) * 0.08 or abs(hi) * 0.05 or 1.0
    y_scale = alt.Scale(domain=[lo - pad, hi + pad], nice=False)

    df = view.rename_axis("date").reset_index()
    layers = []
    if metric.threshold is not None:
        layers.append(alt.Chart(pd.DataFrame({"v": [metric.threshold]})).mark_rule(
            color=SENTI_GREED_COLOR, strokeDash=[4, 3], strokeWidth=1.2).encode(y=alt.Y("v:Q", scale=y_scale)))
    for i, col in enumerate(refs):
        layers.append(alt.Chart(df[["date", col]].dropna()).mark_line(
            color=RADAR_REF_COLORS[i % len(RADAR_REF_COLORS)], strokeDash=[5, 3], strokeWidth=1.2).encode(
            x=alt.X("date:T", scale=x_scale), y=alt.Y(f"{col}:Q", scale=y_scale),
            tooltip=[alt.Tooltip("date:T", title="日期"), alt.Tooltip(f"{col}:Q", format=value_format)]))
    layers.append(alt.Chart(df).mark_line(color="#90a4ae", strokeWidth=1.6).encode(
        x=alt.X("date:T", title=None, scale=x_scale, axis=x_axis),
        y=alt.Y("value:Q", title=None, scale=y_scale, axis=alt.Axis(minExtent=45)),
        tooltip=[alt.Tooltip("date:T", title="日期"), alt.Tooltip("value:Q", title=metric.name, format=value_format)]))
    danger_df = df[df["danger"]]
    if not danger_df.empty:
        layers.append(alt.Chart(danger_df).mark_circle(size=20, color=SENTI_GREED_COLOR, opacity=0.9).encode(
            x=alt.X("date:T", scale=x_scale), y=alt.Y("value:Q", scale=y_scale),
            tooltip=[alt.Tooltip("date:T", title="日期"), alt.Tooltip("value:Q", title=metric.name, format=value_format)]))
    return alt.layer(*layers).properties(height=150)


def _show_radar_chart(metric, start, end, value_format=".2f"):
    chart = _radar_history_chart(metric, start, end, value_format)
    if chart is not None:
        st.altair_chart(chart, use_container_width=True)
    elif metric.available:
        st.caption("⚫ 歷史資料不足，無法畫走勢。")


def _render_sentiment_block():
    """情緒雙端溫度計（恐慌悲觀 ↔ 樂觀過熱）。"""
    st.divider()
    st.markdown("### 🌡️ 情緒雙端溫度計：恐慌悲觀 ↔ 樂觀過熱")
    st.caption("獨立區塊，不併入上方四支柱計分。三個指標各自落在「恐慌端／中性／過熱端」，三個同時落在同一端才稱為共振。")
    with st.spinner("同步 CNN 恐懼貪婪指數與 VIX…"):
        senti = fetch_sentiment_extremes_block()

    zone_badge = {
        ed.ZONE_PANIC: "🔵 恐慌端",
        ed.ZONE_GREED: "🔴 過熱端",
        ed.ZONE_NEUTRAL: "⚪ 中性",
        ed.ZONE_NA: "⚫ N/A",
    }
    rng = st.radio("期間", ["近 6 個月", "近 1 年", "近 3 年", "全部"], index=1, horizontal=True, key="senti_range")
    series_map = senti.get("series", {})
    ends = [ser.index[-1] for ser in series_map.values() if ser is not None and len(ser)]
    end_day = max(ends) if ends else pd.Timestamp.today().normalize()
    start_day = end_day - pd.Timedelta(days={"近 6 個月": 182, "近 1 年": 365, "近 3 年": 1095, "全部": 100000}[rng])
    st.caption("底色：🔵 恐慌區、🔴 過熱區；虛線＝門檻；彩色點＝當天落在極端區；深色直條＝三指標同時共振的期間。")

    for item in senti["readings"]:
        fmt = ed.SENTIMENT_RULES[item.key]["fmt"]
        value_text = fmt.format(item.value) if item.available else "N/A"
        st.markdown(f"**{item.label}**　`{value_text}`　{zone_badge[item.zone]}")
        st.caption(
            f"恐慌端 {ed.rule_text(item.key, 'panic')}｜過熱端 {ed.rule_text(item.key, 'greed')}"
            f"｜截至 {item.as_of or 'N/A'}｜{item.detail}"
        )
        ser = series_map.get(item.key)
        chart = None
        if ser is not None and len(ser):
            chart = _sentiment_line_chart(item.key, ser, max(start_day, ser.index[0]), end_day,
                                          senti["panic_episodes"], senti["greed_episodes"])
        if chart is not None:
            st.altair_chart(chart, use_container_width=True)
        else:
            st.caption("⚫ 沒有歷史資料可畫圖。")

    for err in senti.get("errors", []):
        st.caption(f"⚠️ {err}（該指標顯示 N/A，不以估值代替）")

    verdict = senti["verdict"]
    count_text = f"恐慌端 {senti['panic']}/3、過熱端 {senti['greed']}/3"
    if verdict == "insufficient":
        st.warning(f"⚠️ **資料不足：只有 {senti['available']}/3 個指標可用**，不產生共振結論。")
    elif verdict == "panic_resonance":
        st.info(f"😱 **恐慌悲觀共振：三個指標同時落在恐慌端。**（{count_text}）市場情緒已到極度悲觀，歷史上屬於少見的恐慌區；這是情緒描述，不是買進訊號。")
    elif verdict == "greed_resonance":
        st.error(f"🔥 **樂觀過熱共振：三個指標同時落在過熱端。**（{count_text}）市場情緒極度樂觀、避險需求極低；這是情緒描述，不是賣出訊號。")
    elif verdict == "mixed":
        st.warning(f"🔀 **訊號分歧：恐慌與過熱同時出現。**（{count_text}）指標彼此矛盾，暫不解讀。")
    elif verdict == "leaning_panic":
        st.info(f"↘️ **偏恐慌，未共振。**（{count_text}）")
    elif verdict == "leaning_greed":
        st.warning(f"↗️ **偏過熱，未共振。**（{count_text}）")
    else:
        st.success(f"⚪ **情緒中性。**（{count_text}）")

    with st.expander("📜 歷史共振紀錄與口徑說明"):
        if senti["history_start"]:
            st.caption(f"歷史比對期間：{senti['history_start']} ～ {senti['history_end']}，共 {senti['history_days']} 個三指標皆有資料的交易日（CNN 端點最早只提供到 2021 年）。")
        h1, h2 = st.columns(2)
        with h1:
            st.markdown("**😱 恐慌悲觀共振**")
            if senti["panic_episodes"]:
                st.dataframe(pd.DataFrame(senti["panic_episodes"]), hide_index=True, width="stretch")
            else:
                st.caption("期間內未出現。")
        with h2:
            st.markdown("**🔥 樂觀過熱共振**")
            if senti["greed_episodes"]:
                st.dataframe(pd.DataFrame(senti["greed_episodes"]), hide_index=True, width="stretch")
            else:
                st.caption("期間內未出現。")
        st.caption(
            "口徑：恐慌端三條沿用刀神期權學院影片（貪婪指數個位數、PCR 五日平均 ≥0.9、VIX 超過 40）。"
            "過熱端依 2021 起實測分布自訂：CNN 指數 2021 起最高只到 83，因此用 CNN 官方「極度貪婪」分界 75；"
            "PCR ≤0.70、VIX <14；三者同時成立的罕見程度與恐慌端相當（更嚴的 ≤0.62／<13 在 2021 起從未同時成立，等於永不亮燈）。"
        )
        st.caption(
            "⚠️ 卡片上的貪婪指數是 CNN 即時分數（網站顯示值）；歷史紀錄用的是 CNN 每日歷史值，兩者偶有落差"
            "（例：2026-11-20 網站一度顯示 9.7，但歷史值記為 18.6，所以該日不計入恐慌共振）。VIX 一律用收盤，不用盤中最高。"
        )
        st.caption("事件數極少（2021 起恐慌共振只有一段），不足以做統計推論；要當進出場訊號前須先開概念測試單。")



# --- Tab 7: 🚨 極端背離雷達 (原 Tab 7) ---
with t_crash:
    st.error("## 🚨 黑天鵝雷達：系統性反轉與流動性枯竭預警")
    st.caption("全自動宏觀風險控制台：資料失敗時顯示 N/A 並退出計分，不使用人工預設值代替真實資料。")
    st.divider()

    with st.spinner("同步 CFTC、波動期限結構與市場廣度…"):
        cftc_metric = fetch_cftc_radar_metric()
        volatility_metric, equal_weight_metric = fetch_market_proxy_radar_metrics()
        sp500_breadth_metric = fetch_sp500_breadth_radar_metric()

    sox_metric = ed.unavailable_metric("SOX RSI", "費半指數價格不足")
    if '^SOX' in raw_df.columns:
        # 只用真實交易日：raw_df 是多資產聯集日曆（含 24 小時交易的 BTC），ffill 會把休市日填成平盤列，
        # 壓低 RSI、把 252 列 Sharpe 縮成約 8 個月（2026-11-25 實測 SOX RSI 29.3 vs 39.8）。
        sox_data = raw_df['^SOX'].dropna()
        if not sox_data.empty:
            sox_rsi_val = round(calculate_rsi(sox_data).iloc[-1], 2)
            if pd.notna(sox_rsi_val):
                sox_rsi_series = calculate_rsi(sox_data)
                sox_metric = ed.RadarMetric(
                    name="SOX RSI",
                    available=True,
                    danger=bool(sox_rsi_val > 86),
                    value=float(sox_rsi_val),
                    as_of=pd.Timestamp(sox_data.index[-1]).strftime("%Y-%m-%d"),
                    status="極端超買" if sox_rsi_val > 86 else "正常",
                    detail="14 日 RSI（簡單移動平均口徑）",
                    history=pd.DataFrame({"value": sox_rsi_series, "danger": sox_rsi_series > 86}).dropna(subset=["value"]),
                    threshold=86.0,
                )

    sharpe_metric = ed.unavailable_metric("QQQ Sharpe", "QQQ 價格不足")
    if 'QQQ' in raw_df.columns:
        qqq_data = raw_df['QQQ'].dropna()  # 同上，只用真實交易日
        if not qqq_data.empty:
            ndx_sharpe_val = round(calculate_sharpe(qqq_data), 2)
            if pd.notna(ndx_sharpe_val):
                _qqq_ret = qqq_data.pct_change()
                qqq_sharpe_series = (_qqq_ret.rolling(252).mean() / _qqq_ret.rolling(252).std()) * np.sqrt(252)
                sharpe_metric = ed.RadarMetric(
                    name="QQQ Sharpe",
                    available=True,
                    danger=bool(ndx_sharpe_val >= 1.6),
                    value=float(ndx_sharpe_val),
                    as_of=pd.Timestamp(qqq_data.index[-1]).strftime("%Y-%m-%d"),
                    status="報酬動能極端擁擠" if ndx_sharpe_val >= 1.6 else "正常",
                    detail="近 252 交易日、無風險利率設為 0",
                    history=pd.DataFrame({"value": qqq_sharpe_series, "danger": qqq_sharpe_series >= 1.6}).dropna(subset=["value"]),
                    threshold=1.6,
                )

    radar_rng = st.radio("走勢期間", ["近 6 個月", "近 1 年", "近 3 年", "全部"], index=1, horizontal=True, key="radar_range")
    radar_end = pd.Timestamp.today().normalize()
    radar_start = radar_end - pd.Timedelta(days={"近 6 個月": 182, "近 1 年": 365, "近 3 年": 1095, "全部": 100000}[radar_rng])
    st.caption("走勢圖：灰線＝指標、紅虛線＝紅燈門檻、橘／紫虛線＝參考線（均線、滾動 P90）、紅點＝當天達紅燈條件。")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("#### 📈 價格與動能極端值")
        st.metric(
            "SOX (費半) RSI",
            f"{sox_metric.value:.1f}" if sox_metric.available else "N/A",
            delta=f"{sox_metric.value - 50:+.1f}" if sox_metric.available else None,
            delta_color="inverse",
        )
        st.caption(f"{sox_metric.status}｜{sox_metric.detail}｜截至 {sox_metric.as_of or 'N/A'}")
        _show_radar_chart(sox_metric, radar_start, radar_end, ".1f")

        st.metric(
            "QQQ Sharpe",
            f"{sharpe_metric.value:.2f}x" if sharpe_metric.available else "N/A",
            delta=f"{sharpe_metric.value - 1.0:+.2f}" if sharpe_metric.available else None,
            delta_color="inverse",
        )
        st.caption(f"{sharpe_metric.status}｜{sharpe_metric.detail}｜截至 {sharpe_metric.as_of or 'N/A'}")
        _show_radar_chart(sharpe_metric, radar_start, radar_end, ".2f")

    with c2:
        st.markdown("#### 🏦 部位與波動壓力")
        st.metric(
            "CFTC 機構淨曝險／OI",
            f"{cftc_metric.value:.1f}%" if cftc_metric.available else "N/A",
            delta=f"近五年 P{cftc_metric.percentile:.0f}" if cftc_metric.available else None,
            delta_color="inverse",
        )
        st.caption(f"{cftc_metric.status}｜{cftc_metric.detail}｜截至 {cftc_metric.as_of or 'N/A'}")
        _show_radar_chart(cftc_metric, radar_start, radar_end, ".1f")

        st.metric(
            "VIX／VIX3M",
            f"{volatility_metric.value:.3f}x" if volatility_metric.available else "N/A",
            delta=f"近兩年 P{volatility_metric.percentile:.0f}" if volatility_metric.available else None,
            delta_color="inverse",
        )
        st.caption(f"{volatility_metric.status}｜{volatility_metric.detail}｜截至 {volatility_metric.as_of or 'N/A'}")
        _show_radar_chart(volatility_metric, radar_start, radar_end, ".3f")

    with c3:
        st.markdown("#### 📉 結構與廣度失衡")
        st.metric(
            "RSP／SPY 等權廣度",
            f"{equal_weight_metric.value:.3f}x" if equal_weight_metric.available else "N/A",
            delta=f"近兩年 P{equal_weight_metric.percentile:.0f}" if equal_weight_metric.available else None,
            delta_color="inverse",
        )
        st.caption(f"{equal_weight_metric.status}｜{equal_weight_metric.detail}｜截至 {equal_weight_metric.as_of or 'N/A'}")
        _show_radar_chart(equal_weight_metric, radar_start, radar_end, ".3f")

        st.metric(
            "S&P 500 成分股高於年線",
            f"{sp500_breadth_metric.value:.1f}%" if sp500_breadth_metric.available else "N/A",
            delta=(
                f"涵蓋 {sp500_breadth_metric.coverage:.0%}"
                if sp500_breadth_metric.coverage is not None
                else None
            ),
            delta_color="inverse",
        )
        st.caption(f"{sp500_breadth_metric.status}｜{sp500_breadth_metric.detail}｜價格截至 {sp500_breadth_metric.as_of or 'N/A'}")
        _show_radar_chart(sp500_breadth_metric, radar_start, radar_end, ".1f")
        st.caption("註：逐日廣度用的是「目前」的成分股回算，越往前倖存者偏差越大，只供看趨勢。")

    st.divider()
    st.markdown("### 📝 四支柱風險判讀")
    risk_summary = ed.summarize_risk_pillars(
        [sox_metric, sharpe_metric],
        cftc_metric,
        volatility_metric,
        [equal_weight_metric, sp500_breadth_metric],
    )
    pillar_text = " ｜ ".join(
        f"{'🔴' if danger else '🟢' if available else '⚪'} {name}"
        for name, available, danger in risk_summary["pillars"]
    )
    st.caption(f"{pillar_text}｜有效支柱 {risk_summary['available']}/4；同一支柱的相關指標最多只計一次。")

    danger_count = int(risk_summary["danger"])
    if risk_summary["insufficient"]:
        st.warning(f"⚠️ **資料不足：目前只有 {risk_summary['available']}/4 個支柱可用。** 不產生安全或紅色警戒結論，請先排除標示為 N/A 的資料源。")
    elif danger_count >= 3:
        st.error(f"🚨 **紅色警戒：4 大風險支柱中有 {danger_count} 項亮紅燈。** 動能、部位、波動與廣度已有多面向共振，應提高防禦並降低新增風險。")
    elif danger_count >= 2:
        st.warning(f"⚠️ **中度戒備：4 大風險支柱中有 {danger_count} 項亮紅燈。** 暫停擴張風險，等待期限結構或市場廣度改善。")
    else:
        st.info(f"✅ **未形成多面向共振：目前有 {danger_count} 個風險支柱亮紅燈。** 這只代表雷達條件未同時成立，不等同保證市場安全。")

    # --- 情緒雙端溫度計（獨立區塊，不參與上方四支柱計分）---
    try:
        _render_sentiment_block()
    except Exception as _senti_exc:  # noqa: BLE001 — 本區塊出錯不得連帶讓後面分頁停止渲染
        st.warning(f"⚠️ 情緒雙端溫度計暫時無法顯示（{type(_senti_exc).__name__}），其他區塊不受影響。")

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

# --- Tab: 🌡️ 股民溫度計（PTT Stock 版盤中／盤後閒聊情緒）---
@st.cache_data(ttl=900, show_spinner=False)
def load_ptt_thermometer():
    """讀已提交的每日情緒歷史，再即時補抓 PTT 上更新的閒聊串（失敗就只用歷史）。"""
    daily, words, quotes = ptt_th.load_history()
    note = ""
    if not daily.empty:
        last_day = daily["date"].max().date()
        try:
            live_d, live_w, live_q = ptt_th.fetch_live(last_day)
        except Exception as exc:  # 部署環境連不到 PTT 時退回歷史資料
            live_d, live_w, live_q = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
            note = f"即時補抓失敗（{type(exc).__name__}），以下只顯示已存的歷史。"
        if not live_d.empty:
            daily = pd.concat([daily, live_d], ignore_index=True)
            words = pd.concat([words, live_w], ignore_index=True)
            quotes = pd.concat([quotes, live_q], ignore_index=True)
        daily = ptt_th.add_temperature(daily)
    return daily, words, quotes, note


with t_ptt:
    st.subheader("🌡️ 股民溫度計：PTT 股版散戶現在多樂觀、多悲觀")
    st.caption(
        "資料：PTT Stock 版每日「盤中閒聊」＋「盤後閒聊」全部推文，用台股黑話詞典判斷每則推文偏多或偏空。"
        "溫度＝當天的多空淨分數，在這一天以前所有歷史裡排第幾（0＝史上最悲觀，100＝最樂觀）。紅＝樂觀、綠＝悲觀。"
    )
    with st.spinner("讀取 PTT 情緒資料…"):
        ptt_daily, ptt_words, ptt_quotes, ptt_note = load_ptt_thermometer()
    if ptt_note:
        st.info(ptt_note)
    ptt_valid = ptt_daily.dropna(subset=["temp"]) if not ptt_daily.empty else ptt_daily
    if ptt_valid.empty:
        st.warning("PTT 情緒歷史尚未建立或天數不足（至少需要 120 個交易日）。")
    else:
        latest = ptt_valid.iloc[-1]
        latest_day = latest["date"]
        z_label, z_color = ptt_th.zone(latest["temp"])
        z5_label, _ = ptt_th.zone(latest["temp5"])
        live_flag = "（含今日即時資料，盤中會變動）" if bool(latest.get("live", False)) else ""
        st.markdown(
            f"<div style='font-size:1.1rem'>資料日：<b>{latest_day:%Y-%m-%d}</b>{live_flag}　"
            f"今日情緒：<span style='color:{z_color};font-size:1.6rem;font-weight:700'>{z_label}</span></div>",
            unsafe_allow_html=True,
        )
        st.progress(min(1.0, max(0.0, float(latest["temp"]) / 100)))
        st.caption("0 極度悲觀 ─ 10 悲觀 ─ 30 中性 ─ 70 樂觀 ─ 90 極度樂觀 ─ 100")

        prev = ptt_valid.iloc[-2] if len(ptt_valid) > 1 else latest
        pc1, pc2, pc3, pc4 = st.columns(4)
        pc1.metric("今日溫度", f"{latest['temp']:.0f}", f"{latest['temp'] - prev['temp']:+.0f}（較前一日）", delta_color="inverse")
        pc2.metric("近 5 日溫度", f"{latest['temp5']:.0f}", z5_label, delta_color="off", delta_arrow="off")
        pc3.metric("恐慌推文占比", f"{latest['fear_share']:.1%}", f"貪婪 {latest['greed_share']:.1%}", delta_color="off", delta_arrow="off")
        heat = latest.get("heat")
        pc4.metric("討論熱度", f"{int(latest['n_push']):,} 則推文",
                   f"{heat:.1f} 倍於近 60 日中位" if pd.notna(heat) else "—", delta_color="off", delta_arrow="off")

        st.divider()
        rng = st.radio("期間", ["近 6 個月", "近 1 年", "近 3 年", "全部"], index=1, horizontal=True, key="ptt_range")
        span = {"近 6 個月": 182, "近 1 年": 365, "近 3 年": 1095, "全部": 100000}[rng]
        start = latest_day - pd.Timedelta(days=span)
        view = ptt_valid[ptt_valid["date"] >= start].copy()
        twii_view = twii_hist_df[twii_hist_df.index >= start].rename("加權指數").reset_index()
        twii_view.columns = ["date", "加權指數"]

        bands = pd.DataFrame([
            {"lo": lo, "hi": (ptt_th.ZONES[i + 1][0] if i + 1 < len(ptt_th.ZONES) else 100), "區間": lab, "color": col}
            for i, (lo, lab, col) in enumerate(ptt_th.ZONES)
        ])
        x_scale = alt.Scale(domain=[start.to_pydatetime(), latest_day.to_pydatetime()])
        # y 軸標題預設轉 90 度直排，中文要歪頭看；改成橫排放在軸線上方（titleX 對齊 minExtent 的左緣）。
        flat_title = dict(minExtent=55, titleAngle=0, titleAlign="left", titleBaseline="bottom", titleX=-55, titleY=-8)
        band_layer = alt.Chart(bands).mark_rect(opacity=0.10).encode(
            y=alt.Y("lo:Q", scale=alt.Scale(domain=[0, 100])), y2="hi:Q",
            color=alt.Color("color:N", scale=None),
        )
        temp_line = alt.Chart(view).mark_line(color="#455a64", strokeWidth=1.8).encode(
            x=alt.X("date:T", title=None, scale=x_scale),
            y=alt.Y("temp5:Q", title="近 5 日溫度", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(**flat_title)),
            tooltip=[alt.Tooltip("date:T", title="日期"), alt.Tooltip("temp5:Q", title="5 日溫度", format=".0f"),
                     alt.Tooltip("temp:Q", title="當日溫度", format=".0f"), alt.Tooltip("n_push:Q", title="推文數", format=",")],
        )
        temp_pts = alt.Chart(view).mark_circle(size=18, opacity=0.35).encode(
            x="date:T", y="temp:Q",
            color=alt.Color("temp:Q", scale=alt.Scale(domain=[0, 50, 100], range=["#1b7f3b", "#bdbdbd", "#c62828"]), legend=None),
        )
        twii_line = alt.Chart(twii_view).mark_line(color="#1565c0").encode(
            x=alt.X("date:T", title=None, scale=x_scale),
            y=alt.Y("加權指數:Q", scale=alt.Scale(zero=False), axis=alt.Axis(**flat_title)),
            tooltip=[alt.Tooltip("date:T", title="日期"), alt.Tooltip("加權指數:Q", format=",.0f")],
        )
        # 不用 vconcat：合併圖在容器寬度下會溢出約 2px，整頁出現橫向捲軸。改成兩張各自貼合寬度、共用 x 範圍與 y 軸寬度的圖。
        st.altair_chart((band_layer + temp_pts + temp_line).properties(height=260), use_container_width=True)
        st.altair_chart(twii_line.properties(height=160), use_container_width=True)
        st.caption("上圖：灰線＝近 5 日溫度，點＝當日溫度，背景色帶＝五個區間。下圖：加權指數。")

        fg = view.melt(id_vars="date", value_vars=["fear5", "greed5"], var_name="kind", value_name="share")
        fg["kind"] = fg["kind"].map({"fear5": "恐慌推文占比", "greed5": "貪婪推文占比"})
        st.altair_chart(
            alt.Chart(fg).mark_line().encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("share:Q", title="近 5 日占比", axis=alt.Axis(format="%", **flat_title)),
                color=alt.Color("kind:N", title=None, scale=alt.Scale(domain=["恐慌推文占比", "貪婪推文占比"], range=["#1b7f3b", "#c62828"])),
                tooltip=[alt.Tooltip("date:T", title="日期"), "kind:N", alt.Tooltip("share:Q", format=".1%")],
            ).properties(height=180),
            use_container_width=True,
        )
        st.caption("恐慌詞例：斷頭、畢業、救救我、跌停、崩盤；貪婪詞例：歐印、梭哈、財富自由、噴爆、起飛。")

        st.divider()
        st.markdown(f"#### 💬 {latest_day:%Y-%m-%d} 大家在說什麼")
        wc1, wc2 = st.columns([1, 1])
        day_words = ptt_words[ptt_words["date"] == latest_day] if not ptt_words.empty else pd.DataFrame()
        with wc1:
            if day_words.empty:
                st.caption("這天沒有情緒詞統計。")
            else:
                dw = day_words.assign(傾向=day_words["side"].map({"bull": "偏多", "bear": "偏空"}))
                st.altair_chart(
                    alt.Chart(dw).mark_bar().encode(
                        x=alt.X("count:Q", title="出現則數"),
                        y=alt.Y("word:N", sort="-x", title=None),
                        color=alt.Color("傾向:N", scale=alt.Scale(domain=["偏多", "偏空"], range=["#c62828", "#1b7f3b"])),
                        tooltip=["word:N", "傾向:N", "count:Q"],
                    ).properties(height=240),
                    use_container_width=True,
                )
        with wc2:
            day_q = ptt_quotes[ptt_quotes["date"] == latest_day] if not ptt_quotes.empty else pd.DataFrame()
            if day_q.empty:
                st.caption("這天沒有挑到代表推文。")
            else:
                for _, qr in day_q.iterrows():
                    icon = "🔥" if qr["kind"] == "greed" else "😱"
                    st.markdown(f"{icon} `{qr['time']}` {qr['text']}")
                st.caption("🔥＝含貪婪詞、😱＝含恐慌詞，每天隨機各挑最多 3 則（固定種子，重整不變）。")

        st.divider()
        st.markdown("#### 📜 歷史上最悲觀與最樂觀的日子")
        twii_ret = twii_hist_df.pct_change()
        ext = ptt_valid[["date", "temp", "net", "fear_share", "n_push"]].copy()
        ext["當日加權漲跌"] = ext["date"].map(twii_ret)
        fmt = lambda d: d.assign(  # noqa: E731
            日期=d["date"].dt.strftime("%Y-%m-%d"), 溫度=d["temp"].round(1), 多空淨分數=d["net"].round(3),
            恐慌占比=(d["fear_share"] * 100).round(1).astype(str) + "%",
            當日加權漲跌=(d["當日加權漲跌"] * 100).round(2).astype(str) + "%", 推文數=d["n_push"].astype(int),
        )[["日期", "溫度", "多空淨分數", "恐慌占比", "當日加權漲跌", "推文數"]]
        ec1, ec2 = st.columns(2)
        with ec1:
            st.markdown("**😱 最悲觀 10 天**")
            st.dataframe(fmt(ext.nsmallest(10, "net")), hide_index=True, use_container_width=True)
        with ec2:
            st.markdown("**🔥 最樂觀 10 天**")
            st.dataframe(fmt(ext.nlargest(10, "net")), hide_index=True, use_container_width=True)
        st.caption("依多空淨分數排序（全期）。只列當天的情緒與漲跌，不含之後的走勢。")

        with st.expander("方法、限制與預測力檢驗結果"):
            st.markdown(
                f"""
- **資料範圍**：{ptt_valid['date'].min():%Y-%m-%d} 起共 {len(ptt_valid):,} 個交易日有溫度（前 120 個交易日只當基準，不給溫度）。
- **一天的範圍**：該交易日 08:00 到下一個交易日 08:30 之間，當天盤中串與盤後串裡的推文。
- **判斷方式**：詞典比對（`ptt_sentiment/lexicon.py`，v1）。抓不到反諷與語境，例如「好棒棒又套牢了」會被判成偏空、「穩了」可能是反話。單日分數有雜訊，看 5 日溫度比較穩。
- **代表性**：只代表 PTT 股版族群，不是全體投資人。
- **討論熱度**：單一閒聊串的推文數有上限，多數日子落在 2,750～2,850 則，熱度只在特別熱的日子（多開串）才會明顯偏高。
- **預測力**：已檢驗，**沒有**（概念測試單 CT-20261122-03，2026-11-22 判定陣亡）。情緒分數跟當天漲跌高度同步（Spearman +0.52），扣掉過去 5／20 日漲跌後，對之後 5／20 日加權指數幾乎沒有關係（2020～2023 與 2023～2026 兩段都 |ρ|<0.03，方向還跟「反指標」相反）。本頁只用來感受散戶情緒，**不是買賣訊號**。
                """
            )
