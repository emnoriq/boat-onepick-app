#!/usr/bin/env python3
"""
朝スコア重み最適化スクリプト

Supabase の過去レースデータ（entries + results）を使って
morning_score 各成分の重みを scipy.optimize で最適化する。

最適化対象パラメータ (6個):
  w_player : 選手力 (級別 + 全国3連対率 + ボート率)
  w_motor  : モーター評価
  w_lane   : 枠スコア
  w_course : コース適性
  w_st     : スタート力
  w_local  : 当地相性

目標関数: 三連複的中率（上位3艇 == 実際の3着内3艇）の最大化

Usage:
  cd scraper && python3 optimize_weights.py
  cd scraper && python3 optimize_weights.py --method nelder-mead
  cd scraper && python3 optimize_weights.py --days 30   # 直近30日のみ
"""

import argparse
import sys
import os
import time
import logging
from datetime import date, datetime, timezone, timedelta

import numpy as np
from scipy import optimize as scipy_opt
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from db import get_client
from scoring import (
    EntryData, RaceCondition,
    _class_score, _national_top3_score, _local_top3_score,
    _motor_score, _boat_rate_score, _lane_score, _st_score,
    _course_affinity_score, _local_rate_score,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


# ── データ取得 ────────────────────────────────────────────────────────────────

def pull_dataset(db, days: int | None = None):
    """
    (entries_list, actual_set) のリストを返す。

    actual_set: trifecta_result から作った艇番セット (例: {'1','2','3'})
    entries_list: そのレースの全エントリdictリスト
    """
    logger.info("データ取得開始...")

    # ── 結果テーブルを全件取得（ページネーション）
    results_raw = []
    offset = 0
    while True:
        batch = (db.table("results")
                 .select("race_id,trifecta_result")
                 .range(offset, offset + 999)
                 .execute().data)
        if not batch:
            break
        results_raw.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    logger.info("results: %d件", len(results_raw))

    # 有効な trifecta_result のみ
    valid_results = {
        r["race_id"]: set(r["trifecta_result"].split("-"))
        for r in results_raw
        if r.get("trifecta_result") and "-" in r["trifecta_result"]
    }

    # 日付フィルタ
    if days is not None:
        JST = timezone(timedelta(hours=9))
        cutoff = (datetime.now(JST).date() - timedelta(days=days)).isoformat()
        races_raw = []
        offset = 0
        while True:
            batch = (db.table("races")
                     .select("id,race_date")
                     .gte("race_date", cutoff)
                     .range(offset, offset + 999)
                     .execute().data)
            if not batch:
                break
            races_raw.extend(batch)
            if len(batch) < 1000:
                break
            offset += 1000
        recent_ids = {r["id"] for r in races_raw}
        valid_results = {k: v for k, v in valid_results.items() if k in recent_ids}
        logger.info("日付フィルタ後: %d件 (直近%d日)", len(valid_results), days)

    race_id_list = list(valid_results.keys())
    logger.info("有効レース数: %d件", len(race_id_list))

    # ── entries を一括取得（50件ずつ）
    entries_by_race: dict[str, list[dict]] = {}
    for i in range(0, len(race_id_list), 50):
        chunk = race_id_list[i:i + 50]
        batch = (db.table("entries")
                 .select("*")
                 .in_("race_id", chunk)
                 .execute().data)
        for e in batch:
            rid = e["race_id"]
            entries_by_race.setdefault(rid, []).append(e)

    logger.info("entries 取得完了: %d艇", sum(len(v) for v in entries_by_race.values()))

    # ── データセット構築
    dataset = []
    for race_id, actual_set in valid_results.items():
        entries = entries_by_race.get(race_id, [])
        if len(entries) >= 4:  # 最低4艇必要
            dataset.append((entries, actual_set))

    logger.info("最終データセット: %d件", len(dataset))
    return dataset


# ── 単一エントリのスコア計算（パラメータ可変）────────────────────────────────

def score_entry(e: dict, params: np.ndarray, fleet_avg_motor: float) -> float:
    """パラメータ付きで1艇のスコアを計算する。"""
    w_player, w_motor, w_lane, w_course, w_st, w_local = params

    # 選手力
    player = min(20.0,
        _class_score(e.get("racer_class", "B1"))
        + _national_top3_score(e.get("national_top3_rate", 0.0) or 0.0)
        + min(3.0, _boat_rate_score(e.get("boat_rate", 0.0) or 0.0))
    )

    # モーター（艦隊相対評価）
    motor = _motor_score(e.get("motor_rate", 40.0) or 40.0, fleet_avg_motor)

    # 枠スコア
    lane_val = _lane_score(e.get("lane", 4))

    # コース適性
    entry_obj = EntryData(
        lane=e.get("lane", 4),
        racer_name="",
        c1_win_rate=e.get("c1_win_rate") or 0.0,
        c2_win_rate=e.get("c2_win_rate") or 0.0,
        c3_win_rate=e.get("c3_win_rate") or 0.0,
        c4_win_rate=e.get("c4_win_rate") or 0.0,
        c5_win_rate=e.get("c5_win_rate") or 0.0,
        c6_win_rate=e.get("c6_win_rate") or 0.0,
    )
    course = _course_affinity_score(entry_obj, e.get("lane", 4))

    # スタート力
    st = _st_score(
        e.get("avg_st") or 0.15,
        e.get("f_count") or 0,
        e.get("l_count") or 0,
    )

    # 当地相性
    local_top3 = e.get("local_top3_rate") or 0.0
    if local_top3 > 0:
        local = _local_top3_score(local_top3)
    else:
        local = _local_rate_score(e.get("local_win_rate") or 0.0)

    return (w_player * player + w_motor * motor + w_lane * lane_val
            + w_course * course + w_st * st + w_local * local)


# ── 目標関数 ─────────────────────────────────────────────────────────────────

def hit_rate(params: np.ndarray, dataset: list) -> float:
    """三連複的中率（負値で返す＝最小化で最大化）。"""
    hits = 0
    for entries, actual_set in dataset:
        motor_rates = [e.get("motor_rate") or 40.0 for e in entries]
        fleet_avg = sum(motor_rates) / len(motor_rates)

        scored = [(str(e.get("lane")), score_entry(e, params, fleet_avg))
                  for e in entries]
        scored.sort(key=lambda x: -x[1])
        top3 = {s[0] for s in scored[:3]}

        if top3 == actual_set:
            hits += 1

    return -hits / len(dataset) if dataset else 0.0


# ── ベースライン評価 ──────────────────────────────────────────────────────────

def evaluate(params: np.ndarray, dataset: list, label: str) -> float:
    rate = -hit_rate(params, dataset)
    logger.info("[%s] 三連複的中率: %.1f%% (%d/%d件)",
                label, rate * 100, int(rate * len(dataset)), len(dataset))
    return rate


# ── メイン ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=["de", "nelder-mead"], default="de",
                        help="最適化手法: de=differential_evolution(推奨), nelder-mead")
    parser.add_argument("--days", type=int, default=None,
                        help="直近N日のみ使用 (省略時: 全件)")
    parser.add_argument("--train-ratio", type=float, default=0.8,
                        help="学習データ比率 (default: 0.8)")
    args = parser.parse_args()

    db = get_client()
    dataset = pull_dataset(db, days=args.days)

    if len(dataset) < 50:
        logger.error("データが少なすぎます (%d件)。終了。", len(dataset))
        sys.exit(1)

    # ── 学習/検証 分割（シャッフル）
    rng = np.random.default_rng(42)
    indices = rng.permutation(len(dataset))
    split = int(len(dataset) * args.train_ratio)
    train_idx, test_idx = indices[:split], indices[split:]
    train = [dataset[i] for i in train_idx]
    test  = [dataset[i] for i in test_idx]
    logger.info("Train: %d件 / Test: %d件", len(train), len(test))

    # ── 現在の重み（全て1.0）でベースライン計測
    current_params = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    logger.info("=== ベースライン ===")
    train_base = evaluate(current_params, train, "train-baseline")
    test_base  = evaluate(current_params, test,  "test-baseline")

    # ── 最適化
    bounds = [(0.1, 4.0)] * 6  # 各重み: 0.1〜4.0倍
    param_names = ["w_player", "w_motor", "w_lane", "w_course", "w_st", "w_local"]

    logger.info("=== 最適化開始 (method=%s) ===", args.method)
    t0 = time.monotonic()

    if args.method == "de":
        result = scipy_opt.differential_evolution(
            hit_rate, bounds, args=(train,),
            maxiter=200, seed=42, tol=1e-4,
            popsize=15, mutation=(0.5, 1.0), recombination=0.7,
            callback=lambda xk, convergence: logger.info(
                "  DE iteration: hit_rate=%.2f%%", -hit_rate(xk, train) * 100
            ) if False else None,  # verbose=Falseでコールバック無効
            disp=False,
        )
    else:  # nelder-mead
        result = scipy_opt.minimize(
            hit_rate, current_params, args=(train,),
            method="Nelder-Mead",
            options={"maxiter": 5000, "xatol": 1e-4, "fatol": 1e-5, "disp": True},
        )

    elapsed = time.monotonic() - t0
    logger.info("最適化完了: %.1f秒", elapsed)

    opt_params = result.x

    # ── 最適化後の評価
    logger.info("=== 最適化結果 ===")
    train_opt = evaluate(opt_params, train, "train-optimized")
    test_opt  = evaluate(opt_params, test,  "test-optimized")

    logger.info("=== ベースライン vs 最適化 ===")
    logger.info("Train: %.1f%% → %.1f%% (Δ%+.1f%%)",
                train_base * 100, train_opt * 100, (train_opt - train_base) * 100)
    logger.info("Test:  %.1f%% → %.1f%% (Δ%+.1f%%)",
                test_base * 100, test_opt * 100, (test_opt - test_base) * 100)

    # ── 最適重みの表示（scoring.py 更新用）
    logger.info("=== 最適重み (scoring.py 更新用) ===")
    for name, val in zip(param_names, opt_params):
        logger.info("  %-12s = %.4f", name, val)

    # ── scoring.py への反映提案
    logger.info("=== scoring.py 反映案 ===")
    suggestions = []
    component_maxpts = {
        "w_player": 20.0, "w_motor": 15.0, "w_lane": 8.0,
        "w_course": 7.0,  "w_st": 10.0,   "w_local": 10.0,
    }
    for name, val in zip(param_names, opt_params):
        orig_max = component_maxpts[name]
        new_max = orig_max * val
        direction = "↑強化" if val > 1.2 else ("↓軽減" if val < 0.8 else "≈維持")
        suggestions.append(f"  {name}: ×{val:.2f} → 実効最大値 {orig_max:.0f}pt → {new_max:.1f}pt  {direction}")
        logger.info(suggestions[-1])

    # ── Test改善が 0.5% 以上あれば scoring.py を自動更新する提案
    improvement = test_opt - test_base
    if improvement >= 0.005:
        logger.info("")
        logger.info("✅ テストデータで %.1f%% 改善。scoring.py の重みを更新することを推奨。", improvement * 100)
        logger.info("   → python3 optimize_weights.py --apply で自動適用 (未実装: 手動で確認後に適用)")
    elif improvement > 0:
        logger.info("△ 改善幅が小さい (%.2f%%)。現状維持を推奨。", improvement * 100)
    else:
        logger.info("❌ 最適化でテスト性能が改善しませんでした。過学習の可能性あり。")

    return opt_params, test_opt


if __name__ == "__main__":
    main()
