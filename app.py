"""押し目銘柄スクリーナー - Streamlit メインアプリ。"""

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

# ─── ページ設定 ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="押し目銘柄スクリーナー（日経225）",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 押し目銘柄スクリーナー（日経225）")
st.markdown("上昇トレンド中の銘柄から、押し目買いの好機を自動スクリーニングします。")

# ─── サイドバー設定 ──────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ スクリーニング設定")

    min_score = st.slider("最低スコア（0〜100）", 0, 100, 50, 5,
                          help="スコアが高いほど押し目条件が多く揃っています")

    period = st.selectbox("データ取得期間", ["3mo", "6mo", "1y"], index=1,
                          help="長い期間ほど精度が上がりますが時間がかかります")

    max_stocks = st.slider("一度にスキャンする銘柄数", 10, 225, 225, 10,
                           help="少ないほど速く完了します")

    st.divider()
    st.subheader("条件フィルター")
    require_ma = st.checkbox("MA上向き整列（必須）", value=True)
    require_pullback = st.checkbox("押し目ゾーン内（必須）", value=True)
    require_volume = st.checkbox("出来高確認あり", value=False)

    st.divider()
    st.markdown("""
    **スコアの内訳**
    - トレンド確認: 30点
    - 押し目ゾーン: 20点
    - 下げ止まりサイン×4: 各10点
    - 出来高確認: 10点
    - 全揃いボーナス: +10点
    """)

# ─── スクリーニング実行 ────────────────────────────────────────────────────
if st.button("🔍 スクリーニング開始", type="primary", use_container_width=True):
    tickers = get_nikkei225_tickers()[:max_stocks]
    total = len(tickers)

    progress_bar = st.progress(0, text="データ取得中...")
    status_text = st.empty()

    results = []

    for i, ticker in enumerate(tickers):
        progress = (i + 1) / total
        name = get_company_name(ticker)
        status_text.text(f"処理中: {name}（{ticker}） [{i+1}/{total}]")
        progress_bar.progress(progress, text=f"スキャン中... {i+1}/{total}")

        df = fetch_ohlcv(ticker, period=period)
        if df is None:
            continue

        df = add_all_indicators(df)
        result = score_ticker(df)

        if result["score"] < min_score:
            continue
        if require_ma and not result["ma_alignment"]["pass"]:
            continue
        if require_pullback and not result["pullback_zone"]["pass"]:
            continue
        if require_volume and not result.get("volume_ok", False):
            continue

        last = df.iloc[-1]
        results.append({
            "ticker": ticker,
            "name": name,
            "score": result["score"],
            "close": last["Close"],
            "MA5": last.get("MA5", None),
            "MA25": last.get("MA25", None),
            "MA75": last.get("MA75", None),
            "RSI": last.get("RSI", None),
            "RCI": last.get("RCI_SHORT", None),
            "ma_ok": result["ma_alignment"]["pass"],
            "zone_ok": result["pullback_zone"]["pass"],
            "reversal_count": result.get("reversal_count", 0),
            "volume_ok": result.get("volume_ok", False),
            "summary": result["summary"],
            "_df": df,
            "_result": result,
        })

    progress_bar.empty()
    status_text.empty()

    if not results:
        st.warning("条件に合致する銘柄が見つかりませんでした。最低スコアを下げるか、フィルター条件を緩めてください。")
        st.stop()

    results.sort(key=lambda x: x["score"], reverse=True)
    st.session_state["results"] = results
    st.session_state["scan_done"] = True
    st.success(f"スキャン完了！ {total}銘柄中 {len(results)}銘柄が条件を満たしました。")

# ─── 結果表示 ─────────────────────────────────────────────────────────────
if st.session_state.get("scan_done") and st.session_state.get("results"):
    results = st.session_state["results"]

    # 一覧テーブル
    st.subheader(f"📋 スクリーニング結果（{len(results)}件）")

    display_df = pd.DataFrame([{
        "スコア": r["score"],
        "コード": r["ticker"].replace(".T", ""),
        "銘柄名": r["name"],
        "現在値": f"¥{r['close']:,.0f}",
        "MA5": f"¥{r['MA5']:,.0f}" if r["MA5"] else "-",
        "MA25": f"¥{r['MA25']:,.0f}" if r["MA25"] else "-",
        "RSI": f"{r['RSI']:.1f}" if r["RSI"] else "-",
        "RCI短期": f"{r['RCI']:.1f}" if r["RCI"] else "-",
        "MA整列": "✅" if r["ma_ok"] else "❌",
        "押し目帯": "✅" if r["zone_ok"] else "❌",
        "反転数": f"{r['reversal_count']}/4",
        "出来高": "✅" if r["volume_ok"] else "❌",
        "コメント": r["summary"],
    } for r in results])

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "スコア": st.column_config.ProgressColumn("スコア", min_value=0, max_value=100),
        }
    )

    # 詳細チャート
    st.subheader("📊 詳細チャート")
    ticker_options = [f"{r['ticker'].replace('.T','')} - {r['name']} (スコア:{r['score']})" for r in results]
    selected = st.selectbox("銘柄を選択", ticker_options)

    if selected:
        idx = ticker_options.index(selected)
        r = results[idx]
        df = r["_df"]
        result = r["_result"]

        # ─── Plotlyチャート描画 ───────────────────────────────────────────
        fig = make_subplots(
            rows=4, cols=1,
            shared_xaxes=True,
            row_heights=[0.5, 0.15, 0.175, 0.175],
            vertical_spacing=0.03,
            subplot_titles=[
                f"{r['name']}（{r['ticker']}）",
                "出来高",
                "RSI / RCI短期",
                "MACD",
            ]
        )

        # ローソク足
        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"],
            name="ローソク足",
            increasing_line_color="#ff4b4b",
            decreasing_line_color="#1f77b4",
        ), row=1, col=1)

        # MA
        for ma, color, width in [("MA5", "#f5a623", 1), ("MA25", "#7ed321", 1.5), ("MA75", "#9013fe", 2)]:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[ma], name=ma,
                line=dict(color=color, width=width), opacity=0.9,
            ), row=1, col=1)

        # BB
        fig.add_trace(go.Scatter(
            x=df.index, y=df["BB_UPPER2"], name="BB+2σ",
            line=dict(color="rgba(150,150,150,0.5)", width=1, dash="dot"),
            showlegend=False,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["BB_LOWER2"], name="BB-2σ",
            line=dict(color="rgba(150,150,150,0.5)", width=1, dash="dot"),
            fill="tonexty",
            fillcolor="rgba(150,150,150,0.05)",
            showlegend=False,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["BB_MID"], name="BB MID",
            line=dict(color="rgba(150,150,150,0.7)", width=1, dash="dash"),
        ), row=1, col=1)

        # 出来高
        colors = ["#ff4b4b" if c >= o else "#1f77b4"
                  for c, o in zip(df["Close"], df["Open"])]
        fig.add_trace(go.Bar(
            x=df.index, y=df["Volume"], name="出来高",
            marker_color=colors, opacity=0.7,
        ), row=2, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["VOL_MA"], name="VOL MA25",
            line=dict(color="orange", width=1.5),
        ), row=2, col=1)

        # RSI
        fig.add_trace(go.Scatter(
            x=df.index, y=df["RSI"], name="RSI",
            line=dict(color="#f5a623", width=1.5),
        ), row=3, col=1)
        # RSI水平線
        for lvl, color in [(30, "green"), (50, "gray"), (70, "red")]:
            fig.add_hline(y=lvl, line_dash="dot", line_color=color,
                          opacity=0.5, row=3, col=1)

        # RCI短期
        fig.add_trace(go.Scatter(
            x=df.index, y=df["RCI_SHORT"], name="RCI短期",
            line=dict(color="#4fc3f7", width=1.5),
        ), row=3, col=1)
        for lvl in [-80, 80]:
            fig.add_hline(y=lvl, line_dash="dot", line_color="purple",
                          opacity=0.4, row=3, col=1)

        # MACD
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
        fig.add_hline(y=0, line_dash="dot", line_color="gray",
                      opacity=0.5, row=4, col=1)

        fig.update_layout(
            height=850,
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            legend=dict(orientation="h", y=1.02, x=0),
            margin=dict(l=10, r=10, t=60, b=10),
        )

        st.plotly_chart(fig, use_container_width=True)

        # 条件詳細
        st.subheader("📝 条件詳細")
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
            rc = result["reversal_candle"]
            st.write(f"{'✅' if rc['pass'] else '❌'} ローソク足反転: {rc['detail']}")
            rsi = result["rsi"]
            st.write(f"{'✅' if rsi['pass'] else '❌'} {rsi['detail']}")
            rci = result["rci"]
            st.write(f"{'✅' if rci['pass'] else '❌'} {rci['detail']}")
            macd = result["macd"]
            st.write(f"{'✅' if macd['pass'] else '❌'} {macd['detail']}")
            vol = result["volume"]
            st.write(f"{'✅' if vol['pass'] else '❌'} 出来高: {vol['detail']}")

        if result["danger"]["has_danger"]:
            st.error(f"⚠️ 危険サイン: {result['danger']['detail']}")

        # 外部リンク
        code = r["ticker"].replace(".T", "")
        st.markdown(f"""
        **外部チャートを確認する:**
        [Yahoo!ファイナンス](https://finance.yahoo.co.jp/quote/{code}.T)　|
        [株探](https://kabutan.jp/stock/chart?code={code})　|
        [みんかぶ](https://minkabu.jp/stock/{code}/chart)
        """)

# ─── フッター ─────────────────────────────────────────────────────────────
st.divider()
st.caption("※ 本アプリは情報提供を目的としており、投資を推奨するものではありません。投資判断はご自身の責任でお願いします。")
