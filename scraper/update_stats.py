#!/usr/bin/env python3
"""
DB実績から stadium_stats.json を自動更新するスクリプト。

処理内容:
  1. Supabase の races + results + predictions + entries を集計
  2. 場別・1号艇クラス別の三連複的中率を計算
  3. 全体平均との比較で confidence 乗数を決定
  4. scraper/stadium_stats.json を上書き保存

使い方:
  cd scraper && python3 update_stats.py           # 全期間
  cd scraper && python3 update_stats.py --days 90 # 直近90日

GitHub Actions weekly_optimize.yml から自動実行される。
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from math import sqrt

from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))
from db import get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

STATS_PATH = os.path.join(os.path.dirname(__file__), "stadium_stats.json")
MIN_SAMPLE_STADIUM = 30   # 場別: この件数未満は初期値を維持
MIN_SAMPLE_CLASS   = 20   # クラス別: この件数未満は初期値を維持
OVERALL_FALLBACK   = 0.186
BUY_INELIGIBLE_TH  = 0.160


def _conf_mul_from_rate(hit_rate: float, overall: float) -> float:
    """
    的中率から confidence 乗数を計算する。

    設計:
      overall     → ×1.00 (基準)
      +10%以上     → 最大 ×1.08
      -10%以上悪い → 最小 ×0.80
    """
    ratio = hit_rate / overall if overall > 0 else 1.0
    # ratio=1.0→×1.0, ratio=1.5→×1.08, ratio=0.5→×0.80 にクリップ
    mul = 1.0 + (ratio - 1.0) * 0.16
    return round(min(1.12, max(0.78, mul)), 3)


def compute_stats(db, days: int | None = None) -> dict:
    """
    DB から統計を計算して stats dict を返す。
    """
    JST = timezone(timedelta(hours=9))
    now_jst = datetime.now(JST)

    # ── 対象レースIDを取得 ──────────────────────────────────────────────────
    if days:
        cutoff = (now_jst.date() - timedelta(days=days)).isoformat()
        races_raw = []
        offset = 0
        while True:
            batch = (db.table("races")
                     .select("id,stadium,race_date")
                     .gte("race_date", cutoff)
                     .range(offset, offset + 999)
                     .execute().data)
            if not batch:
                break
            races_raw.extend(batch)
            if len(batch) < 1000:
                break
            offset += 1000
    else:
        races_raw = []
        offset = 0
        while True:
            batch = (db.table("races")
                     .select("id,stadium,race_date")
                     .range(offset, offset + 999)
                     .execute().data)
            if not batch:
                break
            races_raw.extend(batch)
            if len(batch) < 1000:
                break
            offset += 1000

    race_id_to_stadium = {r["id"]: r["stadium"] for r in races_raw}
    race_ids = list(race_id_to_stadium.keys())
    logger.info("対象レース: %d件", len(race_ids))

    # ── results を一括取得 ──────────────────────────────────────────────────
    results_map: dict[str, dict] = {}
    for i in range(0, len(race_ids), 50):
        chunk = race_ids[i:i + 50]
        batch = (db.table("results")
                 .select("race_id,trifecta_result,prediction_hit")
                 .in_("race_id", chunk)
                 .execute().data)
        for r in batch:
            results_map[r["race_id"]] = r

    # ── predictions を一括取得 (1号艇クラス取得用に pick も) ────────────────
    preds_map: dict[str, dict] = {}
    for i in range(0, len(race_ids), 50):
        chunk = race_ids[i:i + 50]
        batch = (db.table("predictions")
                 .select("race_id,pick,is_hit")
                 .in_("race_id", chunk)
                 .execute().data)
        for p in batch:
            preds_map[p["race_id"]] = p

    # ── entries (lane=1) の racer_class を取得 ─────────────────────────────
    lane1_class_map: dict[str, str] = {}
    for i in range(0, len(race_ids), 50):
        chunk = race_ids[i:i + 50]
        batch = (db.table("entries")
                 .select("race_id,lane,racer_class")
                 .in_("race_id", chunk)
                 .eq("lane", 1)
                 .execute().data)
        for e in batch:
            lane1_class_map[e["race_id"]] = e.get("racer_class") or ""

    # ── 集計 ──────────────────────────────────────────────────────────────
    stadium_counts: dict[str, dict] = {}  # {stadium: {hits, total}}
    class_counts:   dict[str, dict] = {}  # {class: {hits, total}}

    for race_id, result in results_map.items():
        stadium = race_id_to_stadium.get(race_id, "")
        if not stadium:
            continue

        is_hit = bool(result.get("prediction_hit"))

        # 場別
        if stadium not in stadium_counts:
            stadium_counts[stadium] = {"hits": 0, "total": 0}
        stadium_counts[stadium]["total"] += 1
        if is_hit:
            stadium_counts[stadium]["hits"] += 1

        # 1号艇クラス別
        lane1_cls = lane1_class_map.get(race_id, "")
        if lane1_cls:
            if lane1_cls not in class_counts:
                class_counts[lane1_cls] = {"hits": 0, "total": 0}
            class_counts[lane1_cls]["total"] += 1
            if is_hit:
                class_counts[lane1_cls]["hits"] += 1

    total_hits  = sum(v["hits"]  for v in stadium_counts.values())
    total_total = sum(v["total"] for v in stadium_counts.values())
    overall = total_hits / total_total if total_total > 0 else OVERALL_FALLBACK
    logger.info("全体的中率: %.1f%% (%d/%d)", overall * 100, total_hits, total_total)

    # ── 場別 stats 構築 ────────────────────────────────────────────────────
    # 既存 JSON の初期値を読み込んで base とする
    try:
        with open(STATS_PATH, encoding="utf-8") as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing = {"stadiums": {}, "lane1_class": {}}

    stadiums_out: dict[str, dict] = {}
    all_stadiums = set(list(existing.get("stadiums", {}).keys()) + list(stadium_counts.keys()))
    for stadium in sorted(all_stadiums):
        counts = stadium_counts.get(stadium)
        if counts and counts["total"] >= MIN_SAMPLE_STADIUM:
            hit_rate = counts["hits"] / counts["total"]
            mul      = _conf_mul_from_rate(hit_rate, overall)
            sample   = counts["total"]
        else:
            # データ不足 → 既存値を保持
            prev = existing.get("stadiums", {}).get(stadium, {})
            hit_rate = float(prev.get("hit_rate", OVERALL_FALLBACK))
            mul      = float(prev.get("conf_mul", 1.0))
            sample   = int(prev.get("sample", 0))
        stadiums_out[stadium] = {
            "hit_rate": round(hit_rate, 4),
            "conf_mul": mul,
            "sample":   sample,
        }
        logger.info("  %s: %.1f%% (n=%d) mul=×%.3f%s",
                    stadium, hit_rate * 100, sample, mul,
                    " [低精度]" if hit_rate < BUY_INELIGIBLE_TH and sample >= MIN_SAMPLE_STADIUM else "")

    # ── クラス別 stats 構築 ────────────────────────────────────────────────
    class_out: dict[str, dict] = {}
    all_classes = set(list(existing.get("lane1_class", {}).keys()) + list(class_counts.keys()))
    for cls in sorted(all_classes):
        counts = class_counts.get(cls)
        if counts and counts["total"] >= MIN_SAMPLE_CLASS:
            hit_rate = counts["hits"] / counts["total"]
            mul      = _conf_mul_from_rate(hit_rate, overall)
            sample   = counts["total"]
        else:
            prev = existing.get("lane1_class", {}).get(cls, {})
            hit_rate = float(prev.get("hit_rate", OVERALL_FALLBACK))
            mul      = float(prev.get("conf_mul", 1.0))
            sample   = int(prev.get("sample", 0))
        class_out[cls] = {
            "hit_rate": round(hit_rate, 4),
            "conf_mul": mul,
            "sample":   sample,
        }
        logger.info("  1号艇%s級: %.1f%% (n=%d) mul=×%.3f",
                    cls, hit_rate * 100, sample, mul)

    return {
        "_comment":      "update_stats.py が DB 実績から自動生成。手動編集不要。",
        "_updated_at":   now_jst.strftime("%Y-%m-%d %H:%M JST"),
        "_sample_races": total_total,
        "_overall_hit_rate": round(overall, 4),
        "stadiums":      stadiums_out,
        "lane1_class":   class_out,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=None,
                        help="直近N日のみ集計 (省略時: 全件)")
    args = parser.parse_args()

    db = get_client()
    stats = compute_stats(db, days=args.days)

    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    logger.info("stadium_stats.json を更新しました: %s", STATS_PATH)
    logger.info("対象レース数: %d / 場数: %d / クラス数: %d",
                stats["_sample_races"],
                len(stats["stadiums"]),
                len(stats["lane1_class"]))


if __name__ == "__main__":
    main()
