"""股民溫度計每日更新（本機 Windows 排程，每天 08:45 經 run_daily_hidden.vbs 隱藏執行）。

一條龍：續抓 PTT 索引與閒聊串 → 重建每日情緒表 → 只提交三個溫度計 CSV → push。
push 後 Streamlit Cloud 自動重新部署，面板的歷史檔就跟上前一個交易日。

安全設計（這個 repo 也是人手改版的工作目錄）：
- 只用「指定路徑提交」（git commit -- 三個 CSV），不碰工作區其他檔案，也不 reset。
- 本機 main 若已有其他還沒推的 commit，只提交、不推送（避免把半成品一起推上部署版），記 log。
- 不在 main、或正在 merge／rebase 時整個略過 git 步驟。
- 內建看門狗：VBS 隱藏殼讓排程器的逾時殺不到 python，自己 25 分鐘後強制結束。
- 每個子行程都帶 CREATE_NO_WINDOW，不彈黑視窗。
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "data" / "ptt_raw" / "logs"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PY = sys.executable
CSVS = ["ptt_sentiment/daily_sentiment.csv", "ptt_sentiment/daily_top_words.csv", "ptt_sentiment/daily_quotes.csv"]
WATCHDOG_SEC = 25 * 60
AUTO_PREFIX = "chore: 股民溫度計每日資料更新"


def log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG_DIR / f"daily_{datetime.now():%Y-%m}.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_py(desc: str, args: list[str], timeout: int) -> bool:
    log(f"START: {desc}")
    try:
        r = subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, creationflags=NO_WINDOW)
    except Exception as e:  # noqa: BLE001
        log(f"  {desc} 例外：{e}")
        return False
    tail = " | ".join((r.stdout or "").strip().splitlines()[-3:])
    log(f"  {desc} exit={r.returncode} {tail}")
    if r.returncode != 0:
        log(f"  stderr：{(r.stderr or '').strip()[-400:]}")
    return r.returncode == 0


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300, creationflags=NO_WINDOW)


def publish() -> int:
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    gitdir = ROOT / ".git"
    if branch != "main" or any((gitdir / x).exists() for x in ("MERGE_HEAD", "rebase-merge", "rebase-apply")):
        log(f"  目前分支 {branch!r} 或有進行中的 merge／rebase，略過 git。")
        return 1
    if git("diff", "--quiet", "--", *CSVS).returncode == 0:
        log("  三個 CSV 沒有變化（非交易日或資料未更新），不提交。")
        return 0
    fetch = git("fetch", "origin")
    if fetch.returncode != 0:
        log(f"  fetch 失敗：{fetch.stderr.strip()[-200:]}")
    # 只算「不是本排程自己產生」的未推送 commit：前幾天因故只提交沒推送的自動 commit 可以一起推。
    subjects = [s for s in git("log", "--format=%s", "origin/main..HEAD").stdout.splitlines() if s.strip()]
    ahead = str(sum(not s.startswith(AUTO_PREFIX) for s in subjects))
    behind = git("rev-list", "--count", "HEAD..origin/main").stdout.strip()
    git("add", "--", *CSVS)
    c = git("commit", "-m", f"{AUTO_PREFIX} {datetime.now():%Y-%m-%d}（本機排程）", "--", *CSVS)
    if c.returncode != 0:
        log(f"  commit 失敗：{(c.stderr or c.stdout).strip()[-200:]}")
        return 1
    log(f"  commit：{c.stdout.strip().splitlines()[0]}")
    if ahead not in ("", "0"):
        log(f"  本機 main 另有 {ahead} 個非本排程的未推送 commit，為免把半成品推上部署版，本次只提交不推送。")
        return 1
    if behind not in ("", "0"):
        log(f"  遠端比本機多 {behind} 個 commit，不自動合併，本次只提交不推送。")
        return 1
    p = git("push", "origin", "main")
    log(f"  push：{'成功' if p.returncode == 0 else '失敗 ' + p.stderr.strip()[-200:]}")
    return 0 if p.returncode == 0 else 1


def main() -> int:
    threading.Timer(WATCHDOG_SEC, lambda: (log("看門狗逾時，強制結束"), os._exit(124))).start()
    log("=== 股民溫度計每日更新開始 ===")
    crawled = run_py("續抓 PTT", ["ptt_sentiment/crawl.py", "recent"], timeout=20 * 60)
    built = run_py("重建每日情緒表", ["ptt_sentiment/build_daily.py"], timeout=5 * 60)
    if not built:
        log("=== 結束（建表失敗，不提交）===")
        os._exit(1)
    if not crawled:
        log("  爬蟲有錯，但仍以已抓到的資料建表並提交。")
    rc = publish()
    log(f"=== 結束（rc={rc}）===")
    os._exit(rc)  # 立即結束，連同看門狗計時器


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
