"""押し目・高値ブレイク銘柄スクリーナー - Streamlit メインアプリ。"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from nikkei225 import get_nikkei225_tickers, get_company_name
from data_fetcher import fetch_ohlcv
from indicators import add_all_indicators
from screener import score_ticker
from breakout_screener import score_breakout
from chart_skill1 import score_chart_skill1

# ─── ページ設定 ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="日経225 銘柄スクリーナー",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 日経225 銘柄スクリーナー")

tab_oshi, tab_break, tab_skill = st.tabs(["🔽 押し目買い銘柄", "🚀 高値ブレイク銘柄", "📖 チャートスキル1"])


# ════════════════════════════════════════
# 共通：チャート描画関数
# ════════════════════════════════════════

def draw_chart(df: pd.DataFrame, title: str):
    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        row_heights=[0.5, 0.15, 0.175, 0.175],
        vertical_spacing=0.03,
        subplot_titles=[title, "出来高", "RSI / RCI短期", "MACD"],
    )

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"], name="ローソク足",
        increasing_line_color="#ff4b4b", decreasing_line_color="#1f77b4",
    ), row=1, col=1)

    for ma, color, width in [("MA5", "#f5a623", 1), ("MA25", "#7ed321", 1.5), ("MA75", "#9013fe", 2)]:
        fig.add_trace(go.Scatter(
            x=df.index, y=df[ma], name=ma,
            line=dict(color=color, width=width), opacity=0.9,
        ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df.index, y=df["BB_UPPER2"], name="BB+2σ",
        line=dict(color="rgba(150,150,150,0.5)", width=1, dash="dot"), showlegend=False,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df["BB_LOWER2"], name="BB-2σ",
        line=dict(color="rgba(150,150,150,0.5)", width=1, dash="dot"),
        fill="tonexty", fillcolor="rgba(150,150,150,0.05)", showlegend=False,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df["BB_MID"], name="BB MID",
        line=dict(color="rgba(150,150,150,0.7)", width=1, dash="dash"),
    ), row=1, col=1)

    colors = ["#ff4b4b" if c >= o else "#1f77b4" for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(
        x=df.index, y=df["Volume"], name="出来高",
        marker_color=colors, opacity=0.7,
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df["VOL_MA"], name="VOL MA25",
        line=dict(color="orange", width=1.5),
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=df.index, y=df["RSI"], name="RSI",
        line=dict(color="#f5a623", width=1.5),
    ), row=3, col=1)
    for lvl, color in [(30, "green"), (50, "gray"), (70, "red")]:
        fig.add_hline(y=lvl, line_dash="dot", line_color=color, opacity=0.5, row=3, col=1)

    fig.add_trace(go.Scatter(
        x=df.index, y=df["RCI_SHORT"], name="RCI短期",
        line=dict(color="#4fc3f7", width=1.5),
    ), row=3, col=1)
    for lvl in [-80, 80]:
        fig.add_hline(y=lvl, line_dash="dot", line_color="purple", opacity=0.4, row=3, col=1)

    hist_colors = ["#ff4b4b" if v >= 0 else "#1f77b4" for v in df["MACD_HIST"]]
    fig.add_trace(go.Bar(
        x=df.index, y=df["MACD_HIST"], name="ヒストグラム",
        marker_color=hist_colors, opacity=0.6,
    ), row=4, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df["MACD"], name="MACD",
        line=dict(color="#f5a623", width=1.5),
    ), row=4, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df["MACD_SIGNAL"], name="シグナル",
        line=dict(color="#ff4b4b", width=1.5),
    ), row=4, col=1)
    fig.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.5, row=4, col=1)

    fig.update_layout(
        height=850,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        legend=dict(orientation="h", y=1.02, x=0),
        margin=dict(l=10, r=10, t=60, b=10),
    )
    return fig


def external_links(ticker: str) -> str:
    code = ticker.replace(".T", "")
    return (
        f"**外部チャート:** "
        f"[Yahoo!ファイナンス](https://finance.yahoo.co.jp/quote/{code}.T)　|　"
        f"[株探](https://kabutan.jp/stock/chart?code={code})　|　"
        f"[みんかぶ](https://minkabu.jp/stock/{code}/chart)"
    )


def run_scan(mode: str, min_score: int, period: str, max_stocks: int,
             require_ma: bool, require_zone: bool, require_volume: bool):
    """スキャン実行（押し目・ブレイク共通）。mode='oshi' or 'break'"""
    tickers = get_nikkei225_tickers()[:max_stocks]
    total = len(tickers)
    progress_bar = st.progress(0, text="データ取得中...")
    status_text = st.empty()
    results = []

    for i, ticker in enumerate(tickers):
        name = get_company_name(ticker)
        status_text.text(f"処理中: {name}（{ticker}） [{i+1}/{total}]")
        progress_bar.progress((i + 1) / total)

        df = fetch_ohlcv(ticker, period=period)
        if df is None:
            continue
        df = add_all_indicators(df)

        if mode == "oshi":
            result = score_ticker(df)
        else:
            result = score_breakout(df)

        if result["score"] < min_score:
            continue
        if require_ma and not result["ma_alignment"]["pass"]:
            continue
        if mode == "oshi" and require_zone and not result["pullback_zone"]["pass"]:
            continue
        if mode == "break" and require_zone and not result["near_high"]["pass"]:
            continue
        if mode == "oshi" and require_volume and not result.get("volume_ok", False):
            continue
        if mode == "break" and require_volume and not result["breakout_volume"]["pass"]:
            continue

        last = df.iloc[-1]
        entry = {
            "ticker": ticker,
            "name": name,
            "score": result["score"],
            "close": last["Close"],
            "MA5": last.get("MA5"),
            "MA25": last.get("MA25"),
            "RSI": last.get("RSI"),
            "summary": result["summary"],
            "_df": df,
            "_result": result,
        }
        results.append(entry)

    progress_bar.empty()
    status_text.empty()
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ════════════════════════════════════════
# タブ1: 押し目買い銘柄
# ════════════════════════════════════════

with tab_oshi:
    st.markdown("上昇トレンド中の銘柄から、押し目買いの好機を自動スクリーニングします。")

    with st.sidebar:
        st.header("⚙️ 押し目スクリーニング設定")
        min_score_o = st.slider("最低スコア（押し目）", 0, 100, 50, 5, key="oshi_score")
        period_o = st.selectbox("データ取得期間（押し目）", ["3mo", "6mo", "1y"], index=1, key="oshi_period")
        max_stocks_o = st.slider("スキャン銘柄数（押し目）", 10, 225, 225, 10, key="oshi_stocks")
        require_ma_o = st.checkbox("MA上向き整列（必須）", value=True, key="oshi_ma")
        require_zone_o = st.checkbox("押し目ゾーン内（必須）", value=True, key="oshi_zone")
        require_vol_o = st.checkbox("出来高確認あり（押し目）", value=False, key="oshi_vol")

        st.divider()
        st.markdown("""
        **スコア内訳（押し目）**
        - トレンド確認: 30点
        - 押し目ゾーン: 20点
        - 下げ止まり×4: 各10点
        - 出来高: 10点
        - 全揃いボーナス: +10点
        """)

    if st.button("🔍 押し目スキャン開始", type="primary", use_container_width=True, key="oshi_scan"):
        results = run_scan("oshi", min_score_o, period_o, max_stocks_o,
                           require_ma_o, require_zone_o, require_vol_o)
        st.session_state["oshi_results"] = results
        if results:
            st.success(f"スキャン完了！ {len(results)}銘柄が条件を満たしました。")
        else:
            st.warning("条件に合致する銘柄が見つかりませんでした。")

    if st.session_state.get("oshi_results"):
        results = st.session_state["oshi_results"]
        st.subheader(f"📋 押し目銘柄一覧（{len(results)}件）")

        display_df = pd.DataFrame([{
            "スコア": r["score"],
            "コード": r["ticker"].replace(".T", ""),
            "銘柄名": r["name"],
            "現在値": f"¥{r['close']:,.0f}",
            "MA5": f"¥{r['MA5']:,.0f}" if r["MA5"] else "-",
            "MA25": f"¥{r['MA25']:,.0f}" if r["MA25"] else "-",
            "RSI": f"{r['RSI']:.1f}" if r["RSI"] else "-",
            "MA整列": "✅" if r["_result"]["ma_alignment"]["pass"] else "❌",
            "押し目帯": "✅" if r["_result"]["pullback_zone"]["pass"] else "❌",
            "反転数": f"{r['_result'].get('reversal_count', 0)}/4",
            "出来高": "✅" if r["_result"].get("volume_ok") else "❌",
            "コメント": r["summary"],
        } for r in results])

        st.dataframe(display_df, use_container_width=True, hide_index=True,
                     column_config={"スコア": st.column_config.ProgressColumn("スコア", min_value=0, max_value=100)})

        st.subheader("📊 詳細チャート（押し目）")
        opts = [f"{r['ticker'].replace('.T','')} - {r['name']} (スコア:{r['score']})" for r in results]
        sel = st.selectbox("銘柄を選択", opts, key="oshi_chart_sel")
        if sel:
            idx = opts.index(sel)
            r = results[idx]
            df = r["_df"]
            result = r["_result"]

            st.plotly_chart(draw_chart(df, f"{r['name']}（{r['ticker']}）"), use_container_width=True)

            st.subheader("📝 条件詳細（押し目）")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown("**① トレンド確認**")
                ma = result["ma_alignment"]
                st.write(f"{'✅' if ma['pass'] else '❌'} {ma['detail']}")
                hl = result["higher_lows"]
                st.write(f"{'✅' if hl['pass'] else '❌'} {hl['detail']}")
            with col2:
                st.markdown("**② 押し目ゾーン**")
                pz = result["pullback_zone"]
                st.write(f"{'✅' if pz['in_ma_zone'] else '❌'} MA5〜MA25ゾーン")
                st.write(f"{'✅' if pz['in_bb_zone'] else '❌'} BB MID〜-1σ圏")
                st.write(f"{'✅' if pz['in_fib_zone'] else '❌'} フィボナッチ38.2〜61.8%")
            with col3:
                st.markdown("**③ 下げ止まり + 出来高**")
                for key, label in [("reversal_candle", "ローソク足"), ("rsi", "RSI"),
                                    ("rci", "RCI"), ("macd", "MACD")]:
                    c = result[key]
                    st.write(f"{'✅' if c['pass'] else '❌'} {label}: {c['detail']}")
                vol = result["volume"]
                st.write(f"{'✅' if vol['pass'] else '❌'} 出来高: {vol['detail']}")

            if result["danger"]["has_danger"]:
                st.error(f"⚠️ 危険サイン: {result['danger']['detail']}")

            st.markdown(external_links(r["ticker"]))


# ════════════════════════════════════════
# タブ2: 高値ブレイク銘柄
# ════════════════════════════════════════

with tab_break:
    st.markdown("""
    **新高値ブレイク｜待ちぶせ型**エントリーチェックリストに基づき銘柄を抽出します。
    ブレイクを確認してから、ピボット付近への最初の押し目を待ち伏せするための候補リストです。
    """)

    with st.sidebar:
        st.divider()
        st.header("🚀 ブレイク銘柄スクリーニング設定")
        min_score_b = st.slider("最低スコア（ブレイク）", 0, 100, 50, 5, key="break_score")
        period_b = st.selectbox("データ取得期間（ブレイク）", ["3mo", "6mo", "1y"], index=1, key="break_period")
        max_stocks_b = st.slider("スキャン銘柄数（ブレイク）", 10, 225, 225, 10, key="break_stocks")
        require_ma_b = st.checkbox("MA上向き整列（必須）", value=True, key="break_ma")
        require_zone_b = st.checkbox("52週高値圏（必須）", value=True, key="break_zone")
        require_vol_b = st.checkbox("ブレイク出来高確認", value=True, key="break_vol")

        st.divider()
        st.markdown("""
        **スコア内訳（ブレイク）**
        - 52週高値圏: 25点
        - MA整列: 20点
        - ベース質: 15点
        - 出来高: 15点
        - 蓄積確認: 10点
        - 出来高枯れ: 10点
        - RR≥1.5: 5点
        - 全揃いボーナス: +5点
        """)

    if st.button("🔍 ブレイク銘柄スキャン開始", type="primary", use_container_width=True, key="break_scan"):
        results = run_scan("break", min_score_b, period_b, max_stocks_b,
                           require_ma_b, require_zone_b, require_vol_b)
        st.session_state["break_results"] = results
        if results:
            st.success(f"スキャン完了！ {len(results)}銘柄が条件を満たしました。")
        else:
            st.warning("条件に合致する銘柄が見つかりませんでした。")

    if st.session_state.get("break_results"):
        results = st.session_state["break_results"]
        st.subheader(f"📋 高値ブレイク候補一覧（{len(results)}件）")

        display_df = pd.DataFrame([{
            "スコア": r["score"],
            "コード": r["ticker"].replace(".T", ""),
            "銘柄名": r["name"],
            "現在値": f"¥{r['close']:,.0f}",
            "52週高値比": f"-{r['_result']['near_high']['pct_from_high']:.1f}%",
            "ピボット": f"¥{r['_result']['pivot']['pivot']:,.0f}",
            "高値更新": "✅" if r["_result"]["near_high"]["is_breakout"] else "—",
            "待ちぶせ帯": "✅" if r["_result"]["pivot"]["near_pivot"] else "❌",
            "出来高": f"{r['_result']['breakout_volume']['vol_ratio']:.1f}倍",
            "蓄積": "✅" if r["_result"]["accumulation"]["pass"] else "❌",
            "RR": f"{r['_result']['risk_reward']['rr']:.1f}",
            "コメント": r["summary"],
        } for r in results])

        st.dataframe(display_df, use_container_width=True, hide_index=True,
                     column_config={"スコア": st.column_config.ProgressColumn("スコア", min_value=0, max_value=100)})

        st.subheader("📊 詳細チャート（ブレイク）")
        opts = [f"{r['ticker'].replace('.T','')} - {r['name']} (スコア:{r['score']})" for r in results]
        sel = st.selectbox("銘柄を選択", opts, key="break_chart_sel")
        if sel:
            idx = opts.index(sel)
            r = results[idx]
            df = r["_df"]
            result = r["_result"]

            # ピボットラインをチャートに追加
            fig = draw_chart(df, f"{r['name']}（{r['ticker']}）")
            pivot_val = result["pivot"]["pivot"]
            fig.add_hline(
                y=pivot_val, line_dash="dash", line_color="yellow",
                annotation_text=f"ピボット ¥{pivot_val:,.0f}",
                annotation_position="top left", row=1, col=1,
            )
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("📝 チェックリスト詳細（待ちぶせ型）")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**STEP1: 形（パターン）**")
                nh = result["near_high"]
                st.write(f"{'✅' if nh['pass'] else '❌'} {nh['detail']}")
                ma = result["ma_alignment"]
                st.write(f"{'✅' if ma['pass'] else '❌'} {ma['detail']}")
                bq = result["base_quality"]
                st.write(f"{'✅' if bq['pass'] else '❌'} {bq['detail']}")
                pv = result["pivot"]
                st.write(f"{'✅' if pv['pass'] else '❌'} ピボット: {pv['detail']}")

            with col2:
                st.markdown("**STEP2: 質（出来高）**")
                bv = result["breakout_volume"]
                st.write(f"{'✅' if bv['pass'] else '❌'} {bv['detail']}")
                ac = result["accumulation"]
                st.write(f"{'✅' if ac['pass'] else '❌'} {ac['detail']}")
                vd = result["base_vol_dry"]
                st.write(f"{'✅' if vd['pass'] else '❌'} {vd['detail']}")

            with col3:
                st.markdown("**STEP4: リスクリワード**")
                rr = result["risk_reward"]
                st.write(f"{'✅' if rr['rr_ok'] else '❌'} {rr['detail']}")
                if pv["too_extended"]:
                    st.error("⚠️ ピボットから離れすぎ — 飛びつき厳禁")
                elif pv["near_pivot"]:
                    st.success("✅ 待ちぶせポイント圏内")

            st.info("""
            **STEP5 禁止事項（エントリー前に必ず確認）**
            - ギャップアップ・寄りへの飛びつきは禁止
            - ピボットから8%以上離れたら見送り
            - ナンピン（下げ局面での買い増し）は禁止
            - OCO（利確＋逆指値）を必ずセットで発注
            """)

            st.markdown(external_links(r["ticker"]))


# ════════════════════════════════════════
# タブ3: チャートスキル1
# ════════════════════════════════════════

with tab_skill:
    st.markdown("""
    **チャートスキル1** に収録された6つの技法で銘柄をスクリーニングします。
    N大（ものわかれ）・下半身・逆くちばし・7の法則・前高値ブレイク・キリ値節目を複合評価します。
    """)

    with st.sidebar:
        st.divider()
        st.header("📖 チャートスキル1 設定")
        min_score_s = st.slider("最低スコア（スキル1）", 0, 100, 40, 5, key="skill_score")
        period_s = st.selectbox("データ取得期間（スキル1）", ["3mo", "6mo", "1y"], index=1, key="skill_period")
        max_stocks_s = st.slider("スキャン銘柄数（スキル1）", 10, 225, 225, 10, key="skill_stocks")

        st.divider()
        st.markdown("""
        **スコア内訳（チャートスキル1）**
        - N大（ものわかれ）: 35点
        - 下半身: 30点
        - 逆くちばし: 25点
        - 前高値ブレイク: 15点
        - キリ値節目: 10点
        - 上昇初動（1〜3日）: +5点
        - 上昇7日以上: −20点
        """)
        st.markdown("""
        **主要技法の見方**

        🔵 **N大（ものわかれ）**
        MA5がMA20に接近後、再び上に離れる→トレンド継続の確認

        🟢 **下半身**
        MA5が上向き＋陽線実体がMA5をカラダ半分以上超えた→買いシグナル

        🟡 **逆くちばし**
        上昇中のMA20にMA5が接近後、再び上昇→トレンド加速の初動

        ⚠️ **7の法則**
        上昇・下落は7日で終わる。5日以上で反転注意
        """)

    if st.button("🔍 チャートスキル1 スキャン開始", type="primary", use_container_width=True, key="skill_scan"):
        tickers = get_nikkei225_tickers()[:max_stocks_s]
        total = len(tickers)
        progress_bar = st.progress(0)
        status_text = st.empty()
        results = []

        for i, ticker in enumerate(tickers):
            name = get_company_name(ticker)
            status_text.text(f"処理中: {name}（{ticker}） [{i+1}/{total}]")
            progress_bar.progress((i + 1) / total)

            df = fetch_ohlcv(ticker, period=period_s)
            if df is None:
                continue
            df = add_all_indicators(df)
            result = score_chart_skill1(df)

            if result["score"] < min_score_s:
                continue

            last = df.iloc[-1]
            results.append({
                "ticker": ticker,
                "name": name,
                "score": result["score"],
                "close": last["Close"],
                "MA5": last.get("MA5"),
                "MA20": last.get("MA20"),
                "summary": result["summary"],
                "_df": df,
                "_result": result,
            })

        progress_bar.empty()
        status_text.empty()
        results.sort(key=lambda x: x["score"], reverse=True)
        st.session_state["skill_results"] = results

        if results:
            st.success(f"スキャン完了！ {len(results)}銘柄が条件を満たしました。")
        else:
            st.warning("条件に合致する銘柄が見つかりませんでした。最低スコアを下げてお試しください。")

    if st.session_state.get("skill_results"):
        results = st.session_state["skill_results"]
        st.subheader(f"📋 チャートスキル1 候補一覧（{len(results)}件）")

        rule7_labels = {True: "⚠️反転注意", False: ""}

        display_df = pd.DataFrame([{
            "スコア": r["score"],
            "コード": r["ticker"].replace(".T", ""),
            "銘柄名": r["name"],
            "現在値": f"¥{r['close']:,.0f}",
            "N大": "✅" if r["_result"]["monoware_bull"]["pass"] else "—",
            "下半身": "✅" if r["_result"]["shitahanshin"]["pass"] else "—",
            "逆くちばし": "✅" if r["_result"]["kuchibashi"]["pass"] else "—",
            "前高値ブレイク": "✅" if r["_result"]["prev_high_break"]["pass"] else "—",
            "7の法則": r["_result"]["rule_of_7"]["detail"],
            "コメント": r["summary"],
        } for r in results])

        st.dataframe(display_df, use_container_width=True, hide_index=True,
                     column_config={"スコア": st.column_config.ProgressColumn("スコア", min_value=0, max_value=100)})

        st.subheader("📊 詳細チャート（チャートスキル1）")
        opts = [f"{r['ticker'].replace('.T','')} - {r['name']} (スコア:{r['score']})" for r in results]
        sel = st.selectbox("銘柄を選択", opts, key="skill_chart_sel")

        if sel:
            idx = opts.index(sel)
            r = results[idx]
            df = r["_df"]
            result = r["_result"]

            fig = draw_chart(df, f"{r['name']}（{r['ticker']}）")
            # MA20ラインを追加
            if "MA20" in df.columns:
                fig.add_trace(go.Scatter(
                    x=df.index, y=df["MA20"], name="MA20",
                    line=dict(color="#00bcd4", width=1.5, dash="dot"),
                ), row=1, col=1)
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("📝 チャートスキル1 詳細判定")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**ものわかれ（N大）**")
                mw = result["monoware_bull"]
                st.write(f"{'✅' if mw['pass'] else '❌'} {mw['detail']}")
                if not mw["pass"]:
                    st.write(f"　トレンド上昇: {'✅' if mw.get('trend_up') else '❌'}")
                    st.write(f"　接近あり: {'✅' if mw.get('was_close') else '❌'} (最小乖離{mw.get('min_diff_pct', 0):.1f}%)")
                    st.write(f"　再離反: {'✅' if mw.get('now_diverging') else '❌'}")

                st.markdown("**前高値ブレイク**")
                ph = result["prev_high_break"]
                st.write(f"{'✅' if ph['pass'] else '❌'} {ph['detail']}")

            with col2:
                st.markdown("**下半身**")
                sh = result["shitahanshin"]
                st.write(f"{'✅' if sh['pass'] else '❌'} {sh['detail']}")
                if not sh["pass"]:
                    st.write(f"　MA5上向き: {'✅' if sh.get('ma5_flat_or_up') else '❌'}")
                    st.write(f"　陽線: {'✅' if sh.get('is_bullish') else '❌'}")
                    st.write(f"　実体MA5超え: {'✅' if sh.get('body_above_ma5') else '❌'}")

                st.markdown("**キリ値節目**")
                rn = result["round_number"]
                st.write(f"{'✅' if rn['pass'] else '—'} {rn['detail']}")

            with col3:
                st.markdown("**逆くちばし**")
                kb = result["kuchibashi"]
                st.write(f"{'✅' if kb['pass'] else '❌'} {kb['detail']}")

                st.markdown("**7の法則**")
                r7 = result["rule_of_7"]
                if r7["reversal_warning"]:
                    st.warning(f"⚠️ {r7['detail']}")
                else:
                    st.write(f"ℹ️ {r7['detail']}")
                st.caption("上昇・下落は連続7日で終わりやすい。5日以上で反転を意識。")

            st.markdown(external_links(r["ticker"]))

# ─── フッター ─────────────────────────────────────────────────────────────
st.divider()
st.caption("※ 本アプリは情報提供を目的としており、投資を推奨するものではありません。投資判断はご自身の責任でお願いします。")
