#!/usr/bin/env python3
"""
バックテスト: 過去レースデータで予想精度を検証

Supabase への書き込みは一切行わない。
boatrace.jp から過去の出走表・展示情報・結果を取得し、
現在のスコアリングモデルで的中率・ROI を計算する。

Usage:
  python3 backtest.py                         # 過去30日・全18場
  python3 backtest.py --days 14               # 過去14日
  python3 backtest.py --start 2026-02-01 --end 2026-04-30
  python3 backtest.py --days 30 --workers 4   # 並列数を増やして高速化
  python3 backtest.py --days 7 --stadiums 08,12,22  # 特定の場のみ
"""

import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import fetch_races as _fetch_races_mod
import fetch_entries as _fetch_entries_mod
import fetch_exhibition as _fetch_exhibition_mod
import fetch_results as _fetch_results_mod

from fetch_races import fetch_race_list
from fetch_entries import fetch_entries
from fetch_exhibition import fetch_exhibition
from fetch_results import fetch_result
from scoring import score_entries, decide

# backtest では per-entry の詳細ログを抑制
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("fetch_exhibition").setLevel(logging.WARNING)
logging.getLogger("fetch_entries").setLevel(logging.WARNING)
logging.getLogger("fetch_results").setLevel(logging.WARNING)
logging.getLogger("fetch_races").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _patch_intervals(interval: float) -> None:
    """全 fetch モジュールの REQUEST_INTERVAL を上書きする（バックテスト高速化用）"""
    _fetch_races_mod.REQUEST_INTERVAL     = interval
    _fetch_entries_mod.REQUEST_INTERVAL   = interval
    _fetch_exhibition_mod.REQUEST_INTERVAL = interval
    _fetch_results_mod.REQUEST_INTERVAL   = interval
    logger.info("REQUEST_INTERVAL を %.1fs に設定", interval)

JST = timezone(timedelta(hours=9))

STADIUM_CODE_MAP = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
    "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
    "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24",
}
CODE_TO_NAME = {v: k for k, v in STADIUM_CODE_MAP.items()}
ALL_CODES = list(STADIUM_CODE_MAP.values())


@dataclass
class BtResult:
    race_date: str
    stadium: str
    race_no: int
    pick: str
    confidence: float
    decision: str
    is_watch: bool
    gap: float
    has_exhibition: bool
    hit: Optional[bool]    # None = 結果未取得
    payout: Optional[int]
    popularity: Optional[int]
    trifecta_result: Optional[str]


def _check_hit(pick: str, trifecta: str) -> bool:
    return set(pick.split("-")) == set(trifecta.split("-"))


def _process_race(code: str, name: str, race_no: int, target_date: date) -> Optional[BtResult]:
    """1レースの予想 + 結果を取得して BtResult を返す"""
    try:
        entries = fetch_entries(code, race_no, target_date)
        if not entries:
            return None

        condition = fetch_exhibition(code, race_no, target_date, entries)
        has_ex = any(e.exhibition_time is not None for e in entries)

        scores = score_entries(entries, condition)
        lane1_entry    = next((e for e in entries if e.lane == 1), None)
        lane1_approach = lane1_entry.approach_lane if lane1_entry else None
        pred = decide(scores, condition, lane1_approach=lane1_approach)

        res = fetch_result(code, race_no, target_date)
        hit = payout = popularity = trifecta = None
        if res and res.get("trifecta_result"):
            trifecta = res["trifecta_result"]
            hit = _check_hit(pred["pick"], trifecta)
            payout = res.get("payout")
            popularity = res.get("popularity")

        return BtResult(
            race_date=target_date.isoformat(),
            stadium=name,
            race_no=race_no,
            pick=pred["pick"],
            confidence=pred["confidence"],
            decision=pred["decision"],
            is_watch=pred.get("is_watch", False),
            gap=pred["gap"],
            has_exhibition=has_ex,
            hit=hit,
            payout=payout,
            popularity=popularity,
            trifecta_result=trifecta,
        )
    except Exception as e:
        logger.debug("処理失敗 %s %dR %s: %s", name, race_no, target_date, e)
        return None


def _process_day(target_date: date, stadium_codes: list[str], workers: int) -> list[BtResult]:
    """1日分を並列処理"""
    race_args: list[tuple] = []
    for code in stadium_codes:
        name = CODE_TO_NAME.get(code, code)
        try:
            races = fetch_race_list(code, target_date)
            if races:
                for r in races:
                    race_args.append((code, name, r["race_no"], target_date))
        except Exception:
            pass

    if not race_args:
        return []

    results: list[BtResult] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_process_race, *a) for a in race_args]
        for fut in as_completed(futs):
            r = fut.result()
            if r is not None:
                results.append(r)
    return results


def _roi_str(hits: list, total: int) -> str:
    """ROI 文字列を計算 (¥100 ベット換算)"""
    payouts = [r.payout for r in hits if r.payout]
    if not payouts or total == 0:
        return "N/A"
    avg_pay = sum(payouts) / len(payouts)
    # ¥100 賭けて avg_pay が返ってきたのが hit/total 回
    roi = (avg_pay * len(hits) / total - 100) / 100 * 100
    return f"{roi:+.1f}%"


def _print_report(results: list[BtResult], start: date, end: date) -> None:
    confirmed = [r for r in results if r.hit is not None]
    with_ex    = [r for r in results if r.has_exhibition]

    print()
    print("=" * 65)
    print("  バックテスト結果")
    print("=" * 65)
    print(f"  期間         : {start} 〜 {end}  ({(end-start).days+1}日間)")
    print(f"  総レース数   : {len(results):,}件")
    print(f"  結果確定     : {len(confirmed):,}件")
    print(f"  展示データあり: {len(with_ex):,}件  ({len(with_ex)/max(1,len(results))*100:.0f}%)")
    print()

    # ── 信頼度ブラケット別 ────────────────────────────────────────
    print("  【信頼度別 的中率・ROI】 (¥100ベット換算)")
    print(f"  {'閾値':<12} {'件数':>5} {'的中':>5} {'的中率':>7} {'平均払戻':>9} {'ROI':>8}")
    print("  " + "-" * 52)

    brackets = [
        ("conf ≥ 78", 78),
        ("conf ≥ 75", 75),
        ("conf ≥ 72", 72),
        ("conf ≥ 70", 70),
        ("conf ≥ 67", 67),
        ("conf ≥ 65", 65),
        ("conf ≥ 62", 62),
        ("conf ≥ 55", 55),
        ("全レース",   0),
    ]

    for label, thr in brackets:
        bucket = [r for r in confirmed if r.confidence >= thr]
        if len(bucket) < 5:
            continue
        hits = [r for r in bucket if r.hit]
        hit_rate = len(hits) / len(bucket) * 100
        payouts = [r.payout for r in hits if r.payout]
        avg_pay = sum(payouts) / len(payouts) if payouts else 0
        roi = _roi_str(hits, len(bucket))
        print(f"  {label:<12} {len(bucket):>5} {len(hits):>5} {hit_rate:>6.1f}% "
              f"{avg_pay:>8,.0f}円 {roi:>8}")

    # ── 判定別 ───────────────────────────────────────────────────
    print()
    print("  【判定別 結果】")
    for dec_label, dec_fn in [
        ("BUY",       lambda r: r.decision == "buy"),
        ("CANDIDATE", lambda r: r.decision == "candidate"),
        ("WATCH",     lambda r: r.decision == "skip" and r.is_watch),
        ("SKIP",      lambda r: r.decision == "skip" and not r.is_watch),
    ]:
        bucket = [r for r in confirmed if dec_fn(r)]
        if not bucket:
            continue
        hits = [r for r in bucket if r.hit]
        hit_rate = len(hits) / len(bucket) * 100
        payouts = [r.payout for r in hits if r.payout]
        avg_pay = sum(payouts) / len(payouts) if payouts else 0
        roi = _roi_str(hits, len(bucket))
        print(f"  {dec_label:<10}: {len(bucket):>4}件  的中{len(hits):>3}件  "
              f"({hit_rate:.1f}%)  平均払戻¥{avg_pay:,.0f}  ROI {roi}")

    # ── 最適閾値の提案 ────────────────────────────────────────────
    print()
    print("  【推奨閾値 (ROI最大化)】")
    best = {"buy": None, "candidate": None}
    best_roi = {"buy": -999.0, "candidate": -999.0}

    for thr in range(55, 90):
        bucket = [r for r in confirmed if r.confidence >= thr]
        if len(bucket) < 10:
            break
        hits = [r for r in bucket if r.hit]
        payouts = [r.payout for r in hits if r.payout]
        if not payouts:
            continue
        avg_pay = sum(payouts) / len(payouts)
        roi_val = avg_pay * len(hits) / len(bucket) - 100   # ¥100 ベット純利益

        if roi_val > best_roi["buy"]:
            best_roi["buy"] = roi_val
            best["buy"] = (thr, len(bucket), len(hits)/len(bucket)*100, avg_pay, roi_val)

    # candidate: ROI+で件数が一定以上
    for thr in range(55, 85):
        bucket = [r for r in confirmed if r.confidence >= thr]
        if len(bucket) < 20:
            break
        hits = [r for r in bucket if r.hit]
        payouts = [r.payout for r in hits if r.payout]
        if not payouts:
            continue
        avg_pay = sum(payouts) / len(payouts)
        roi_val = avg_pay * len(hits) / len(bucket) - 100
        if roi_val > 0 and roi_val > best_roi["candidate"]:
            best_roi["candidate"] = roi_val
            best["candidate"] = (thr, len(bucket), len(hits)/len(bucket)*100, avg_pay, roi_val)

    if best["buy"]:
        t, n, hr, ap, rv = best["buy"]
        print(f"  BUY閾値       : conf ≥ {t}  "
              f"(的中率{hr:.1f}%  平均払戻¥{ap:,.0f}  純利益+¥{rv:.0f}/¥100)  {n}件")
    if best["candidate"] and best["candidate"] != best["buy"]:
        t, n, hr, ap, rv = best["candidate"]
        print(f"  CANDIDATE閾値 : conf ≥ {t}  "
              f"(的中率{hr:.1f}%  平均払戻¥{ap:,.0f}  純利益+¥{rv:.0f}/¥100)  {n}件")

    print("=" * 65)
    print()

    # 閾値再設定コマンドを出力
    if best["buy"]:
        buy_thr = best["buy"][0]
        cand_thr = best["candidate"][0] if best["candidate"] else buy_thr - 8
        print("  ▼ scoring.py の閾値を以下に更新することを推奨:")
        print(f"  buy:       confidence ≥ {buy_thr} かつ gap ≥ 10")
        print(f"  candidate: confidence ≥ {cand_thr} かつ gap ≥ 7")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="バックテスト")
    parser.add_argument("--days", type=int, default=30,
                        help="過去何日分を検証 (デフォルト: 30)")
    parser.add_argument("--start", default=None, help="開始日 YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="終了日 YYYY-MM-DD (省略時: 昨日)")
    parser.add_argument("--workers", type=int, default=3,
                        help="並列ワーカー数 (デフォルト: 3)")
    parser.add_argument("--stadiums", default=None,
                        help="場コードをカンマ区切り 例: 08,12,22 (省略時: 全24場)")
    parser.add_argument("--interval", type=float, default=0.5,
                        help="HTTP リクエスト間スリープ秒 (デフォルト: 0.5 / 本番は 1.0〜2.0)")
    args = parser.parse_args()

    # バックテスト用に REQUEST_INTERVAL を一括設定
    _patch_intervals(args.interval)

    now_jst  = datetime.now(JST).date()
    yesterday = now_jst - timedelta(days=1)

    if args.start and args.end:
        start = date.fromisoformat(args.start)
        end   = date.fromisoformat(args.end)
    else:
        end   = yesterday
        start = end - timedelta(days=args.days - 1)

    stadium_codes = args.stadiums.split(",") if args.stadiums else ALL_CODES

    logger.info("=== バックテスト開始 ===")
    logger.info("期間: %s 〜 %s (%d日)", start, end, (end - start).days + 1)
    logger.info("対象場: %d場 / 並列ワーカー: %d / interval: %.1fs",
                len(stadium_codes), args.workers, args.interval)

    all_results: list[BtResult] = []
    total_days = (end - start).days + 1
    current = start

    while current <= end:
        day_num = (current - start).days + 1
        logger.info("[%d/%d] %s 処理中...", day_num, total_days, current)
        day_res = _process_day(current, stadium_codes, args.workers)
        all_results.extend(day_res)
        confirmed = sum(1 for r in day_res if r.hit is not None)
        hits = sum(1 for r in day_res if r.hit)
        logger.info("  → %d件取得  結果確定%d件  的中%d件", len(day_res), confirmed, hits)
        current += timedelta(days=1)

    logger.info("=== 全日程処理完了: %d件 ===", len(all_results))
    _print_report(all_results, start, end)


if __name__ == "__main__":
    main()
