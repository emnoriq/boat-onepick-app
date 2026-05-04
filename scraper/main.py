"""
メインエントリポイント
コマンドライン引数で処理モードを切り替える:
  morning   - 朝スキャン (出走表 + 仮スコア)
  pre_race  - 直前スキャン (展示 + 最終判定)
  result    - 結果スキャン (的中判定)
"""

import argparse
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone, timedelta
from typing import Optional

from dotenv import load_dotenv
load_dotenv()  # ローカル実行時に .env を読み込む

from db import (get_client, upsert_race, upsert_entry, upsert_prediction,
                upsert_result, get_open_races, get_races_near_close,
                bulk_upsert_races, bulk_upsert_entries, bulk_upsert_predictions,
                get_race_ids_with_entries,
                mark_race_final, mark_race_finished)
from fetch_races import fetch_today_schedule, fetch_race_list
from fetch_entries import fetch_entries
from fetch_exhibition import fetch_exhibition
from fetch_results import fetch_result
from scoring import score_entries, decide, RaceCondition, EntryData

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

# ── 並列フェッチ設定 ─────────────────────────────────────────────
# 18場 × 12R = 216レースを直列処理すると 11s/R × 216 ≈ 41分かかる。
# race_list を 4並列、entries を 5並列にすることで ≈ 8-10分に短縮。
MAX_RACE_LIST_WORKERS = 4   # fetch_race_list 並列数 (18場 / 4 ≒ 5バッチ)
MAX_ENTRY_WORKERS     = 5   # fetch_entries  並列数 (216R / 5 ≒ 44バッチ)


def _fetch_race_list_worker(args: tuple) -> tuple:
    """Thread worker: 1場のレース一覧を取得して (code, name, races) を返す"""
    code, name, today = args
    try:
        races = fetch_race_list(code, today)
        return (code, name, races or [])
    except Exception as e:
        logger.error("fetch_race_list失敗 %s: %s", name, e)
        return (code, name, [])


def _fetch_entry_worker(args: tuple) -> tuple:
    """Thread worker: 1レースの出走表取得 & スコア計算を行い結果を返す"""
    code, name, race_no, race_id, today = args
    try:
        entry_list = fetch_entries(code, race_no, today)
        if not entry_list:
            return (name, race_no, race_id, None, None)
        scores = score_entries(entry_list, RaceCondition())
        return (name, race_no, race_id, entry_list, scores)
    except Exception as e:
        logger.error("fetch_entries失敗 %s %dR: %s", name, race_no, e)
        return (name, race_no, race_id, None, None)


def morning_scan(today: date,
                 stadium_filter: Optional[str] = None,
                 limit_races: Optional[int] = None) -> None:
    """
    朝スキャン: 出走表取得 & 仮スコア計算

    高速化ポイント (v2):
      - fetch_race_list を全場 MAX_RACE_LIST_WORKERS で並列取得
      - fetch_entries を全レース MAX_ENTRY_WORKERS で並列取得
      - entries / predictions を全場まとめて一括 upsert (各1 API call)
      - 既存 entries チェックも全場まとめて1 API call

    Args:
        stadium_filter: 指定場のみ処理 (例: "常滑"). None で全場.
        limit_races:    処理するレース数の上限 (手動テスト用).
    """
    scan_start = time.monotonic()
    db = get_client()

    # ── Phase 1: 開催場一覧取得 ──────────────────────────────────
    t0 = time.monotonic()
    stadiums = fetch_today_schedule(today)
    t_p1 = time.monotonic() - t0

    if stadium_filter:
        stadiums = [s for s in stadiums if s["stadium"] == stadium_filter]
        if not stadiums:
            logger.warning("指定場 '%s' が本日の開催場に見つかりません", stadium_filter)
            return

    logger.info("=== Morning Scan 開始 %s ===", today.isoformat())
    logger.info("開催場: %d場%s", len(stadiums),
                f" (フィルタ: {stadium_filter})" if stadium_filter else "")
    logger.info("[P1] 開催場一覧取得: %.1f秒", t_p1)

    # ── Phase 2: 全場のレース一覧を並列取得 ──────────────────────
    t0 = time.monotonic()
    code_map = {s["stadium"]: s["stadium_code"] for s in stadiums}
    race_list_args = [(s["stadium_code"], s["stadium"], today) for s in stadiums]
    stadium_races: dict[str, list[dict]] = {}  # stadium_name → races

    with ThreadPoolExecutor(max_workers=MAX_RACE_LIST_WORKERS) as pool:
        futs = {pool.submit(_fetch_race_list_worker, a): a for a in race_list_args}
        for fut in as_completed(futs):
            code, name, races = fut.result()
            if races:
                stadium_races[name] = races

    t_p2 = time.monotonic() - t0
    total_races_count = sum(len(r) for r in stadium_races.values())
    logger.info("[P2] レース一覧取得 (%d場, 並列%d): %.1f秒 → %d件",
                len(stadium_races), MAX_RACE_LIST_WORKERS, t_p2, total_races_count)

    # ── races upsert ペイロードを全場分まとめて組み立て ───────────
    all_races_payload: list[dict] = []
    for name, races in stadium_races.items():
        for r in races:
            try:
                close_dt = datetime.strptime(
                    f"{today.isoformat()} {r['close_time_str']}", "%Y-%m-%d %H:%M"
                ).replace(tzinfo=JST).astimezone(timezone.utc)
            except ValueError:
                continue
            all_races_payload.append({
                "race_date": today.isoformat(),
                "stadium": name,
                "race_no": r["race_no"],
                "close_time": close_dt.isoformat(),
                "status": "scheduled",
            })

    # ── Phase 3: races を全場まとめて一括 upsert ─────────────────
    t0 = time.monotonic()
    saved_races = bulk_upsert_races(db, all_races_payload)
    t_p3 = time.monotonic() - t0

    race_key_to_id: dict[tuple, str] = {
        (row["stadium"], row["race_no"]): row["id"] for row in saved_races
    }
    logger.info("[P3] races upsert (%d件): %.1f秒", len(saved_races), t_p3)

    # ── Phase 4: 既存 entries チェック (全場一括 1 API call) ──────
    t0 = time.monotonic()
    all_race_ids = [row["id"] for row in saved_races]
    existing_ids = get_race_ids_with_entries(db, all_race_ids)
    t_p4 = time.monotonic() - t0
    logger.info("[P4] entries既存確認 (スキップ:%d/%d): %.1f秒",
                len(existing_ids), len(all_race_ids), t_p4)

    # ── fetch タスク一覧を組み立て ────────────────────────────────
    fetch_tasks: list[tuple] = []
    for name, races in stadium_races.items():
        code = code_map[name]
        for r in races:
            race_id = race_key_to_id.get((name, r["race_no"]))
            if not race_id or race_id in existing_ids:
                continue
            fetch_tasks.append((code, name, r["race_no"], race_id, today))

    if limit_races is not None and len(fetch_tasks) > limit_races:
        fetch_tasks = fetch_tasks[:limit_races]
        logger.info("--limit-races %d 適用 → %d件に絞り込み",
                    limit_races, len(fetch_tasks))

    logger.info("fetch対象: %d件 / スキップ(既存): %d件",
                len(fetch_tasks), len(existing_ids))

    if not fetch_tasks:
        logger.info("取得対象なし。Morning Scan 終了。")
        _log_phase_summary(scan_start, t_p1, t_p2, t_p3, t_p4, 0.0, 0.0, 0.0,
                           len(stadiums), 0, 0, 0, len(existing_ids))
        return

    # ── Phase 5: 出走表を全レース並列取得 ────────────────────────
    t0 = time.monotonic()
    all_entries_payload: list[dict] = []
    all_predictions_payload: list[dict] = []
    fetch_ok = 0
    fetch_ng = 0

    with ThreadPoolExecutor(max_workers=MAX_ENTRY_WORKERS) as pool:
        futs = {pool.submit(_fetch_entry_worker, task): task for task in fetch_tasks}
        done = 0
        for fut in as_completed(futs):
            name, race_no, race_id, entry_list, scores = fut.result()
            done += 1

            if entry_list is None:
                fetch_ng += 1
                logger.warning("  [%d/%d] %s %dR: 出走表取得失敗",
                               done, len(fetch_tasks), name, race_no)
                continue

            score_map = {s.lane: s.total for s in scores}
            all_entries_payload.extend([
                {
                    "race_id": race_id,
                    "lane": e.lane,
                    "racer_name": e.racer_name,
                    "racer_class": e.racer_class,
                    "national_win_rate": e.national_win_rate,
                    "local_win_rate": e.local_win_rate,
                    "motor_rate": e.motor_rate,
                    "boat_rate": e.boat_rate,
                    "avg_st": e.avg_st,
                    "entry_score": score_map.get(e.lane),
                }
                for e in entry_list
            ])

            pred = decide(scores, RaceCondition())
            all_predictions_payload.append({
                "race_id": race_id,
                "pick": pred["pick"],
                "confidence": pred["confidence"],
                "decision": pred["decision"],
                "reason": "\n".join(pred["reason"]),
            })
            fetch_ok += 1

            # 20件ごとに進捗ログ
            if done % 20 == 0 or done == len(fetch_tasks):
                logger.info("  出走表取得: %d/%d完了 (成功:%d 失敗:%d)",
                            done, len(fetch_tasks), fetch_ok, fetch_ng)

    t_p5 = time.monotonic() - t0
    logger.info("[P5] 出走表取得 (成功:%d 失敗:%d, 並列%d): %.1f秒",
                fetch_ok, fetch_ng, MAX_ENTRY_WORKERS, t_p5)

    # ── Phase 6: entries を全場まとめて一括 upsert ───────────────
    t0 = time.monotonic()
    if all_entries_payload:
        bulk_upsert_entries(db, all_entries_payload)
    t_p6 = time.monotonic() - t0
    logger.info("[P6] entries upsert (%d件): %.1f秒",
                len(all_entries_payload), t_p6)

    # ── Phase 7: predictions を全場まとめて一括 upsert ───────────
    t0 = time.monotonic()
    if all_predictions_payload:
        bulk_upsert_predictions(db, all_predictions_payload)
    t_p7 = time.monotonic() - t0
    logger.info("[P7] predictions upsert (%d件): %.1f秒",
                len(all_predictions_payload), t_p7)

    _log_phase_summary(scan_start, t_p1, t_p2, t_p3, t_p4, t_p5, t_p6, t_p7,
                       len(stadiums), len(saved_races),
                       len(all_entries_payload), len(all_predictions_payload),
                       len(existing_ids))


def _log_phase_summary(scan_start: float,
                       t_p1: float, t_p2: float, t_p3: float, t_p4: float,
                       t_p5: float, t_p6: float, t_p7: float,
                       stadiums: int, races: int,
                       entries: int, predictions: int, skipped: int) -> None:
    """フェーズ別処理時間のサマリをログ出力"""
    total = time.monotonic() - scan_start
    logger.info("=== Morning Scan 完了 ===")
    logger.info("開催場:%d / races:%d / entries:%d / predictions:%d / スキップ:%d",
                stadiums, races, entries, predictions, skipped)
    logger.info("--- フェーズ別処理時間 ---")
    logger.info("  [P1] 開催場一覧取得  : %6.1f秒", t_p1)
    logger.info("  [P2] レース一覧取得  : %6.1f秒  (並列%d)", t_p2, MAX_RACE_LIST_WORKERS)
    logger.info("  [P3] races upsert   : %6.1f秒", t_p3)
    logger.info("  [P4] entries既存確認 : %6.1f秒", t_p4)
    logger.info("  [P5] 出走表取得      : %6.1f秒  (並列%d)", t_p5, MAX_ENTRY_WORKERS)
    logger.info("  [P6] entries保存     : %6.1f秒", t_p6)
    logger.info("  [P7] predictions保存 : %6.1f秒", t_p7)
    logger.info("  合計                 : %6.0f秒  (%.1f分)",
                total, total / 60)


def pre_race_scan(today: date, minutes_before: int = 10) -> None:
    """直前スキャン: 展示取得 & 最終判定"""
    scan_start = time.monotonic()
    db = get_client()
    races = get_races_near_close(db, today, minutes_before)
    logger.info("=== Pre-Race Scan 開始 ===")
    logger.info("締切%d分前対象: %dレース", minutes_before, len(races))

    exhibition_ok = 0
    conf_updated  = 0
    counts = {"buy": 0, "candidate": 0, "skip": 0}

    for race in races:
        race_id = race["id"]
        stadium = race["stadium"]
        race_no = race["race_no"]

        entries_data = (db.table("entries")
                        .select("*")
                        .eq("race_id", race_id)
                        .execute().data)

        entries = [EntryData(
            lane=e["lane"],
            racer_name=e["racer_name"],
            racer_class=e.get("racer_class") or "",
            national_win_rate=e.get("national_win_rate") or 0.0,
            local_win_rate=e.get("local_win_rate") or 0.0,
            motor_rate=e.get("motor_rate") or 0.0,
            boat_rate=e.get("boat_rate") or 0.0,
            avg_st=e.get("avg_st") or 0.15,
        ) for e in entries_data]

        stadium_code = _stadium_name_to_code(stadium)
        condition = fetch_exhibition(stadium_code, race_no, today, entries)

        ex_count = sum(1 for e in entries if e.exhibition_time is not None)
        if ex_count > 0:
            exhibition_ok += 1

        scores = score_entries(entries, condition)
        score_map = {s.lane: s.total for s in scores}

        for e in entries:
            upsert_entry(db, race_id, {
                "lane": e.lane,
                "racer_name": e.racer_name,
                "exhibition_time": e.exhibition_time,
                "exhibition_st": e.exhibition_st,
                "approach_lane": e.approach_lane,
                "entry_score": score_map.get(e.lane),
            })

        result = decide(scores, condition)
        upsert_prediction(db, race_id, {
            "pick": result["pick"],
            "confidence": result["confidence"],
            "decision": result["decision"],
            "reason": "\n".join(result["reason"]),
        })
        mark_race_final(db, race_id)
        conf_updated += 1
        counts[result["decision"]] = counts.get(result["decision"], 0) + 1
        logger.info("%s %dR 最終判定: %s %s (信頼度: %.1f)",
                    stadium, race_no, result["decision"],
                    result["pick"], result["confidence"])

    elapsed = time.monotonic() - scan_start
    logger.info("=== Pre-Race Scan 完了 ===")
    logger.info("対象: %dレース / 展示取得成功: %d / confidence更新: %d",
                len(races), exhibition_ok, conf_updated)
    logger.info("buy: %d / candidate: %d / skip: %d / 経過: %.0f秒",
                counts["buy"], counts["candidate"], counts["skip"], elapsed)


def pre_race_scan_single(today: date, stadium_name: str, race_no: int) -> None:
    """指定レース1本の直前情報を強制取得 (手動テスト用)"""
    db = get_client()

    res = (db.table("races").select("*")
           .eq("race_date", today.isoformat())
           .eq("stadium", stadium_name)
           .eq("race_no", race_no)
           .execute())
    if not res.data:
        logger.error("レースが見つかりません: %s %dR %s", stadium_name, race_no, today)
        logger.info("DBに登録済みの場を確認してください (morning_scan が必要な場合あり)")
        return

    race = res.data[0]
    race_id = race["id"]
    logger.info("=== %s %dR 直前情報テスト取得 ===", stadium_name, race_no)

    entries_data = (db.table("entries")
                    .select("*")
                    .eq("race_id", race_id)
                    .order("lane")
                    .execute().data)
    if not entries_data:
        logger.error("entries が空です。morning_scan を先に実行してください。")
        return

    entries = [EntryData(
        lane=e["lane"],
        racer_name=e["racer_name"],
        racer_class=e.get("racer_class") or "",
        national_win_rate=e.get("national_win_rate") or 0.0,
        local_win_rate=e.get("local_win_rate") or 0.0,
        motor_rate=e.get("motor_rate") or 0.0,
        boat_rate=e.get("boat_rate") or 0.0,
        avg_st=e.get("avg_st") or 0.15,
    ) for e in entries_data]

    stadium_code = _stadium_name_to_code(stadium_name)
    condition = fetch_exhibition(stadium_code, race_no, today, entries)

    extime_count = sum(1 for e in entries if e.exhibition_time is not None)
    if extime_count == 0:
        logger.warning("展示タイムが取得できませんでした (レースがまだ先の可能性があります)")

    scores = score_entries(entries, condition)
    score_map = {s.lane: s.total for s in scores}

    for e in entries:
        upsert_entry(db, race_id, {
            "lane": e.lane,
            "racer_name": e.racer_name,
            "exhibition_time": e.exhibition_time,
            "exhibition_st": e.exhibition_st,
            "approach_lane": e.approach_lane,
            "entry_score": score_map.get(e.lane),
        })

    result = decide(scores, condition)
    upsert_prediction(db, race_id, {
        "pick": result["pick"],
        "confidence": result["confidence"],
        "decision": result["decision"],
        "reason": "\n".join(result["reason"]),
    })
    mark_race_final(db, race_id)

    logger.info("=== 最終判定 ===")
    logger.info("pick: %s / confidence: %.1f / decision: %s",
                result["pick"], result["confidence"], result["decision"])
    logger.info("gap(3位-4位): %.1f点", result["gap"])
    for reason in result["reason"]:
        logger.info("  reason: %s", reason)
    logger.info("スコアTop3:")
    for s in scores[:3]:
        logger.info("  %d号艇 %s: morning=%.1f pre=%.1f total=%.1f",
                    s.lane, s.racer_name,
                    s.morning_score, s.pre_race_score, s.total)


def _save_race_result(db, race_id: str, stadium: str, race_no: int,
                      res: dict) -> None:
    """結果を取得してDBに保存する共通処理"""
    pred = (db.table("predictions")
            .select("pick")
            .eq("race_id", race_id)
            .execute().data)
    is_hit = False
    pick_str = pred[0]["pick"] if pred else "-"
    if pred:
        pick = pred[0]["pick"]
        result_set = set(res.get("trifecta_result", "").split("-"))
        pick_set = set(pick.split("-"))
        is_hit = result_set == pick_set

    res["prediction_hit"] = is_hit
    upsert_result(db, race_id, res)
    # predictions.is_hit も更新 (getStats で参照するため)
    db.table("predictions").update({"is_hit": is_hit}).eq("race_id", race_id).execute()
    mark_race_finished(db, race_id)
    logger.info("%s %dR 結果: %s 予想: %s → %s",
                stadium, race_no, res.get("trifecta_result"),
                pick_str, "的中" if is_hit else "不的中")
    logger.info("払戻: %s円 / 人気: %s",
                res.get("payout"), res.get("popularity"))


def result_scan(today: date) -> None:
    """結果スキャン: 的中判定"""
    scan_start = time.monotonic()
    db = get_client()
    races = get_open_races(db, today)
    final_races = [r for r in races if r["status"] == "final"]
    logger.info("=== Result Scan 開始 ===")
    logger.info("結果取得対象: %dレース", len(final_races))

    fetch_ok = 0
    hit_count = 0
    miss_count = 0

    for race in final_races:
        race_id = race["id"]
        stadium = race["stadium"]
        race_no = race["race_no"]
        stadium_code = _stadium_name_to_code(stadium)

        res = fetch_result(stadium_code, race_no, today)
        if not res:
            continue

        _save_race_result(db, race_id, stadium, race_no, res)
        fetch_ok += 1
        if res.get("prediction_hit"):
            hit_count += 1
        else:
            miss_count += 1

    elapsed = time.monotonic() - scan_start
    logger.info("=== Result Scan 完了 ===")
    logger.info("対象: %dレース / 結果取得成功: %d / 的中: %d / 不的中: %d / 経過: %.0f秒",
                len(final_races), fetch_ok, hit_count, miss_count, elapsed)


def result_scan_single(today: date, stadium_name: str, race_no: int) -> None:
    """指定レース1本の結果を強制取得 (手動テスト用)"""
    db = get_client()

    res_data = (db.table("races").select("*")
                .eq("race_date", today.isoformat())
                .eq("stadium", stadium_name)
                .eq("race_no", race_no)
                .execute())
    if not res_data.data:
        logger.error("レースが見つかりません: %s %dR %s", stadium_name, race_no, today)
        return

    race = res_data.data[0]
    race_id = race["id"]
    logger.info("=== %s %dR 結果テスト取得 ===", stadium_name, race_no)

    stadium_code = _stadium_name_to_code(stadium_name)
    res = fetch_result(stadium_code, race_no, today)
    if not res:
        logger.error("結果の取得に失敗しました (レースがまだ終了していない可能性があります)")
        return

    _save_race_result(db, race_id, stadium_name, race_no, res)
    logger.info("=== 保存完了 ===")
    logger.info("三連複結果: %s", res.get("trifecta_result"))
    logger.info("払戻: %s円", res.get("payout"))
    logger.info("人気: %s", res.get("popularity"))
    logger.info("的中: %s", res.get("prediction_hit"))


STADIUM_CODE_MAP = {
    "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
    "多摩川": "05", "浜名湖": "06", "蒲郡": "07", "常滑": "08",
    "津": "09", "三国": "10", "びわこ": "11", "住之江": "12",
    "尼崎": "13", "鳴門": "14", "丸亀": "15", "児島": "16",
    "宮島": "17", "徳山": "18", "下関": "19", "若松": "20",
    "芦屋": "21", "福岡": "22", "唐津": "23", "大村": "24",
}


def _stadium_name_to_code(name: str) -> str:
    return STADIUM_CODE_MAP.get(name, "01")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ボートレース予想スクレイパー")
    parser.add_argument("mode", choices=["morning", "pre_race", "result"])
    parser.add_argument("--date", default=None,
                        help="対象日 YYYY-MM-DD (省略時: 今日)")
    parser.add_argument("--stadium", default=None,
                        help="処理する場名 例: 常滑 (morning: フィルタ / pre_race・result --force: 対象指定)")
    parser.add_argument("--race-no", type=int, default=None,
                        help="[pre_race / result --force 用] レース番号 例: 1")
    parser.add_argument("--force", action="store_true",
                        help="時刻チェックを無視して指定レースを強制取得 (--stadium / --race-no 必須)")
    parser.add_argument("--limit-races", type=int, default=None,
                        help="[morning 手動テスト用] 処理するレース数の上限 例: 10")
    args = parser.parse_args()

    # date.today() はサーバのシステムTZ（GitHub Actions = UTC）を使うため
    # JST の今日を取得するために datetime.now(JST).date() を使う
    now_jst = datetime.now(JST)
    target = date.fromisoformat(args.date) if args.date else now_jst.date()

    # ── 起動ログ（date バグ検出用）──────────────────────────────
    now_utc = datetime.now(timezone.utc)
    logger.info("=== 実行日時 ===")
    logger.info("UTC  now : %s", now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"))
    logger.info("JST  now : %s", now_jst.strftime("%Y-%m-%d %H:%M:%S JST"))
    logger.info("対象日付 : %s%s",
                target.isoformat(),
                " (--date 指定)" if args.date else " (JST 今日)")
    logger.info("モード   : %s", args.mode)

    if args.mode == "morning":
        morning_scan(target,
                     stadium_filter=args.stadium,
                     limit_races=args.limit_races)
    elif args.mode == "pre_race":
        if args.force:
            if not args.stadium or not args.race_no:
                parser.error("--force には --stadium と --race-no が必要です")
            pre_race_scan_single(target, args.stadium, args.race_no)
        else:
            pre_race_scan(target)
    elif args.mode == "result":
        if args.force:
            if not args.stadium or not args.race_no:
                parser.error("--force には --stadium と --race-no が必要です")
            result_scan_single(target, args.stadium, args.race_no)
        else:
            result_scan(target)
