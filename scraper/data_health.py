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

def _paginate(db, table: str, select: str, filters: list[tuple], limit=1000) -> list[dict]:
    """ページネーション付き全件取得（date/status 等の通常カラム用）"""
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


def _count_entries_by_race_ids(db, race_ids: list[str], with_exh: bool = False) -> int:
    """race_ids を200件ずつチャンクして entries 件数を COUNT で取得（メモリ効率版）"""
    if not race_ids:
        return 0
    total = 0
    CHUNK = 200
    for i in range(0, len(race_ids), CHUNK):
        chunk = race_ids[i:i + CHUNK]
        q = db.table("entries").select("id", count="exact").in_("race_id", chunk)
        if with_exh:
            q = q.not_.is_("exhibition_time", "null")
        res = q.execute()
        total += res.count or 0
    return total


def _fetch_race_ids_since(db, since_date: str) -> list[str]:
    """指定日以降の race_id を全件取得"""
    ids, offset = [], 0
    while True:
        batch = (db.table("races").select("id")
                 .gte("race_date", since_date)
                 .range(offset, offset + 999).execute().data)
        if not batch:
            break
        ids.extend(r["id"] for r in batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return ids


# ─────────────────────────────────────────────────────────────────────────────
# チェック関数
# ─────────────────────────────────────────────────────────────────────────────

def check_exhibition_rate(db, days_short=7, days_long=30) -> dict:
    """展示データ収集率を確認（COUNT クエリで効率よく集計）"""
    today = date.today()
    results = {}
    for label, days in [("7日", days_short), ("30日", days_long)]:
        since = (today - timedelta(days=days)).isoformat()
        race_ids = _fetch_race_ids_since(db, since)
        if not race_ids:
            results[label] = {"total": 0, "with_exh": 0, "rate": 0.0}
            continue
        total   = _count_entries_by_race_ids(db, race_ids, with_exh=False)
        with_exh = _count_entries_by_race_ids(db, race_ids, with_exh=True)
        rate = with_exh / total if total else 0.0
        results[label] = {"total": total, "with_exh": with_exh, "rate": rate}
    return results


def check_today_exhibition(db) -> dict:
    """今日の展示データ取得状況"""
    today = date.today().isoformat()
    races = _paginate(db, "races", "id,stadium,race_no,status",
                      [("race_date", "eq", today)])

    # scheduled (朝スキャン後) または final (展示取得済み)
    target_races = [r for r in races
                    if r["status"] in ("scheduled", "final", "finished")]
    if not target_races:
        return {"races": 0, "entries_total": 0, "entries_with_exh": 0, "rate": 0.0}

    race_ids = [r["id"] for r in target_races]
    total    = _count_entries_by_race_ids(db, race_ids, with_exh=False)
    with_exh = _count_entries_by_race_ids(db, race_ids, with_exh=True)

    return {
        "races": len(target_races),
        "entries_total": total,
        "entries_with_exh": with_exh,
        "rate": with_exh / total if total else 0.0,
    }


def check_prediction_accuracy(db, days=30) -> dict:
    """予測的中率を確認（BUY予測のみ）"""
    since = (date.today() - timedelta(days=days)).isoformat()

    # decision は DB では小文字 "buy" で保存されている
    # is_hit カラムで的中判定（旧コードの "hit" は誤りだった）
    predictions = _paginate(db, "predictions", "id,race_id,decision,pick,is_hit",
                            [("created_at", "gte", since + "T00:00:00")])

    buy_preds  = [p for p in predictions if p.get("decision") == "buy"]
    decided    = [p for p in buy_preds   if p.get("is_hit") is not None]
    hit_decided = [p for p in decided    if p.get("is_hit") is True]

    return {
        "total_predictions": len(predictions),
        "buy_predictions":   len(buy_preds),
        "decided":           len(decided),
        "hits":              len(hit_decided),
        "hit_rate":          len(hit_decided) / len(decided) if decided else None,
        "break_even":        0.150,   # 平均払戻¥677なら損益分岐は約14.8%
    }


def check_data_gaps(db, days=7) -> dict:
    """races に対して predictions / results が欠けているケースを検出"""
    since = (date.today() - timedelta(days=days)).isoformat()

    races = _paginate(db, "races", "id,race_date,stadium,race_no,status",
                      [("race_date", "gte", since)])
    # "finished" = 結果取得済み。"final" = 直前スキャン済みだがまだ結果なし
    finished = [r for r in races if r["status"] == "finished"]

    if not finished:
        return {"races_finished": 0, "missing_prediction": 0, "missing_result": 0}

    race_ids = [r["id"] for r in finished]
    race_id_set = set(race_ids)
    CHUNK = 200

    # predictions の有無を chunk で確認
    pred_ids: set[str] = set()
    for i in range(0, len(race_ids), CHUNK):
        chunk = race_ids[i:i + CHUNK]
        rows = db.table("predictions").select("race_id").in_("race_id", chunk).execute().data
        pred_ids.update(r["race_id"] for r in (rows or []))

    # results の有無を chunk で確認
    result_ids: set[str] = set()
    for i in range(0, len(race_ids), CHUNK):
        chunk = race_ids[i:i + CHUNK]
        rows = db.table("results").select("race_id").in_("race_id", chunk).execute().data
        result_ids.update(r["race_id"] for r in (rows or []))

    return {
        "races_finished":    len(finished),
        "missing_prediction": len(race_id_set - pred_ids),
        "missing_result":     len(race_id_set - result_ids),
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
        if rate_pct < 5 and stat["total"] > 0:
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
