"""押し目スクリーニング条件の評価モジュール。"""

import numpy as np
import pandas as pd
from indicators import calc_fibonacci


# ────────────────────────────────────────
# 1. トレンドが生きているか
# ────────────────────────────────────────

def check_ma_alignment(df: pd.DataFrame) -> dict:
    """MA5 > MA25 > MA75 の上向き整列を確認する。"""
    row = df.iloc[-1]
    ma5, ma25, ma75 = row.get("MA5"), row.get("MA25"), row.get("MA75")
    if any(pd.isna(v) for v in [ma5, ma25, ma75]):
        return {"pass": False, "detail": "MA計算不足"}

    alignment_ok = ma5 > ma25 > ma75
    ma75_rising = df["MA75"].iloc[-1] > df["MA75"].iloc[-5]

    return {
        "pass": alignment_ok and ma75_rising,
        "ma5_gt_ma25": bool(ma5 > ma25),
        "ma25_gt_ma75": bool(ma25 > ma75),
        "ma75_rising": bool(ma75_rising),
        "detail": "MA5>MA25>MA75 上向き" if alignment_ok and ma75_rising else "MA整列崩れ or MA75下向き",
    }


def check_higher_lows(df: pd.DataFrame, lookback: int = 40) -> dict:
    """直近の安値が前の安値より高い（高値・安値の切り上げ）を確認する。"""
    lows = df["Low"].tail(lookback)
    # ローカルミニマムを探す（前後より低い点）
    local_mins = []
    vals = lows.values
    for i in range(1, len(vals) - 1):
        if vals[i] < vals[i - 1] and vals[i] < vals[i + 1]:
            local_mins.append(vals[i])

    if len(local_mins) < 2:
        return {"pass": True, "detail": "安値比較対象不足（通過）"}

    recent_low = local_mins[-1]
    prev_low = local_mins[-2]
    ok = recent_low > prev_low

    return {
        "pass": bool(ok),
        "recent_low": float(recent_low),
        "prev_low": float(prev_low),
        "detail": "安値切り上げ確認" if ok else "安値切り下げ（トレンド転換疑い）",
    }


# ────────────────────────────────────────
# 2. 押しの深さ（支持帯への接近）
# ────────────────────────────────────────

def check_pullback_zone(df: pd.DataFrame) -> dict:
    """現在値がMA5〜MA25ゾーンまたはBB MID〜-1σ圏内かを確認する。"""
    row = df.iloc[-1]
    close = row["Close"]
    ma5 = row.get("MA5")
    ma25 = row.get("MA25")
    bb_mid = row.get("BB_MID")
    bb_lower1 = row.get("BB_LOWER1")

    if any(pd.isna(v) for v in [ma5, ma25, bb_mid, bb_lower1]):
        return {"pass": False, "detail": "指標計算不足"}

    # MA5〜MA25ゾーンへの押し（現値がMA25以上かつMA5以下付近）
    in_ma_zone = bb_lower1 <= close <= ma5 * 1.02

    # BB MIDまで戻ってきているか（MA5〜MID間）
    in_bb_zone = bb_lower1 <= close <= bb_mid * 1.01

    # フィボナッチ38.2〜61.8%圏
    fib = calc_fibonacci(df)
    in_fib_zone = fib["fib_618"] <= close <= fib["fib_382"] * 1.01

    passed = in_ma_zone or in_bb_zone or in_fib_zone

    return {
        "pass": bool(passed),
        "in_ma_zone": bool(in_ma_zone),
        "in_bb_zone": bool(in_bb_zone),
        "in_fib_zone": bool(in_fib_zone),
        "close": float(close),
        "ma5": float(ma5),
        "ma25": float(ma25),
        "bb_mid": float(bb_mid),
        "fib_382": float(fib["fib_382"]),
        "fib_618": float(fib["fib_618"]),
        "detail": "押し目ゾーン内" if passed else "押し目ゾーン外",
    }


# ────────────────────────────────────────
# 3. 下げ止まりの確認サイン
# ────────────────────────────────────────

def check_reversal_candle(df: pd.DataFrame) -> dict:
    """下ヒゲ陽線・包み足・はらみ足など反転サインを確認する。"""
    last = df.iloc[-1]
    prev = df.iloc[-2]

    body = abs(last["Close"] - last["Open"])
    lower_wick = last["Open"] - last["Low"] if last["Close"] >= last["Open"] else last["Close"] - last["Low"]
    upper_wick = last["High"] - last["Close"] if last["Close"] >= last["Open"] else last["High"] - last["Open"]
    total_range = last["High"] - last["Low"]

    # 長い下ヒゲ陽線（下ヒゲが実体の2倍以上）
    long_lower_wick = (lower_wick >= body * 2) and (last["Close"] >= last["Open"])

    # 包み足（前日の実体を今日の実体が包む陽線）
    engulfing = (
        last["Close"] > last["Open"]  # 陽線
        and last["Open"] < prev["Close"]  # 今日の始値が前日終値より低い
        and last["Close"] > prev["Open"]  # 今日の終値が前日始値より高い
    )

    # コマ足・十字線（実体が小さい）
    doji = (body <= total_range * 0.2) if total_range > 0 else False

    passed = long_lower_wick or engulfing or doji

    return {
        "pass": bool(passed),
        "long_lower_wick": bool(long_lower_wick),
        "engulfing": bool(engulfing),
        "doji": bool(doji),
        "detail": ("下ヒゲ陽線" if long_lower_wick else "") +
                  ("包み足" if engulfing else "") +
                  ("十字線/コマ" if doji else "") or "反転サインなし",
    }


def check_rsi(df: pd.DataFrame) -> dict:
    """RSIが売られすぎ圏（30〜50）から反転しているかを確認する。"""
    rsi_series = df["RSI"].dropna()
    if len(rsi_series) < 3:
        return {"pass": False, "detail": "RSI計算不足"}

    current = rsi_series.iloc[-1]
    prev = rsi_series.iloc[-2]
    prev2 = rsi_series.iloc[-3]

    # 40〜55圏で反転上昇中（直近2日以上上向き）
    in_zone = 30 <= current <= 55
    rising = current > prev > prev2

    # 危険ゾーン（RSI高すぎる）
    too_high = current > 65

    return {
        "pass": bool(in_zone and rising and not too_high),
        "rsi_current": float(current),
        "rsi_rising": bool(rising),
        "in_zone": bool(in_zone),
        "detail": f"RSI={current:.1f} {'反転上昇中' if rising else '下降中'} {'(売られすぎ圏)' if in_zone else '(過熱または高すぎ)'}",
    }


def check_rci(df: pd.DataFrame) -> dict:
    """RCI短期が-80以下から反転しているかを確認する。"""
    rci_series = df["RCI_SHORT"].dropna()
    if len(rci_series) < 3:
        return {"pass": False, "detail": "RCI計算不足"}

    current = rci_series.iloc[-1]
    prev = rci_series.iloc[-2]
    prev_min = rci_series.tail(10).min()

    # -80以下から反転（底打ちサイン）
    was_oversold = prev_min <= -75
    now_rising = current > prev

    return {
        "pass": bool(was_oversold and now_rising),
        "rci_current": float(current),
        "rci_rising": bool(now_rising),
        "was_oversold": bool(was_oversold),
        "detail": f"RCI短期={current:.1f} {'↑反転' if now_rising else '↓下降'} {'(底打ち確認)' if was_oversold else '(売られすぎ未到達)'}",
    }


def check_macd(df: pd.DataFrame) -> dict:
    """MACDが0ライン上でヒストグラム反転しているかを確認する。"""
    macd = df["MACD"].dropna()
    hist = df["MACD_HIST"].dropna()
    if len(hist) < 3:
        return {"pass": False, "detail": "MACD計算不足"}

    macd_current = macd.iloc[-1]
    hist_current = hist.iloc[-1]
    hist_prev = hist.iloc[-2]
    hist_prev2 = hist.iloc[-3]

    above_zero = macd_current > 0
    hist_expanding = hist_current > hist_prev  # ヒストグラムが伸びている
    hist_was_shrinking = hist_prev < hist_prev2  # 直前まで縮小していた（= 反転点）

    return {
        "pass": bool(above_zero and hist_expanding),
        "macd": float(macd_current),
        "hist_current": float(hist_current),
        "above_zero": bool(above_zero),
        "hist_expanding": bool(hist_expanding),
        "detail": f"MACD={macd_current:.2f} ヒスト={'拡大' if hist_expanding else '縮小'} {'(0ライン上)' if above_zero else '(0ライン下)'}",
    }


# ────────────────────────────────────────
# 4. 出来高の裏付け
# ────────────────────────────────────────

def check_volume(df: pd.DataFrame) -> dict:
    """
    押し目では出来高が減り、反発時に増えることを確認する。
    ・直近3日の出来高が平均より少ない（押しの出来高縮小）
    ・最終日の出来高が直前2日より多い（反発の兆し）
    """
    if "VOL_MA" not in df.columns:
        return {"pass": False, "detail": "VOL_MA未計算"}

    recent_3 = df["Volume"].tail(3)
    vol_ma = df["VOL_MA"].iloc[-1]
    last_vol = df["Volume"].iloc[-1]
    prev_vol = df["Volume"].iloc[-2]
    prev2_vol = df["Volume"].iloc[-3]

    avg_recent = recent_3.mean()
    pullback_vol_low = avg_recent < vol_ma * 0.85  # 平均比85%未満
    rebound_vol_high = last_vol > prev_vol  # 最終日に出来高増加

    # 危険: 下落時に出来高が急増している
    dangerous = (
        df["Close"].iloc[-1] < df["Close"].iloc[-2]  # 最終日が下落
        and last_vol > vol_ma * 1.5  # 且つ出来高が平均の1.5倍超
    )

    return {
        "pass": bool(pullback_vol_low and rebound_vol_high and not dangerous),
        "vol_ma_ratio": float(avg_recent / vol_ma) if vol_ma > 0 else 0,
        "rebound_vol_high": bool(rebound_vol_high),
        "dangerous_selloff": bool(dangerous),
        "detail": (
            "大量出来高下落（危険）" if dangerous
            else ("出来高縮小→反発増加" if (pullback_vol_low and rebound_vol_high)
                  else "出来高条件未達")
        ),
    }


# ────────────────────────────────────────
# 5. 危険チェック（除外条件）
# ────────────────────────────────────────

def check_danger_signals(df: pd.DataFrame) -> dict:
    """押し目に見えて危険な形をチェックする。"""
    row = df.iloc[-1]
    rsi = df["RSI"].iloc[-1] if "RSI" in df.columns else None
    ma75 = row.get("MA75")
    close = row["Close"]

    dangers = []
    # MA75が下向き
    if "MA75" in df.columns and len(df) >= 5:
        if df["MA75"].iloc[-1] < df["MA75"].iloc[-5]:
            dangers.append("MA75が下向き（戻り売りの可能性）")

    # RSIが高い位置での浅い押し
    if rsi is not None and rsi > 60:
        dangers.append(f"RSI={rsi:.1f}（過熱解消不十分）")

    # 大量出来高の大陰線
    last_candle_bearish = df["Close"].iloc[-1] < df["Open"].iloc[-1]
    large_vol = df["Volume"].iloc[-1] > df["VOL_MA"].iloc[-1] * 1.5 if "VOL_MA" in df.columns else False
    if last_candle_bearish and large_vol:
        dangers.append("大量出来高の大陰線（本格下落の可能性）")

    return {
        "has_danger": len(dangers) > 0,
        "dangers": dangers,
        "detail": "、".join(dangers) if dangers else "危険サインなし",
    }


# ────────────────────────────────────────
# 総合スコアリング
# ────────────────────────────────────────

def score_ticker(df: pd.DataFrame) -> dict:
    """
    1銘柄の押し目スコアを計算する。

    Returns:
        スコア詳細辞書。score(0〜100)、各条件の合否を含む。
    """
    results = {}
    results["ma_alignment"] = check_ma_alignment(df)
    results["higher_lows"] = check_higher_lows(df)
    results["pullback_zone"] = check_pullback_zone(df)
    results["reversal_candle"] = check_reversal_candle(df)
    results["rsi"] = check_rsi(df)
    results["rci"] = check_rci(df)
    results["macd"] = check_macd(df)
    results["volume"] = check_volume(df)
    results["danger"] = check_danger_signals(df)

    # 危険サインがあればスコアを大きく下げる
    if results["danger"]["has_danger"]:
        return {**results, "score": 0, "summary": "危険: " + results["danger"]["detail"]}

    # 大前提条件（トレンド）
    trend_ok = results["ma_alignment"]["pass"] and results["higher_lows"]["pass"]
    if not trend_ok:
        return {**results, "score": 0, "summary": "トレンド条件不成立"}

    # 押し目ゾーン確認（必須）
    if not results["pullback_zone"]["pass"]:
        return {**results, "score": 0, "summary": "押し目ゾーン外"}

    # 下げ止まりサイン（複数のうちいくつ揃っているか）
    reversal_checks = [
        results["reversal_candle"]["pass"],
        results["rsi"]["pass"],
        results["rci"]["pass"],
        results["macd"]["pass"],
    ]
    reversal_count = sum(reversal_checks)

    # 出来高確認
    volume_ok = results["volume"]["pass"]

    # スコア計算（100点満点）
    # トレンド: 30点、押し目ゾーン: 20点、下げ止まり: 各12.5点×4=50点満点のうち取得分、出来高: 20点
    score = 30  # トレンドOK
    score += 20  # 押し目ゾーンOK
    score += reversal_count * 10  # 下げ止まりサイン数×10点（最大40点）
    score += 10 if volume_ok else 0  # 出来高確認

    # 理想形（全条件揃い）にボーナス
    if reversal_count >= 3 and volume_ok:
        score = min(score + 10, 100)

    summary_parts = []
    if results["reversal_candle"]["pass"]:
        summary_parts.append(results["reversal_candle"]["detail"])
    if results["rsi"]["pass"]:
        summary_parts.append(results["rsi"]["detail"])
    if results["rci"]["pass"]:
        summary_parts.append(results["rci"]["detail"])
    if results["macd"]["pass"]:
        summary_parts.append(results["macd"]["detail"])
    if volume_ok:
        summary_parts.append("出来高OK")

    return {
        **results,
        "score": score,
        "reversal_count": reversal_count,
        "volume_ok": volume_ok,
        "summary": " / ".join(summary_parts) if summary_parts else "条件不足",
    }
