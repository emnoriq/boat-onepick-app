"""
data_health.py — データ品質監視スクリプト

以下を自動チェックして問題があれば警告を出す：
  1. 展示データ収集率（直近7日・30日）
  2. 予測的中率（直近30日）
  3. BUY予測件数・的中数
  4. 展示データが今日取れているか（pre_race_scan 後に呼ぶ想定）
  5. entries/races/predictions の整合性

使い方：
  python3 data_health.py              # 全チェック・サマリ表示
  python3 data_health.py --alert-only # 問題があるときだけ出力（GitHub Actions向け）
  python3 data_health.py --days 7     # 直近N日を対象
"""

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone

from db import get_client

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))


# ─────────────────────────────────────────────────────────────────────────────
# ヘルパー
# ─────────────────────────────────────────────────────────────────────────────

def _paginate(db, table: str, select: str, filters: list[tuple], limit=10000) -> list[dict]:
    """ページネーション付き全件取得"""
    rows, offset = [], 0
    while True:
        q = db.table(table).select(select)
        for col, op, val in filters:
            if op == "gte":   q = q.gte(col, val)
            elif op == "lte": q = q.lte(col, val)
            elif op == "eq":  q = q.eq(col, val)
            elif op == "not_is_null": q = q.not_.is_(col, "null")
        res = q.range(offset, offset + limit - 1).execute()
        rows.extend(res.data or [])
        if len(res.data or []) < limit:
            break
        offset += limit
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# チェック関数
# ─────────────────────────────────────────────────────────────────────────────

def check_exhibition_rate(db, days_short=7, days_long=30) -> dict:
    """展示データ収集率を確認"""
    today = date.today()

    results = {}
    for label, days in [("7日", days_short), ("30日", days_long)]:
        since = (today - timedelta(days=days)).isoformat()

        # 対象 entries 数
        races = _paginate(db, "races", "id", [("race_date", "gte", since)])
        race_ids = [r["id"] for r in races]
        if not race_ids:
            results[label] = {"total": 0, "with_exh": 0, "rate": 0.0}
            continue

        # 全 entries
        total_entries = _paginate(
            db, "entries", "id,exhibition_time",
            [("race_id", "gte", min(race_ids))]  # 近似フィルタ
        )
        # race_id でフィルタ（ページネーションの近似を補正）
        race_id_set = set(race_ids)
        target = [e for e in total_entries if e.get("race_id") in race_id_set]
        with_exh = [e for e in target if e.get("exhibition_time") is not None]

        rate = len(with_exh) / len(target) if target else 0.0
        results[label] = {
            "total": len(target),
            "with_exh": len(with_exh),
            "rate": rate,
        }

    return results


def check_today_exhibition(db) -> dict:
    """今日の展示データ取得状況"""
    today = date.today().isoformat()
    races = _paginate(db, "races", "id,stadium,race_no,status",
                      [("race_date", "eq", today)])

    # pre_race 対象（scheduled / running）
    target_races = [r for r in races if r["status"] in ("scheduled", "running", "closed")]
    if not target_races:
        return {"races": 0, "entries_total": 0, "entries_with_exh": 0, "rate": 0.0}

    race_ids = [r["id"] for r in target_races]
    race_id_set = set(race_ids)

    entries = _paginate(db, "entries", "race_id,lane,exhibition_time",
                        [("race_id", "gte", min(race_ids))])
    target_entries = [e for e in entries if e.get("race_id") in race_id_set]
    with_exh = [e for e in target_entries if e.get("exhibition_time") is not None]

    return {
        "races": len(target_races),
        "entries_total": len(target_entries),
        "entries_with_exh": len(with_exh),
        "rate": len(with_exh) / len(target_entries) if target_entries else 0.0,
    }


def check_prediction_accuracy(db, days=30) -> dict:
    """予測的中率を確認（BUY予測のみ）"""
    since = (date.today() - timedelta(days=days)).isoformat()

    predictions = _paginate(db, "predictions", "id,race_id,decision,pick,result_set,hit",
                            [("created_at", "gte", since + "T00:00:00")])

    buy_preds = [p for p in predictions if p.get("decision") == "BUY"]
    hits = [p for p in buy_preds if p.get("hit") is True]

    # 結果未確定を除く（hit が null でないもの）
    decided = [p for p in buy_preds if p.get("hit") is not None]
    hit_decided = [p for p in decided if p.get("hit") is True]

    return {
        "total_predictions": len(predictions),
        "buy_predictions": len(buy_preds),
        "decided": len(decided),
        "hits": len(hit_decided),
        "hit_rate": len(hit_decided) / len(decided) if decided else None,
        "break_even": 0.240,
    }


def check_data_gaps(db, days=7) -> dict:
    """races に対して predictions が欠けているケースを検出"""
    since = (date.today() - timedelta(days=days)).isoformat()

    races = _paginate(db, "races", "id,race_date,stadium,race_no,status",
                      [("race_date", "gte", since)])
    finished = [r for r in races if r["status"] in ("closed", "finished", "done")]

    if not finished:
        return {"races_finished": 0, "missing_prediction": 0, "missing_result": 0}

    race_ids = set(r["id"] for r in finished)

    predictions = _paginate(db, "predictions", "race_id",
                            [("race_id", "gte", min(race_ids))])
    pred_ids = set(p["race_id"] for p in predictions if p.get("race_id") in race_ids)

    results_rows = _paginate(db, "results", "race_id",
                             [("race_id", "gte", min(race_ids))])
    result_ids = set(r["race_id"] for r in results_rows if r.get("race_id") in race_ids)

    missing_pred = race_ids - pred_ids
    missing_result = race_ids - result_ids

    return {
        "races_finished": len(finished),
        "missing_prediction": len(missing_pred),
        "missing_result": len(missing_result),
    }


# ─────────────────────────────────────────────────────────────────────────────
# レポート出力
# ─────────────────────────────────────────────────────────────────────────────

def run_health_check(alert_only: bool = False, days: int = 30) -> int:
    """
    全チェックを実行して結果を表示。
    戻り値: 問題があれば 1、なければ 0
    """
    db = get_client()
    issues = []
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")

    print(f"\n{'='*60}")
    print(f"  データ品質レポート  {now}")
    print(f"{'='*60}")

    # ── 1. 展示データ収集率 ──────────────────────────────────────
    print("\n【展示データ収集率】")
    exh = check_exhibition_rate(db)
    for label, stat in exh.items():
        rate_pct = stat["rate"] * 100
        mark = "✅" if rate_pct >= 50 else ("⚠️ " if rate_pct >= 10 else "❌")
        print(f"  {mark} 直近{label}: {rate_pct:.1f}%  "
              f"({stat['with_exh']}/{stat['total']} entries)")
        if rate_pct < 10 and stat["total"] > 0:
            issues.append(f"展示データ収集率が低すぎます（直近{label}: {rate_pct:.1f}%）")

    # ── 2. 今日の展示データ ─────────────────────────────────────
    print("\n【今日の展示データ】")
    today_exh = check_today_exhibition(db)
    if today_exh["entries_total"] > 0:
        rate_pct = today_exh["rate"] * 100
        mark = "✅" if rate_pct >= 50 else ("⚠️ " if rate_pct >= 10 else "❌")
        print(f"  {mark} {rate_pct:.1f}%  "
              f"({today_exh['entries_with_exh']}/{today_exh['entries_total']} entries, "
              f"{today_exh['races']} races)")
        if rate_pct < 5 and today_exh["entries_total"] >= 6:
            issues.append(f"今日の展示データがほぼ取れていません（{rate_pct:.1f}%）")
    else:
        print("  ℹ️  今日のレースデータなし（まだスキャン前か休場日）")

    # ── 3. 予測的中率 ────────────────────────────────────────────
    print(f"\n【BUY予測 的中率（直近{days}日）】")
    acc = check_prediction_accuracy(db, days=days)
    if acc["decided"] >= 5:
        rate_pct = (acc["hit_rate"] or 0) * 100
        be_pct = acc["break_even"] * 100
        diff = rate_pct - be_pct
        mark = "✅" if diff >= 0 else ("⚠️ " if diff >= -5 else "❌")
        print(f"  {mark} 的中率: {rate_pct:.1f}%  "
              f"(損益分岐 {be_pct:.1f}%, 差: {diff:+.1f}pt)")
        print(f"     BUY: {acc['buy_predictions']}件 / 結果確定: {acc['decided']}件 / 的中: {acc['hits']}件")
        if rate_pct < be_pct - 5:
            issues.append(
                f"的中率が損益分岐を大幅に下回っています（{rate_pct:.1f}% vs {be_pct:.1f}%）"
            )
    else:
        print(f"  ℹ️  BUY結果確定 {acc['decided']}件（統計判断には30件以上必要）")
        print(f"     総予測: {acc['total_predictions']}件 / BUY: {acc['buy_predictions']}件")

    # ── 4. データ欠落チェック ────────────────────────────────────
    print(f"\n【データ欠落（直近{min(days,7)}日）】")
    gaps = check_data_gaps(db, days=min(days, 7))
    print(f"  終了レース: {gaps['races_finished']}件")
    if gaps["missing_prediction"] > 0:
        print(f"  ❌ prediction 欠落: {gaps['missing_prediction']}件")
        issues.append(f"prediction が存在しないレースが {gaps['missing_prediction']}件あります")
    else:
        print(f"  ✅ prediction: 欠落なし")
    if gaps["missing_result"] > 0:
        print(f"  ⚠️  result 欠落: {gaps['missing_result']}件（集計待ちの可能性あり）")
    else:
        print(f"  ✅ result: 欠落なし")

    # ── サマリ ───────────────────────────────────────────────────
    print(f"\n{'='*60}")
    if issues:
        print(f"  ⚠️  {len(issues)}件の問題が検出されました:")
        for i, issue in enumerate(issues, 1):
            print(f"     {i}. {issue}")
        print(f"{'='*60}\n")
        return 1
    else:
        if not alert_only:
            print("  ✅ 全チェック正常")
        print(f"{'='*60}\n")
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="データ品質監視")
    parser.add_argument("--alert-only", action="store_true",
                        help="問題があるときだけ出力する")
    parser.add_argument("--days", type=int, default=30,
                        help="集計対象の直近N日 (default: 30)")
    parser.add_argument("--exit-code", action="store_true",
                        help="問題があれば exit code 1 で終了（CI向け）")
    args = parser.parse_args()

    exit_code = run_health_check(alert_only=args.alert_only, days=args.days)

    if args.exit_code and exit_code != 0:
        sys.exit(exit_code)
