# 1. 修正 Tab 2 的數據彙整 (解決 NameError)
if not df_king.empty:
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("監控檔數", f"{len(df_king)} 檔")
    # 確保變數名稱統一為 df_king
    strong_count = len(df_king[df_king['乖離率'] > 0])
    s2.metric("強勢佔比", f"{int(strong_count / len(df_king) * 100)}%" if len(df_king) > 0 else "0%")
    s3.metric("平均 Z-Score", round(df_king['Z-Score'].mean(), 2))

# 2. 修正 Tab 4 相對強度 (解決 None 問題)
if 'SPY' in raw_df.columns:
    bench_s = raw_df['SPY'].ffill().dropna()
    for t in comp_list:
        target_s = raw_df[t].ffill().dropna()
        # 強制對齊兩個資產的共同交易日期
        common = target_s.index.intersection(bench_s.index)
        if len(common) > 60:
            # 僅使用對齊後的數據進行計算
            t_price = target_s.loc[common]
            b_price = bench_s.loc[common]
            # ...進行計算...
