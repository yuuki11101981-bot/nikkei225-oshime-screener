"""
新高値ブレイク｜待ちぶせ型エントリー前チェックリスト に基づくスクリーナー。

STEP1: 形（チャートパターン）
STEP2: 質（出来高）
STEP3: 地合い（日経トレンドは呼び出し元で確認）
STEP4: エントリー判断（ピボット・RR）
"""

import numpy as np
import pandas as pd


# ────────────────────────────────────────
# STEP 1: 形（チャートパターン）
# ────────────────────────────────────────

def check_near_52w_high(df: pd.DataFrame, threshold: float = 0.07) -> dict:
    """
    52週高値の7%以内にいるか（ブレイクアウト直前 or 直後）。
    上場来高値に近いほど戻り売りの壁がない。
    """
    high_52w = df["High"].tail(252).max()
    close = df["Close"].iloc[-1]
    pct_from_high = (high_52w - close) / high_52w * 100

    # ブレイク済み（高値更新）か直前かを判定
    is_breakout = close >= high_52w * 0.99
    is_near = pct_from_high <= threshold * 100

    return {
        "pass": bool(is_near or is_breakout),
        "high_52w": float(high_52w),
        "close": float(close),
        "pct_from_high": float(pct_from_high),
        "is_breakout": bool(is_breakout),
        "detail": f"52週高値比: -{pct_from_high:.1f}% {'【高値更新】' if is_breakout else ''}",
    }


def check_ma_alignment(df: pd.DataFrame) -> dict:
    """MA5 > MA25 > MA75 の上向き整列を確認する。"""
    row = df.iloc[-1]
    ma5 = row.get("MA5")
    ma25 = row.get("MA25")
    ma75 = row.get("MA75")

    if any(pd.isna(v) for v in [ma5, ma25, ma75]):
        return {"pass": False, "detail": "MA計算不足"}

    alignment_ok = ma5 > ma25 > ma75
    ma75_rising = df["MA75"].iloc[-1] > df["MA75"].iloc[-5]

    return {
        "pass": bool(alignment_ok and ma75_rising),
        "detail": "MA5>MA25>MA75 上向き" if alignment_ok and ma75_rising else "MA整列未完成",
    }


def check_base_quality(df: pd.DataFrame, base_period: int = 40) -> dict:
    """
    ベースの質：調整幅15〜35%以内でタイトに推移しているか。
    V字ではなく一定期間の横ばい（ベース）が形成されているか。
    """
    base = df["Close"].tail(base_period)
    high = base.max()
    low = base.min()
    depth_pct = (high - low) / high * 100

    # タイトなベース：調整幅が35%以内
    tight_enough = depth_pct <= 35

    # V字でないか：ベース期間内での最安値が前半にあるか（後半は戻している）
    half = len(base) // 2
    low_in_first_half = base.iloc[:half].min() <= base.iloc[half:].min() * 1.05
    not_v_shape = low_in_first_half  # 安値が前半にある = 後半は戻している

    # ベースが十分な期間継続しているか（最低3週間＝15日）
    sufficient_duration = base_period >= 15

    return {
        "pass": bool(tight_enough and not_v_shape),
        "depth_pct": float(depth_pct),
        "tight_enough": bool(tight_enough),
        "not_v_shape": bool(not_v_shape),
        "detail": f"ベース調整幅: {depth_pct:.1f}% {'(タイト)' if tight_enough else '(深すぎ)'}",
    }


def check_pivot(df: pd.DataFrame, lookback: int = 60) -> dict:
    """
    ピボット（ブレイクポイント）を特定する。
    直近lookback日の高値をピボットとし、現在値との位置関係を確認。
    """
    recent_high = df["High"].tail(lookback).max()
    close = df["Close"].iloc[-1]

    # 直近高値をブレイクしているか（1%超え）
    breakout = close > recent_high * 1.005

    # ブレイク後の押し目待ち（ピボットの3%以内に戻ってきている）
    near_pivot = (recent_high * 0.97) <= close <= (recent_high * 1.05)

    # ピボットから離れすぎ（5%超）→ 飛びつきリスク
    too_extended = close > recent_high * 1.08

    return {
        "pass": bool(near_pivot and not too_extended),
        "pivot": float(recent_high),
        "close": float(close),
        "breakout": bool(breakout),
        "near_pivot": bool(near_pivot),
        "too_extended": bool(too_extended),
        "pct_above_pivot": float((close - recent_high) / recent_high * 100),
        "detail": (
            "飛びつきリスク（ピボットから離れすぎ）" if too_extended
            else ("ピボット付近（待ちぶせ好機）" if near_pivot else "ピボット未到達")
        ),
    }


# ────────────────────────────────────────
# STEP 2: 質（出来高）
# ────────────────────────────────────────

def check_breakout_volume(df: pd.DataFrame, threshold: float = 1.5) -> dict:
    """
    ブレイク時の出来高が平常の1.5倍以上か。
    直近3日で最大出来高の日を「ブレイク日」と見なす。
    """
    if "VOL_MA" not in df.columns:
        return {"pass": False, "detail": "VOL_MA未計算"}

    vol_ma = df["VOL_MA"].iloc[-1]
    # 直近5日の最大出来高
    max_recent_vol = df["Volume"].tail(5).max()
    ratio = max_recent_vol / vol_ma if vol_ma > 0 else 0

    return {
        "pass": bool(ratio >= threshold),
        "vol_ratio": float(ratio),
        "detail": f"最大出来高比: {ratio:.1f}倍 {'(OK)' if ratio >= threshold else '(不足)'}",
    }


def check_accumulation(df: pd.DataFrame, period: int = 20) -> dict:
    """
    蓄積（玉集め）確認：上げる日の出来高 > 下げる日の出来高。
    """
    recent = df.tail(period)
    up_days = recent[recent["Close"] >= recent["Open"]]
    down_days = recent[recent["Close"] < recent["Open"]]

    up_vol = up_days["Volume"].sum()
    down_vol = down_days["Volume"].sum()

    ok = up_vol > down_vol
    ratio = float(up_vol / down_vol) if down_vol > 0 else float("inf")

    return {
        "pass": bool(ok),
        "up_vol": float(up_vol),
        "down_vol": float(down_vol),
        "ratio": min(ratio, 99.9),
        "detail": f"買い/売り出来高比: {min(ratio, 99.9):.2f} {'(蓄積あり)' if ok else '(分配優勢)'}",
    }


def check_base_volume_dry(df: pd.DataFrame, base_period: int = 20) -> dict:
    """
    ベース後半で出来高が枯れているか（売り疲れのサイン）。
    ベース後半の平均出来高が全体平均の85%未満であれば合格。
    """
    if "VOL_MA" not in df.columns:
        return {"pass": True, "detail": "VOL_MA未計算（スキップ）"}

    base_half = df["Volume"].tail(base_period // 2)
    vol_ma = df["VOL_MA"].iloc[-1]
    avg_ratio = base_half.mean() / vol_ma if vol_ma > 0 else 1.0

    dry = avg_ratio <= 0.9

    return {
        "pass": bool(dry),
        "avg_ratio": float(avg_ratio),
        "detail": f"ベース後半出来高: 平均の{avg_ratio*100:.0f}% {'(枯れ確認)' if dry else '(まだ高い)'}",
    }


# ────────────────────────────────────────
# STEP 4: リスクリワード計算
# ────────────────────────────────────────

def calc_risk_reward(df: pd.DataFrame, pivot: float) -> dict:
    """
    ピボットからのRR（リスクリワード）を計算する。
    ・損切り：ピボット-5%
    ・目標：ピボット+15%（最低目安）
    """
    close = df["Close"].iloc[-1]
    stop_loss = pivot * 0.95
    target = pivot * 1.15

    risk = close - stop_loss
    reward = target - close

    rr = reward / risk if risk > 0 else 0

    return {
        "rr": float(rr),
        "stop_loss": float(stop_loss),
        "target": float(target),
        "rr_ok": bool(rr >= 1.5),
        "detail": f"RR={rr:.1f} 損切={stop_loss:,.0f}円 目標={target:,.0f}円",
    }


# ────────────────────────────────────────
# 総合スコアリング
# ────────────────────────────────────────

def score_breakout(df: pd.DataFrame) -> dict:
    """
    高値ブレイク銘柄のスコアを計算する（0〜100点）。
    """
    results = {}
    results["near_high"] = check_near_52w_high(df)
    results["ma_alignment"] = check_ma_alignment(df)
    results["base_quality"] = check_base_quality(df)
    results["pivot"] = check_pivot(df)
    results["breakout_volume"] = check_breakout_volume(df)
    results["accumulation"] = check_accumulation(df)
    results["base_vol_dry"] = check_base_volume_dry(df)

    pivot_val = results["pivot"]["pivot"]
    results["risk_reward"] = calc_risk_reward(df, pivot_val)

    # 52週高値圏にいない → 対象外
    if not results["near_high"]["pass"]:
        return {**results, "score": 0, "summary": "52週高値圏外"}

    # MA整列が必須
    if not results["ma_alignment"]["pass"]:
        return {**results, "score": 0, "summary": "MA整列未完成"}

    # 飛びつきリスク → 除外
    if results["pivot"]["too_extended"]:
        return {**results, "score": 0, "summary": "ピボットから離れすぎ（飛びつきリスク）"}

    # スコア計算
    score = 0
    score += 25 if results["near_high"]["pass"] else 0       # 高値圏
    score += 20 if results["ma_alignment"]["pass"] else 0    # MA整列
    score += 15 if results["base_quality"]["pass"] else 0    # ベース質
    score += 15 if results["breakout_volume"]["pass"] else 0 # 出来高
    score += 10 if results["accumulation"]["pass"] else 0    # 蓄積
    score += 10 if results["base_vol_dry"]["pass"] else 0    # 枯れ
    score += 5  if results["risk_reward"]["rr_ok"] else 0    # RR

    # 全条件揃いボーナス
    all_pass = all([
        results["near_high"]["pass"],
        results["ma_alignment"]["pass"],
        results["base_quality"]["pass"],
        results["breakout_volume"]["pass"],
        results["accumulation"]["pass"],
    ])
    if all_pass:
        score = min(score + 5, 100)

    summary_parts = []
    if results["near_high"]["is_breakout"]:
        summary_parts.append("高値更新中")
    if results["pivot"]["near_pivot"]:
        summary_parts.append("ピボット付近")
    if results["breakout_volume"]["pass"]:
        summary_parts.append(f"出来高{results['breakout_volume']['vol_ratio']:.1f}倍")
    if results["accumulation"]["pass"]:
        summary_parts.append("蓄積あり")
    if results["risk_reward"]["rr_ok"]:
        summary_parts.append(f"RR={results['risk_reward']['rr']:.1f}")

    return {
        **results,
        "score": score,
        "summary": " / ".join(summary_parts) if summary_parts else "条件不足",
    }
