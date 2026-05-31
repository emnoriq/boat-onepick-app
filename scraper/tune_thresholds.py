#!/usr/bin/env python3
"""
BUY判定閾値の自動チューニングスクリプト

Supabase の過去 predictions (best_ev, confidence, is_hit) と
results (payout) を使って、EVモードの BUY/CANDIDATE 閾値を最適化する。

最適化目標: ROI (投資対利益率) = (払戻合計 - 投資額合計) / 投資額合計

データ要件:
  - predictions.best_ev     : EVモードで実行されたレースに記録される
  - predictions.is_hit      : result_scan 後に確定する
  - predictions.confidence  : 全レースで記録される
  - results.payout          : 的中時の払戻金額 (¥/¥100賭け)

Usage:
  cd scraper && python3 tune_thresholds.py
  cd scraper && python3 tune_thresholds.py --days 90 --save
  cd scraper && python3 tune_thresholds.py --min-bets 20 --save
  cd scraper && python3 tune_thresholds.py --days 60 --min-bets 15 --save --verbose
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))
from db import get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

_DIR = os.path.dirname(__file__)
THRESHOLDS_PATH = os.path.join(_DIR, "thresholds.json")

# ── デフォルト閾値（初回 / データ不足時のフォールバック）──────────────────────
THRESHOLDS_DEFAULT: dict = {
    "_comment": "tune_thresholds.py が自動生成。scoring.py の decide() で適用される。",
    "updated_at":       None,
    # EV モード閾値 (pre_race_scan でオッズが取得できた場合)
    "ev_buy":           0.25,   # EV > この値 かつ conf >= conf_buy → BUY
    "ev_buy_max":       0.50,   # EV がこの値以上は逆選択リスク → CANDIDATE止まり
                                # 実績: EV>0.5 → 的中率5.2%, EV 0.25-0.5 → 的中率30%
    "conf_buy":         68.0,   # confidence 閾値 (EVモード BUY)
    "ev_cand":          0.15,   # EV > この値 → CANDIDATE
    "conf_cand":        65.0,   # confidence 閾値 (EVモード CANDIDATE)
    # スコアモード閾値 (朝スキャン / オッズ未取得時)
    "score_buy_conf":   70.0,   # confidence ≥ この値 かつ gap ≥ score_buy_gap → BUY
    "score_buy_gap":    10.0,
    "score_cand_conf":  62.0,   # CANDIDATE 閾値
    "score_cand_gap":    7.0,
    # チューニング結果メタ情報
    "sample_n":         None,
    "hit_rate":         None,
    "roi":              None,
}


def _load_thresholds() -> dict:
    """thresholds.json を読み込む。存在しなければ DEFAULT を返す。"""
    try:
        with open(THRESHOLDS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(THRESHOLDS_DEFAULT)


# ── データ取得 ─────────────────────────────────────────────────────────────────

def pull_data(db, days: int | None = None) -> tuple[list[dict], dict[str, int]]:
    """
    is_hit が確定済みかつ best_ev が記録されている predictions と
    対応する results (payout) を返す。

    Returns:
        preds: list of {race_id, best_ev, confidence, gap, is_hit, pick, decision}
        payout_map: {race_id: payout}  ← 的中時の払戻額 (¥/¥100賭け)
    """
    JST = timezone(timedelta(hours=9))

    # ── 日付フィルタ用 race_ids ───────────────────────────────────────────────
    race_id_filter: set[str] | None = None
    if days is not None:
        cutoff = (datetime.now(JST).date() - timedelta(days=days)).isoformat()
        ids: list[str] = []
        offset = 0
        while True:
            batch = (db.table("races").select("id")
                     .gte("race_date", cutoff)
                     .range(offset, offset + 999).execute().data)
            if not batch:
                break
            ids.extend(r["id"] for r in batch)
            if len(batch) < 1000:
                break
            offset += 1000
        race_id_filter = set(ids)
        logger.info("直近 %d日 レース: %d件", days, len(race_id_filter))

    # ── predictions 取得 (is_hit 確定 + best_ev 記録済みのみ) ─────────────────
    preds: list[dict] = []
    offset = 0
    while True:
        batch = (db.table("predictions")
                 .select("race_id,best_ev,confidence,gap,is_hit,pick,decision")
                 .not_.is_("is_hit",   "null")
                 .not_.is_("best_ev",  "null")
                 .range(offset, offset + 999)
                 .execute().data)
        if not batch:
            break
        preds.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    if race_id_filter is not None:
        preds = [p for p in preds if p["race_id"] in race_id_filter]

    logger.info("予想データ (is_hit確定 + best_ev記録): %d件", len(preds))

    # ── results (payout) 一括取得 ────────────────────────────────────────────
    race_ids = list({p["race_id"] for p in preds})
    payout_map: dict[str, int] = {}
    CHUNK = 200
    for i in range(0, len(race_ids), CHUNK):
        chunk = race_ids[i:i + CHUNK]
        rows = (db.table("results")
                .select("race_id,payout")
                .in_("race_id", chunk)
                .execute().data or [])
        for r in rows:
            val = r.get("payout")
            if val is not None:
                payout_map[r["race_id"]] = int(val)

    logger.info("払戻データ取得: %d件 / %d件", len(payout_map), len(race_ids))
    return preds, payout_map


# ── グリッドサーチ ──────────────────────────────────────────────────────────────

def grid_search(
    preds: list[dict],
    payout_map: dict[str, int],
    min_bets: int = 10,
) -> tuple[dict | None, list[dict]]:
    """
    EV下限閾値 × EV上限キャップ × confidence閾値 のグリッドサーチ。

    実績: EV>0.5 → 的中率5.2% (逆選択), EV 0.25-0.5 → 的中率30.0% (有効)
    → EV上限キャップ (ev_buy_max) を導入して高EV逆選択を排除する

    ROI = (払戻合計 - 投資額合計) / 投資額合計

    Returns:
        best_result (dict or None): ROI最大の閾値組み合わせ
        all_results (list[dict]):   全探索結果 (ROI降順)
    """
    # グリッド定義
    # ev_max は「逆選択リスクの安全上限」であり 0.50 を超えてはならない。
    # 実績: EV>0.5 → 的中率5.2% (市場が正しく「来ない」と評価した組み合わせ)。
    # 少数サンプルだと grid search が高EV域の見かけ上の高ROIを拾い、
    # この安全キャップを自動で無効化してしまう (逆選択バグの再発)。
    # → グリッド上限を 0.50 に固定し、最適化が安全域を超えられないようにする。
    ev_min_grid = [round(x * 0.025, 3) for x in range(0, 17)]    # 0.000 〜 0.400
    ev_max_grid = [round(0.30 + x * 0.05, 2) for x in range(5)]  # 0.30 〜 0.50 (安全上限・固定)
    conf_grid   = [round(55.0 + x * 2.5, 1) for x in range(13)]  # 55.0 〜 85.0

    all_results: list[dict] = []

    for ev_min in ev_min_grid:
        for ev_max in ev_max_grid:
            if ev_max <= ev_min:
                continue
            for conf_t in conf_grid:
                bets = [
                    (bool(p["is_hit"]), payout_map.get(p["race_id"], 0))
                    for p in preds
                    if (p.get("best_ev") is not None
                        and ev_min <= p["best_ev"] <= ev_max
                        and p.get("confidence") is not None
                        and p["confidence"] >= conf_t)
                ]
                n = len(bets)
                if n < min_bets:
                    continue

                hit_count = sum(1 for hit, _ in bets if hit)
                hit_rate  = hit_count / n

                # ROI 計算 (¥100 ベット換算)
                total_return = sum((pay if hit else 0) for hit, pay in bets)
                roi = (total_return - n * 100) / (n * 100)

                all_results.append({
                    "ev_t":     ev_min,
                    "ev_max":   ev_max,
                    "conf_t":   conf_t,
                    "n":        n,
                    "hit_rate": round(hit_rate, 4),
                    "roi":      round(roi, 4),
                })

    if not all_results:
        return None, []

    all_results.sort(key=lambda x: x["roi"], reverse=True)
    return all_results[0], all_results


# ── メイン ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="BUY判定閾値チューニング")
    parser.add_argument("--days",     type=int,  default=None,
                        help="直近 N日のみ使用 (省略時: 全件)")
    parser.add_argument("--min-bets", type=int,  default=10,
                        help="有効とする最低 BET 数 (デフォルト: 10)")
    parser.add_argument("--save",     action="store_true",
                        help="thresholds.json に書き込む")
    parser.add_argument("--verbose",  action="store_true",
                        help="グリッドサーチ全結果を表示")
    args = parser.parse_args()

    db = get_client()
    preds, payout_map = pull_data(db, days=args.days)

    if len(preds) < args.min_bets:
        logger.warning(
            "データが少なすぎます (%d件, 最低 %d件必要)。チューニングをスキップします。",
            len(preds), args.min_bets,
        )
        return

    # ── is_hit=True でも payout が 0 の件数を警告 ─────────────────────────────
    missing_pay = sum(
        1 for p in preds
        if p.get("is_hit") and payout_map.get(p["race_id"], 0) == 0
    )
    if missing_pay:
        logger.warning("is_hit=True で払戻不明: %d件 (ROI が過小評価される可能性)", missing_pay)

    logger.info("=== グリッドサーチ開始 (min_bets=%d) ===", args.min_bets)
    best, all_results = grid_search(preds, payout_map, min_bets=args.min_bets)

    if not best:
        logger.warning("有効な閾値組み合わせが見つかりませんでした。デフォルト閾値を維持します。")
        return

    # ── 結果レポート ──────────────────────────────────────────────────────────
    top_n = all_results if args.verbose else all_results[:10]
    logger.info("=== グリッドサーチ結果 (上位%d) ===", len(top_n))
    logger.info("%-7s %-7s %-6s  %5s  %7s  %8s", "EV≥", "EV≤", "conf≥", "件数", "的中率", "ROI")
    for r in top_n:
        logger.info("%.3f   %.2f   %-6.1f  %5d  %6.1f%%  %+7.1f%%",
                    r["ev_t"], r.get("ev_max", 9.99), r["conf_t"], r["n"],
                    r["hit_rate"] * 100, r["roi"] * 100)

    logger.info("=== 最良閾値 ===")
    logger.info("  ev_buy        : %.3f", best["ev_t"])
    logger.info("  ev_buy_max    : %.2f",  best.get("ev_max", 0.50))
    logger.info("  conf_threshold: %.1f",  best["conf_t"])
    logger.info("  BET数         : %d",    best["n"])
    logger.info("  的中率        : %.1f%%", best["hit_rate"] * 100)
    logger.info("  ROI           : %+.1f%%", best["roi"] * 100)

    # ── 現在の閾値との比較 ───────────────────────────────────────────────────
    current = _load_thresholds()
    cur_ev      = current.get("ev_buy",     0.25)
    cur_ev_max  = current.get("ev_buy_max", 0.50)
    cur_conf    = current.get("conf_buy",  68.0)
    logger.info("=== 現在の閾値 vs 最良閾値 ===")
    logger.info("  ev_buy     : %.3f → %.3f", cur_ev,     best["ev_t"])
    logger.info("  ev_buy_max : %.2f  → %.2f",  cur_ev_max, best.get("ev_max", 0.50))
    logger.info("  conf_buy   : %.1f → %.1f",   cur_conf,   best["conf_t"])

    if args.save:
        data = _load_thresholds()
        JST  = timezone(timedelta(hours=9))
        data["ev_buy"]     = best["ev_t"]
        data["ev_buy_max"] = best.get("ev_max", 0.50)
        data["conf_buy"]   = best["conf_t"]
        data["updated_at"] = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
        data["sample_n"]   = best["n"]
        data["hit_rate"]   = best["hit_rate"]
        data["roi"]        = best["roi"]
        with open(THRESHOLDS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("✅ thresholds.json を保存しました: %s", THRESHOLDS_PATH)
    else:
        logger.info("(--save なし: thresholds.json は更新しません)")


if __name__ == "__main__":
    main()
