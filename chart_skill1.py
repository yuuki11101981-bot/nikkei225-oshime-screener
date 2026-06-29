"""
チャートスキル1 に基づくスクリーニングモジュール。

Mission016: ものわかれ（N大・逆N大）
Mission014: 下半身・逆下半身
Mission015: くちばし・逆くちばし
Mission012: 7の法則（連続カウント）
Mission013: 前の高値・安値ブレイク / キリ値節目
Mission011: 3・6カ月サイクル（補助情報）
"""

import numpy as np
import pandas as pd


# ────────────────────────────────────────
# Mission016: ものわかれ（N大・逆N大）
# ────────────────────────────────────────

def check_monoware_bullish(df: pd.DataFrame) -> dict:
    """
    上昇トレンドでのものわかれ（N大）を検出する。
    条件:
    1. MA5 が MA20 の上にある（上昇トレンド）
    2. 直近 5〜15 日以内に MA5 と MA20 が接近（差が Close の 2% 以内）した
    3. 現在は再び MA5 が MA20 から離れている（差が広がっている）
    """
    if "MA5" not in df.columns or "MA20" not in df.columns:
        return {"pass": False, "detail": "MA未計算"}

    ma5 = df["MA5"].dropna()
    ma20 = df["MA20"].dropna()
    close = df["Close"]

    if len(ma5) < 20:
        return {"pass": False, "detail": "データ不足"}

    current_ma5 = ma5.iloc[-1]
    current_ma20 = ma20.iloc[-1]
    current_close = close.iloc[-1]

    # MA5がMA20の上にあるか（上昇トレンド前提）
    trend_up = current_ma5 > current_ma20

    # 直近15日のMA5とMA20の差を計算（Close比の%）
    lookback = min(15, len(ma5) - 1)
    diffs = []
    for i in range(1, lookback + 1):
        idx = -i
        d = abs(ma5.iloc[idx] - ma20.iloc[idx]) / close.iloc[idx] * 100
        diffs.append(d)

    min_diff = min(diffs)           # 直近15日の最小乖離
    current_diff = diffs[0]         # 直近の乖離
    was_close = min_diff <= 2.0     # 接近した（2%以内）
    now_diverging = current_diff > min_diff * 1.5  # 再び離れている

    passed = trend_up and was_close and now_diverging

    return {
        "pass": bool(passed),
        "trend_up": bool(trend_up),
        "was_close": bool(was_close),
        "now_diverging": bool(now_diverging),
        "min_diff_pct": float(min_diff),
        "current_diff_pct": float(current_diff),
        "detail": "N大（ものわかれ上昇）確認" if passed else "ものわかれ未成立",
    }


def check_monoware_bearish(df: pd.DataFrame) -> dict:
    """
    下落トレンドでのものわかれ（逆N大）を検出する。
    条件:
    1. MA5 が MA20 の下にある（下落トレンド）
    2. 直近 5〜15 日以内に MA5 と MA20 が接近した
    3. 現在は再び MA5 が MA20 から離れて下落している
    """
    if "MA5" not in df.columns or "MA20" not in df.columns:
        return {"pass": False, "detail": "MA未計算"}

    ma5 = df["MA5"].dropna()
    ma20 = df["MA20"].dropna()
    close = df["Close"]

    if len(ma5) < 20:
        return {"pass": False, "detail": "データ不足"}

    current_ma5 = ma5.iloc[-1]
    current_ma20 = ma20.iloc[-1]

    trend_down = current_ma5 < current_ma20

    lookback = min(15, len(ma5) - 1)
    diffs = []
    for i in range(1, lookback + 1):
        d = abs(ma5.iloc[-i] - ma20.iloc[-i]) / close.iloc[-i] * 100
        diffs.append(d)

    min_diff = min(diffs)
    current_diff = diffs[0]
    was_close = min_diff <= 2.0
    now_diverging = current_diff > min_diff * 1.5

    passed = trend_down and was_close and now_diverging

    return {
        "pass": bool(passed),
        "trend_down": bool(trend_down),
        "was_close": bool(was_close),
        "now_diverging": bool(now_diverging),
        "min_diff_pct": float(min_diff),
        "detail": "逆N大（ものわかれ下落）確認" if passed else "逆ものわかれ未成立",
    }


# ────────────────────────────────────────
# Mission014: 下半身・逆下半身
# ────────────────────────────────────────

def check_shitahanshin(df: pd.DataFrame) -> dict:
    """
    下半身（買いシグナル）を検出する。
    条件:
    - MA5 が横ばい or 上向き
    - 陽線のローソク足実体の中心がMA5を上回っている（実体がMA5を半分以上超えた）
    """
    if "MA5" not in df.columns:
        return {"pass": False, "detail": "MA5未計算"}

    last = df.iloc[-1]
    ma5_now = df["MA5"].iloc[-1]
    ma5_prev = df["MA5"].iloc[-5]

    if pd.isna(ma5_now) or pd.isna(ma5_prev):
        return {"pass": False, "detail": "MA5計算不足"}

    # MA5が横ばい or 上向き
    ma5_flat_or_up = ma5_now >= ma5_prev * 0.998

    # 陽線
    is_bullish = last["Close"] > last["Open"]

    # 実体の中心がMA5を上回っているか（実体がMA5をカラダ半分以上超えた）
    body_center = (last["Close"] + last["Open"]) / 2
    body_above_ma5 = body_center > ma5_now
    # かつ実体下端がMA5付近（MA5から乖離しすぎていない）
    body_low = min(last["Close"], last["Open"])
    body_near_ma5 = body_low <= ma5_now * 1.03

    passed = ma5_flat_or_up and is_bullish and body_above_ma5 and body_near_ma5

    return {
        "pass": bool(passed),
        "ma5_flat_or_up": bool(ma5_flat_or_up),
        "is_bullish": bool(is_bullish),
        "body_above_ma5": bool(body_above_ma5),
        "detail": "下半身（買いシグナル）成立" if passed else "下半身未成立",
    }


def check_gyaku_shitahanshin(df: pd.DataFrame) -> dict:
    """
    逆下半身（売りシグナル）を検出する。
    条件:
    - MA5 が横ばい or 下向き
    - 陰線のローソク足実体の中心がMA5を下回っている
    """
    if "MA5" not in df.columns:
        return {"pass": False, "detail": "MA5未計算"}

    last = df.iloc[-1]
    ma5_now = df["MA5"].iloc[-1]
    ma5_prev = df["MA5"].iloc[-5]

    if pd.isna(ma5_now) or pd.isna(ma5_prev):
        return {"pass": False, "detail": "MA5計算不足"}

    ma5_flat_or_down = ma5_now <= ma5_prev * 1.002
    is_bearish = last["Close"] < last["Open"]
    body_center = (last["Close"] + last["Open"]) / 2
    body_below_ma5 = body_center < ma5_now
    body_high = max(last["Close"], last["Open"])
    body_near_ma5 = body_high >= ma5_now * 0.97

    passed = ma5_flat_or_down and is_bearish and body_below_ma5 and body_near_ma5

    return {
        "pass": bool(passed),
        "ma5_flat_or_down": bool(ma5_flat_or_down),
        "is_bearish": bool(is_bearish),
        "body_below_ma5": bool(body_below_ma5),
        "detail": "逆下半身（売りシグナル）成立" if passed else "逆下半身未成立",
    }


# ────────────────────────────────────────
# Mission015: くちばし・逆くちばし
# ────────────────────────────────────────

def check_kuchibashi(df: pd.DataFrame) -> dict:
    """
    くちばし（上昇への反転前兆）を検出する。
    条件:
    - MA20が下向き
    - 直近にMA5がMA20に接近した（2%以内）が、突き抜けずに再び下落
    - 下向きMA20の下にあった5日線が、上向きに転じた形 → 底打ちの初動
    """
    if "MA5" not in df.columns or "MA20" not in df.columns:
        return {"pass": False, "detail": "MA未計算"}

    ma5 = df["MA5"].dropna()
    ma20 = df["MA20"].dropna()

    if len(ma5) < 15:
        return {"pass": False, "detail": "データ不足"}

    ma20_down = df["MA20"].iloc[-1] < df["MA20"].iloc[-10]

    # 直近10日以内にMA5がMA20に接近（2%以内）したが突き抜けていない
    approached = False
    for i in range(2, 12):
        if i >= len(ma5):
            break
        diff_pct = (ma20.iloc[-i] - ma5.iloc[-i]) / ma20.iloc[-i] * 100
        if 0 < diff_pct <= 2.5:
            approached = True
            break

    # 現在はMA5がMA20を下回っている（突き抜けず）
    currently_below = ma5.iloc[-1] < ma20.iloc[-1]

    # MA5が直近5日で上向きに転じている（底打ちの初動）
    ma5_turning_up = ma5.iloc[-1] > ma5.iloc[-3]

    passed = ma20_down and approached and currently_below and ma5_turning_up

    return {
        "pass": bool(passed),
        "ma20_down": bool(ma20_down),
        "approached": bool(approached),
        "ma5_turning_up": bool(ma5_turning_up),
        "detail": "くちばし（上昇転換の前兆）検出" if passed else "くちばし未検出",
    }


def check_gyaku_kuchibashi(df: pd.DataFrame) -> dict:
    """
    逆くちばし（下落への転換前兆）を検出する。
    条件:
    - MA20が上向き
    - 直近にMA5がMA20に接近したが、突き抜けずに再び上昇
    - 上向きMA20の上にある5日線が、再び上に離れていく形
    """
    if "MA5" not in df.columns or "MA20" not in df.columns:
        return {"pass": False, "detail": "MA未計算"}

    ma5 = df["MA5"].dropna()
    ma20 = df["MA20"].dropna()

    if len(ma5) < 15:
        return {"pass": False, "detail": "データ不足"}

    ma20_up = df["MA20"].iloc[-1] > df["MA20"].iloc[-10]

    approached = False
    for i in range(2, 12):
        if i >= len(ma5):
            break
        diff_pct = (ma5.iloc[-i] - ma20.iloc[-i]) / ma20.iloc[-i] * 100
        if 0 < diff_pct <= 2.5:
            approached = True
            break

    currently_above = ma5.iloc[-1] > ma20.iloc[-1]
    ma5_turning_up = ma5.iloc[-1] > ma5.iloc[-3]

    passed = ma20_up and approached and currently_above and ma5_turning_up

    return {
        "pass": bool(passed),
        "ma20_up": bool(ma20_up),
        "approached": bool(approached),
        "ma5_turning_up": bool(ma5_turning_up),
        "detail": "逆くちばし（上昇トレンド継続の初動）検出" if passed else "逆くちばし未検出",
    }


# ────────────────────────────────────────
# Mission012: 7の法則
# ────────────────────────────────────────

def check_rule_of_7(df: pd.DataFrame) -> dict:
    """
    7の法則：終値ベースで連続上昇・下落日数をカウントする。
    上昇カウント: 終値が前日より高い日を連続でカウント（陰線が出たら終了）
    下落カウント: 終値が前日より低い日を連続でカウント（陽線が出たら終了）

    5日以上続いている場合、反転に注意。
    """
    closes = df["Close"].values
    n = len(closes)

    up_count = 0
    down_count = 0

    # 直近の方向を判定
    for i in range(n - 1, 0, -1):
        if closes[i] > closes[i - 1]:
            if down_count > 0:
                break
            up_count += 1
        elif closes[i] < closes[i - 1]:
            if up_count > 0:
                break
            down_count += 1
        else:
            break

    reversal_warning = up_count >= 5 or down_count >= 5
    direction = "上昇" if up_count > 0 else ("下落" if down_count > 0 else "横ばい")
    count = up_count if up_count > 0 else down_count

    return {
        "up_count": up_count,
        "down_count": down_count,
        "direction": direction,
        "count": count,
        "reversal_warning": bool(reversal_warning),
        "detail": f"{direction}{count}日連続 {'⚠️反転注意' if reversal_warning else ''}",
    }


# ────────────────────────────────────────
# Mission013: 前の高値・安値ブレイク / キリ値節目
# ────────────────────────────────────────

def check_previous_high_break(df: pd.DataFrame, lookback: int = 60) -> dict:
    """
    直近lookback日の高値をブレイクしたかを確認する。
    ブレイク直後（3日以内）かつ大きく離れていない（8%以内）が理想。
    """
    recent_high = df["High"].tail(lookback).iloc[:-1].max()  # 最終日除く直近高値
    last_close = df["Close"].iloc[-1]
    broke = last_close > recent_high
    days_since_break = 0
    if broke:
        for i in range(1, min(10, len(df))):
            if df["Close"].iloc[-i] > recent_high:
                days_since_break = i
            else:
                break

    pct_above = (last_close - recent_high) / recent_high * 100

    return {
        "pass": bool(broke and pct_above <= 8),
        "recent_high": float(recent_high),
        "pct_above": float(pct_above),
        "broke": bool(broke),
        "detail": f"前高値¥{recent_high:,.0f} {'ブレイク+{:.1f}%'.format(pct_above) if broke else '未ブレイク'}",
    }


def check_round_number_support(df: pd.DataFrame) -> dict:
    """
    キリのいい株価（節目）付近にいるかを確認する。
    500円・1000円単位の節目から±3%以内を検出。
    """
    close = df["Close"].iloc[-1]
    unit = 1000 if close >= 1000 else 500

    lower = (close // unit) * unit
    upper = lower + unit
    nearest = lower if (close - lower) < (upper - close) else upper

    pct_from_kiri = abs(close - nearest) / nearest * 100
    near_kiri = pct_from_kiri <= 3.0

    return {
        "pass": bool(near_kiri),
        "nearest_kiri": float(nearest),
        "pct_from_kiri": float(pct_from_kiri),
        "detail": f"キリ値¥{nearest:,.0f}付近 ({pct_from_kiri:.1f}%)" if near_kiri else f"キリ値から{pct_from_kiri:.1f}%",
    }


# ────────────────────────────────────────
# 総合スコアリング（チャートスキル1）
# ────────────────────────────────────────

def score_chart_skill1(df: pd.DataFrame) -> dict:
    """
    チャートスキル1の全技法を評価してスコアを返す（買い目線のみ）。
    """
    results = {}
    results["monoware_bull"] = check_monoware_bullish(df)
    results["shitahanshin"] = check_shitahanshin(df)
    results["kuchibashi"] = check_gyaku_kuchibashi(df)   # 上昇継続の逆くちばし
    results["rule_of_7"] = check_rule_of_7(df)
    results["prev_high_break"] = check_previous_high_break(df)
    results["round_number"] = check_round_number_support(df)

    # 下半身かものわかれかくちばし、いずれかが成立していなければ対象外
    primary_signals = [
        results["monoware_bull"]["pass"],
        results["shitahanshin"]["pass"],
        results["kuchibashi"]["pass"],
    ]
    if not any(primary_signals):
        return {**results, "score": 0, "summary": "主要シグナルなし"}

    # 7の法則で5日以上上昇中は過熱注意
    rule7 = results["rule_of_7"]
    if rule7["up_count"] >= 6:
        return {**results, "score": 0, "summary": f"上昇{rule7['up_count']}日継続（過熱・反転注意）"}

    # スコア計算
    score = 0
    if results["monoware_bull"]["pass"]:
        score += 35
    if results["shitahanshin"]["pass"]:
        score += 30
    if results["kuchibashi"]["pass"]:
        score += 25
    if results["prev_high_break"]["pass"]:
        score += 15
    if results["round_number"]["pass"]:
        score += 10
    # 7の法則：下落後の反転初動（1〜3日上昇）ならボーナス
    if 1 <= rule7["up_count"] <= 3:
        score += 5
    # 7の法則：7日以上上昇で警告（減点）
    if rule7["up_count"] >= 7:
        score = max(score - 20, 0)

    score = min(score, 100)

    summary_parts = []
    if results["monoware_bull"]["pass"]:
        summary_parts.append("N大（ものわかれ）")
    if results["shitahanshin"]["pass"]:
        summary_parts.append("下半身")
    if results["kuchibashi"]["pass"]:
        summary_parts.append("逆くちばし")
    if results["prev_high_break"]["pass"]:
        summary_parts.append("前高値ブレイク")
    if results["rule_of_7"]["reversal_warning"]:
        summary_parts.append(f"⚠️{rule7['direction']}{rule7['count']}日")

    return {
        **results,
        "score": score,
        "summary": " / ".join(summary_parts),
    }
