#!/usr/bin/env python3
"""
システムヘルスチェック

毎週 weekly_optimize.yml から実行される。
以下を確認し、問題があれば exit(1) して GitHub Actions を失敗させる
→ GitHub の「失敗時メール通知」が届く。

チェック項目:
  1. result_scan の停滞: is_hit=NULL が直近7日に多すぎないか
  2. データ蓄積状況: 直近7日の predictions 件数 (スキャンが止まっていないか)
  3. BUY実績サマリー: 直近30日の的中率・ROI を表示 (ログ確認用)
"""

import os
import sys
import logging
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))
from db import get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# ── 閾値 ──────────────────────────────────────────────────────────────────────
MAX_PENDING_RATIO   = 0.50   # 直近7日で is_hit=NULL が全体の50%超 → 警告
MIN_WEEKLY_SCANS    = 50     # 直近7日で 50件未満 → スキャン停止疑い
CRITICAL_THRESHOLD  = 0.80   # 直近7日で NULL が 80%超 → ERROR (exit 1)


def main() -> None:
    JST = timezone(timedelta(hours=9))
    today = datetime.now(JST).date()
    week_ago  = (today - timedelta(days=7)).isoformat()
    month_ago = (today - timedelta(days=30)).isoformat()

    db = get_client()
    has_error = False

    # ── 1. 直近7日の race_ids を取得 ─────────────────────────────────────────
    race_rows = (db.table("races").select("id")
                 .gte("race_date", week_ago)
                 .execute().data or [])
    recent_race_ids = {r["id"] for r in race_rows}
    logger.info("直近7日のレース数: %d件", len(recent_race_ids))

    # ── 2. 直近7日の predictions 件数チェック ────────────────────────────────
    if len(recent_race_ids) == 0:
        logger.error("❌ 直近7日のレースデータが0件 — スキャンが止まっている可能性")
        has_error = True
    else:
        preds_rows = []
        for i in range(0, len(recent_race_ids), 200):
            chunk = list(recent_race_ids)[i:i+200]
            batch = (db.table("predictions").select("race_id,is_hit,decision")
                     .in_("race_id", chunk).execute().data or [])
            preds_rows.extend(batch)

        total   = len(preds_rows)
        pending = sum(1 for p in preds_rows if p.get("is_hit") is None)
        buys    = sum(1 for p in preds_rows if p.get("decision") == "buy")

        logger.info("直近7日 predictions: 計%d件 / BUY=%d件 / is_hit未確定=%d件",
                    total, buys, pending)

        if total < MIN_WEEKLY_SCANS:
            logger.warning("⚠️ 直近7日の予想が%d件 (最低%d件) — morning_scan が止まっている可能性",
                           total, MIN_WEEKLY_SCANS)
            has_error = True

        if total > 0:
            ratio = pending / total
            if ratio >= CRITICAL_THRESHOLD:
                logger.error(
                    "❌ is_hit未確定率 %.0f%% (閾値%.0f%%) — result_scan が長期停止中",
                    ratio * 100, CRITICAL_THRESHOLD * 100
                )
                has_error = True
            elif ratio >= MAX_PENDING_RATIO:
                logger.warning(
                    "⚠️ is_hit未確定率 %.0f%% (閾値%.0f%%) — result_scan の遅延を確認",
                    ratio * 100, MAX_PENDING_RATIO * 100
                )

    # ── 3. 直近30日 BUY実績サマリー ───────────────────────────────────────────
    race_30d = (db.table("races").select("id")
                .gte("race_date", month_ago)
                .execute().data or [])
    race_ids_30d = {r["id"] for r in race_30d}

    buy_rows = []
    for i in range(0, len(race_ids_30d), 200):
        chunk = list(race_ids_30d)[i:i+200]
        batch = (db.table("predictions")
                 .select("race_id,decision,is_hit")
                 .in_("race_id", chunk)
                 .eq("decision", "buy")
                 .not_.is_("is_hit", "null")
                 .execute().data or [])
        buy_rows.extend(batch)

    if buy_rows:
        n_buy  = len(buy_rows)
        n_hit  = sum(1 for r in buy_rows if r.get("is_hit"))
        hit_rate = n_hit / n_buy if n_buy else 0.0

        # 払戻データ取得
        buy_race_ids = list({r["race_id"] for r in buy_rows})
        payout_map: dict[str, int] = {}
        for i in range(0, len(buy_race_ids), 200):
            chunk = buy_race_ids[i:i+200]
            res_rows = (db.table("results").select("race_id,payout")
                        .in_("race_id", chunk).execute().data or [])
            for rr in res_rows:
                if rr.get("payout"):
                    payout_map[rr["race_id"]] = int(rr["payout"])

        total_return = sum(
            payout_map.get(r["race_id"], 0)
            for r in buy_rows if r.get("is_hit")
        )
        roi = (total_return - n_buy * 100) / (n_buy * 100) if n_buy else 0.0

        logger.info("=" * 50)
        logger.info("【直近30日 BUY実績】")
        logger.info("  BET数   : %d件", n_buy)
        logger.info("  的中数  : %d件", n_hit)
        logger.info("  的中率  : %.1f%%", hit_rate * 100)
        logger.info("  ROI     : %+.1f%%", roi * 100)
        logger.info("=" * 50)
    else:
        logger.info("直近30日 BUYデータなし (まだデータ蓄積中)")

    # ── 結果 ──────────────────────────────────────────────────────────────────
    if has_error:
        logger.error("❌ ヘルスチェック失敗 — GitHub通知を確認してください")
        sys.exit(1)
    else:
        logger.info("✅ ヘルスチェック正常")


if __name__ == "__main__":
    main()
