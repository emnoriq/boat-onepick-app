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
                get_race_ids_with_entries, get_entries_by_race_ids,
                get_races_for_result_scan,
                mark_race_final, mark_race_finished)
from fetch_races import fetch_today_schedule, fetch_race_list
from fetch_entries import fetch_entries
from fetch_exhibition import fetch_exhibition
from fetch_results import fetch_result
from fetch_odds import fetch_trifecta_box_odds, get_pick_payout
from fetch_racer_stats import fetch_course_win_rates, apply_course_win_rates
from scoring import score_entries, score_entries_ml, decide, RaceCondition, EntryData
from notify import notify_buy, notify_hit

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

# ── 並列フェッチ設定 ─────────────────────────────────────────────
# Morning : race_list だけ並列取得 (entries はしない)
# Pre-Race: entries + exhibition を per-race で並列
# Result  : fetch_result を並列
MAX_RACE_LIST_WORKERS = 4   # fetch_race_list 並列数 (18場)
MAX_PRE_RACE_WORKERS  = 3   # pre_race 並列数 (窓内 ~5-20R)
MAX_RESULT_WORKERS    = 5   # result   並列数
MAX_MORNING_ENTRY_WORKERS = 6   # 朝スキャン用 entry 並列数


def _fetch_race_list_worker(args: tuple) -> tuple:
    """Thread worker: 1場のレース一覧を取得して (code, name, races) を返す"""
    code, name, today = args
    try:
        races = fetch_race_list(code, today)
        return (code, name, races or [])
    except Exception as e:
        logger.error("fetch_race_list失敗 %s: %s", name, e)
        return (code, name, [])


def _pre_race_worker(args: tuple) -> tuple:
    """
    Thread worker: 1レースの entries + exhibition を順次取得
    Returns: (race_id, name, race_no, entries: list[EntryData] | None, condition | None, code)
    """
    code, name, race_no, race_id, today, existing_entries = args
    # existing_entries: list[dict] from DB, None = 未取得
    try:
        # ① entries 取得（DB になければ HTTP フェッチ）
        if existing_entries is None:
            entry_objects = fetch_entries(code, race_no, today)
            if not entry_objects:
                logger.warning("%s %dR: 出走表取得失敗", name, race_no)
                return (race_id, name, race_no, None, None, code)
            # EntryData → dict 変換 (race_id を付与)
            existing_entries = [{
                "race_id": race_id,
                "lane": e.lane,
                "racer_name": e.racer_name,
                "racer_class": e.racer_class,
                "national_win_rate": e.national_win_rate,
                "local_win_rate": e.local_win_rate,
                "motor_rate": e.motor_rate,
                "boat_rate": e.boat_rate,
                "avg_st": e.avg_st,
            } for e in entry_objects]

        # ② DB の dict から EntryData を組み立て
        # 旧データでは top2/top3 rate が NULL の場合があるため or 0.0 でフォールバック
        entries = [EntryData(
            lane=e["lane"],
            racer_name=e.get("racer_name", ""),
            racer_class=e.get("racer_class") or "",
            racer_no=e.get("racer_no") or "",
            national_win_rate=e.get("national_win_rate") or 0.0,
            national_top2_rate=e.get("national_top2_rate") or 0.0,
            national_top3_rate=e.get("national_top3_rate") or 0.0,
            local_win_rate=e.get("local_win_rate") or 0.0,
            local_top2_rate=e.get("local_top2_rate") or 0.0,
            local_top3_rate=e.get("local_top3_rate") or 0.0,
            motor_rate=e.get("motor_rate") or 0.0,
            boat_rate=e.get("boat_rate") or 0.0,
            avg_st=e.get("avg_st") or 0.15,
            f_count=int(e.get("f_count") or 0),
            l_count=int(e.get("l_count") or 0),
            c1_win_rate=e.get("c1_win_rate") or 0.0,
            c2_win_rate=e.get("c2_win_rate") or 0.0,
            c3_win_rate=e.get("c3_win_rate") or 0.0,
            c4_win_rate=e.get("c4_win_rate") or 0.0,
            c5_win_rate=e.get("c5_win_rate") or 0.0,
            c6_win_rate=e.get("c6_win_rate") or 0.0,
        ) for e in sorted(existing_entries, key=lambda x: x["lane"])]

        # ② ½: コース別1着率を取得（DB未取得 or racer_no あり時）
        for entry in entries:
            if entry.racer_no and all(
                getattr(entry, f"c{i}_win_rate") == 0.0 for i in range(1, 7)
            ):
                rates = fetch_course_win_rates(entry.racer_no)
                apply_course_win_rates(entry, rates)

        # ③ 展示情報取得（entries を in-place で更新）
        condition = fetch_exhibition(code, race_no, today, entries)

        return (race_id, name, race_no, entries, condition, code)
    except Exception as e:
        logger.error("_pre_race_worker失敗 %s %dR: %s", name, race_no, e)
        return (race_id, name, race_no, None, None, code)


def _result_worker(args: tuple) -> tuple:
    """Thread worker: 1レースの結果を取得"""
    code, name, race_no, race_id, today = args
    try:
        res = fetch_result(code, race_no, today)
        return (race_id, name, race_no, res)
    except Exception as e:
        logger.error("_result_worker失敗 %s %dR: %s", name, race_no, e)
        return (race_id, name, race_no, None)


def _morning_entry_worker(args: tuple) -> tuple:
    """
    Thread worker: 朝スキャン用 — entry取得のみ（展示なし）
    Returns: (race_id, name, race_no, entry_objects: list[EntryData] | None)
    """
    code, name, race_no, race_id, today = args
    try:
        entry_objects = fetch_entries(code, race_no, today)
        if not entry_objects:
            logger.warning("_morning_entry_worker: 出走表なし %s %dR", name, race_no)
            return (race_id, name, race_no, None)
        return (race_id, name, race_no, entry_objects)
    except Exception as e:
        logger.warning("_morning_entry_worker失敗 %s %dR: %s", name, race_no, e)
        return (race_id, name, race_no, None)


def morning_scan(today: date,
                 stadium_filter: Optional[str] = None,
                 limit_races: Optional[int] = None,
                 use_ml: bool = False,
                 ml_blend: float = 0.5) -> None:
    """
    軽量版朝スキャン: races テーブルへの基本情報保存のみ。

    保存するのは: race_date / stadium / race_no / close_time / status=scheduled
    entries・predictions の取得は Pre-Race Scan (締切45分前) で行う。

    目標処理時間: 3分以内
    変更前 (entries全件取得): 41分40秒 → 変更後: ~1分

    Args:
        stadium_filter: 指定場のみ処理 (例: "常滑"). None で全場.
        limit_races:    登録するレース数の上限 (手動テスト用).
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
    race_list_args = [(s["stadium_code"], s["stadium"], today) for s in stadiums]
    stadium_races: dict[str, list[dict]] = {}

    with ThreadPoolExecutor(max_workers=MAX_RACE_LIST_WORKERS) as pool:
        futs = {pool.submit(_fetch_race_list_worker, a): a for a in race_list_args}
        for fut in as_completed(futs):
            code, name, races = fut.result()
            if races:
                stadium_races[name] = races

    t_p2 = time.monotonic() - t0
    total_count = sum(len(r) for r in stadium_races.values())
    logger.info("[P2] レース一覧取得 (%d場, 並列%d): %.1f秒 → %d件",
                len(stadium_races), MAX_RACE_LIST_WORKERS, t_p2, total_count)

    # ── races upsert ペイロードを組み立て ─────────────────────────
    all_races_payload: list[dict] = []
    for name, races in stadium_races.items():
        for r in races:
            if limit_races is not None and len(all_races_payload) >= limit_races:
                break
            try:
                close_dt = datetime.strptime(
                    f"{today.isoformat()} {r['close_time_str']}", "%Y-%m-%d %H:%M"
                ).replace(tzinfo=JST).astimezone(timezone.utc)
            except ValueError:
                continue
            all_races_payload.append({
                "race_date": today.isoformat(),
                "stadium":   name,
                "race_no":   r["race_no"],
                "close_time": close_dt.isoformat(),
                "status":    "scheduled",
            })

    # ── Phase 3: races を全場まとめて一括 upsert ─────────────────
    t0 = time.monotonic()
    saved_races = bulk_upsert_races(db, all_races_payload)
    t_p3 = time.monotonic() - t0
    logger.info("[P3] races upsert (%d件): %.1f秒", len(saved_races), t_p3)

    # ── Phase 4: entries を並列取得 ───────────────────────────────
    t0 = time.monotonic()
    entry_worker_args = [
        (
            _stadium_name_to_code(r["stadium"]),
            r["stadium"],
            r["race_no"],
            r["id"],
            today,
        )
        for r in saved_races
        if _stadium_name_to_code(r["stadium"]) is not None  # ③ 未知場名をスキップ
    ]

    all_entries_payload: list[dict] = []
    entry_results: list[tuple] = []  # (race_id, name, race_no, entries)

    with ThreadPoolExecutor(max_workers=MAX_MORNING_ENTRY_WORKERS) as pool:
        futs = {pool.submit(_morning_entry_worker, a): a for a in entry_worker_args}
        for fut in as_completed(futs):
            race_id, name, race_no, entry_objects = fut.result()
            if not entry_objects:
                continue
            entry_results.append((race_id, name, race_no, entry_objects))
            for e in entry_objects:
                all_entries_payload.append({
                    "race_id":            race_id,
                    "lane":               e.lane,
                    "racer_name":         e.racer_name,
                    "racer_class":        e.racer_class,
                    "racer_no":           e.racer_no,
                    "national_win_rate":  e.national_win_rate,
                    "national_top2_rate": e.national_top2_rate,
                    "national_top3_rate": e.national_top3_rate,
                    "local_win_rate":     e.local_win_rate,
                    "local_top2_rate":    e.local_top2_rate,
                    "local_top3_rate":    e.local_top3_rate,
                    "motor_rate":         e.motor_rate,
                    "boat_rate":          e.boat_rate,
                    "avg_st":             e.avg_st,
                    "f_count":            e.f_count,
                    "l_count":            e.l_count,
                })

    t_p4 = time.monotonic() - t0
    logger.info("[P4] entries 取得 (%d件, 並列%d): %.1f秒 → %d艇",
                len(entry_results), MAX_MORNING_ENTRY_WORKERS, t_p4, len(all_entries_payload))

    # entries を一括 upsert
    if all_entries_payload:
        bulk_upsert_entries(db, all_entries_payload)

    # ── Phase 5: 暫定予想を作成（展示データなし） ─────────────────
    t0 = time.monotonic()
    all_predictions_payload: list[dict] = []
    default_condition = RaceCondition()

    for race_id, name, race_no, entry_objects in entry_results:
        if use_ml:
            scores = score_entries_ml(entry_objects, default_condition, blend_alpha=ml_blend)
        else:
            scores = score_entries(entry_objects, default_condition)
        lane1_e = next((e for e in entry_objects if e.lane == 1), None)
        lane1_cls = lane1_e.racer_class if lane1_e else None
        pred   = decide(scores, default_condition,
                        stadium=name, lane1_class=lane1_cls, race_no=race_no)
        all_predictions_payload.append({
            "race_id":    race_id,
            "pick":       pred["pick"],
            "confidence": pred["confidence"],
            "decision":   pred["decision"],
            "reason":     "[展示未取得]\n" + "\n".join(pred["reason"]),
            "gap":        pred["gap"],
        })
        if pred["decision"] == "buy":
            notify_buy(name, race_no, pred["pick"], pred["confidence"])

    if all_predictions_payload:
        bulk_upsert_predictions(db, all_predictions_payload)

    t_p5 = time.monotonic() - t0
    counts = {"buy": 0, "candidate": 0, "watch": 0, "skip": 0}
    for p in all_predictions_payload:
        if p["decision"] == "buy":       counts["buy"] += 1
        elif p["decision"] == "candidate": counts["candidate"] += 1
        elif "[watch]" in (p["reason"] or ""): counts["watch"] += 1
        else:                             counts["skip"] += 1
    logger.info("[P5] 暫定予想作成 (%d件): %.1f秒 | buy=%d cand=%d watch=%d skip=%d",
                len(all_predictions_payload), t_p5,
                counts["buy"], counts["candidate"], counts["watch"], counts["skip"])

    total_elapsed = time.monotonic() - scan_start
    logger.info("=== Morning Scan 完了 ===")
    logger.info("開催場: %d場 / races: %d件 / entries: %d艇 / 暫定予想: %d件",
                len(stadiums), len(saved_races), len(all_entries_payload), len(all_predictions_payload))
    logger.info("[P1] 開催場一覧  : %6.1f秒", t_p1)
    logger.info("[P2] レース一覧  : %6.1f秒  (並列%d)", t_p2, MAX_RACE_LIST_WORKERS)
    logger.info("[P3] races upsert: %6.1f秒", t_p3)
    logger.info("[P4] entries取得 : %6.1f秒  (並列%d)", t_p4, MAX_MORNING_ENTRY_WORKERS)
    logger.info("[P5] 暫定予想    : %6.1f秒", t_p5)
    logger.info("合計              : %6.0f秒  (%.1f分)", total_elapsed, total_elapsed / 60)


def pre_race_scan(today: date, window_minutes: int = 45,
                  use_ml: bool = False, ml_blend: float = 0.5) -> None:
    """
    直前スキャン (メイン処理): 締切 window_minutes 分前以内のレースを処理

    対象条件:
      - race_date = today
      - status = 'scheduled' (まだ pre_race 未処理)
      - close_time: now <= close_time <= now + window_minutes

    処理内容 (per race):
      1. entries が DB になければ HTTP で取得
      2. exhibition 情報 (展示タイム/ST/風速/波高/進入) を HTTP で取得
      3. score_entries + decide (buy/candidate/watch/skip)
      4. entries・predictions を一括 upsert
      5. race status を 'final' に更新
    """
    scan_start = time.monotonic()
    db = get_client()

    now = datetime.now(timezone.utc)
    # 対象レース: scheduled かつ window 内
    races = get_races_near_close(db, today, window_minutes)
    today_total = (db.table("races")
                   .select("id", count="exact")
                   .eq("race_date", today.isoformat())
                   .execute().count or 0)

    logger.info("=== Pre-Race Scan 開始 ===")
    logger.info("今日の全レース数: %d / 窓内対象 (締切%d分前): %d件",
                today_total, window_minutes, len(races))

    if not races:
        logger.info("対象レースなし。終了。")
        return

    # ── 全対象レースの既存 entries を一括取得 ─────────────────────
    race_ids = [r["id"] for r in races]
    existing_entries_map = get_entries_by_race_ids(db, race_ids)

    # ── 並列フェッチ (entries + exhibition) ──────────────────────
    t0 = time.monotonic()
    worker_args = [
        (
            _stadium_name_to_code(r["stadium"]),
            r["stadium"],
            r["race_no"],
            r["id"],
            today,
            existing_entries_map.get(r["id"]),
        )
        for r in races
        if _stadium_name_to_code(r["stadium"]) is not None  # ③ 未知場名をスキップ
    ]

    results: list[tuple] = []
    with ThreadPoolExecutor(max_workers=MAX_PRE_RACE_WORKERS) as pool:
        futs = {pool.submit(_pre_race_worker, a): a for a in worker_args}
        for fut in as_completed(futs):
            results.append(fut.result())

    t_fetch = time.monotonic() - t0
    logger.info("[fetch] entries + exhibition 取得: %.1f秒 (並列%d)",
                t_fetch, MAX_PRE_RACE_WORKERS)

    # ── スコア計算 & ペイロード組み立て ──────────────────────────
    all_entries_payload: list[dict] = []
    all_predictions_payload: list[dict] = []
    race_ids_processed: list[str] = []   # entries 取得成功した全レース
    ex_ok_set: set[str]  = set()         # 展示データ取得済みの race_id
    close_time_map = {r["id"]: r["close_time"] for r in races}
    counts = {"buy": 0, "candidate": 0, "watch": 0, "skip": 0}
    ex_ok_count = 0

    # 朝にBUYだったレースを把握（展示後の更新通知に使用）
    morning_buy_ids: set[str] = set()
    if race_ids:
        for i in range(0, len(race_ids), 200):
            chunk = race_ids[i:i+200]
            rows = (db.table("predictions").select("race_id,decision")
                    .in_("race_id", chunk).execute().data or [])
            for r in rows:
                if r.get("decision") == "buy":
                    morning_buy_ids.add(r["race_id"])

    for race_id, name, race_no, entries, condition, code in results:
        if entries is None:
            continue

        ex_ok = any(e.exhibition_time is not None for e in entries)
        if ex_ok:
            ex_ok_count += 1
            ex_ok_set.add(race_id)

        if use_ml:
            scores = score_entries_ml(entries, condition, blend_alpha=ml_blend)
        else:
            scores = score_entries(entries, condition)
        score_map = {s.lane: s.total for s in scores}

        # 1号艇の実際の進入コース（confidence 補正用）
        lane1_entry  = next((e for e in entries if e.lane == 1), None)
        lane1_approach = lane1_entry.approach_lane if lane1_entry else None

        # 三連複オッズを全20組み合わせ取得してEV計算に使用
        odds = fetch_trifecta_box_odds(code, race_no, today)
        lane1_cls = lane1_entry.racer_class if lane1_entry else None
        pred = decide(scores, condition, lane1_approach=lane1_approach,
                      all_odds=odds if odds else None,
                      stadium=name, lane1_class=lane1_cls, race_no=race_no)

        # entries ペイロード (展示情報・チルト・コース別1着率込み)
        all_entries_payload.extend([{
            "race_id":            race_id,
            "lane":               e.lane,
            "racer_name":         e.racer_name,
            "racer_class":        e.racer_class,
            "racer_no":           e.racer_no,
            "national_win_rate":  e.national_win_rate,
            "national_top2_rate": e.national_top2_rate,
            "national_top3_rate": e.national_top3_rate,
            "local_win_rate":     e.local_win_rate,
            "local_top2_rate":    e.local_top2_rate,
            "local_top3_rate":    e.local_top3_rate,
            "motor_rate":         e.motor_rate,
            "boat_rate":          e.boat_rate,
            "avg_st":             e.avg_st,
            "f_count":            e.f_count,
            "l_count":            e.l_count,
            "c1_win_rate":        e.c1_win_rate,
            "c2_win_rate":        e.c2_win_rate,
            "c3_win_rate":        e.c3_win_rate,
            "c4_win_rate":        e.c4_win_rate,
            "c5_win_rate":        e.c5_win_rate,
            "c6_win_rate":        e.c6_win_rate,
            "exhibition_time":    e.exhibition_time,
            "exhibition_st":      e.exhibition_st,
            "approach_lane":      e.approach_lane,
            "tilt":               e.tilt,
            "entry_score":        score_map.get(e.lane),
        } for e in entries])

        # reason に展示未取得マーカーを付与
        reason_lines = pred["reason"]
        if not ex_ok:
            reason_lines = ["[展示未取得]"] + reason_lines

        all_predictions_payload.append({
            "race_id":    race_id,
            "pick":       pred["pick"],
            "confidence": pred["confidence"],
            "decision":   pred["decision"],
            "reason":     "\n".join(reason_lines),
            "gap":        pred["gap"],
            "best_ev":        pred["best_ev"],
            "kelly_fraction": pred.get("kelly_fraction"),
        })
        race_ids_processed.append(race_id)

        # カウント (watch は is_watch フラグで判別)
        # 締切時刻を JST 文字列に変換
        _close = close_time_map.get(race_id, "")
        _race_time = None
        if _close:
            try:
                _dt = datetime.fromisoformat(_close)
                if _dt.tzinfo is None:
                    _dt = _dt.replace(tzinfo=timezone.utc)
                _race_time = _dt.astimezone(JST).strftime("%H:%M")
            except Exception:
                pass

        if pred["decision"] == "buy":
            counts["buy"] += 1
            # ntfy: 展示データが取得できたBUYのみ通知。
            # 展示取得=この直後にfinal確定し窓から外れるため重複通知が起きない。
            # 展示未取得のBUYは scheduled のまま15分ごとに再評価されるので、
            # ここで通知すると同一レースを何度も通知してしまう → ex_ok で抑止。
            if ex_ok:
                notify_buy(name, race_no, pred["pick"], pred["confidence"],
                           best_ev=pred.get("best_ev"), race_time=_race_time)
        elif pred["decision"] == "candidate":
            counts["candidate"] += 1
        elif pred.get("is_watch"):
            counts["watch"] += 1
        else:
            counts["skip"] += 1

        logger.info("%s %dR → %s%s %s conf=%.1f gap=%.1f %s",
                    name, race_no,
                    pred["decision"].upper(),
                    " [watch]" if pred.get("is_watch") else "",
                    pred["pick"],
                    pred["confidence"], pred["gap"],
                    "✓展示" if ex_ok else "△展示未取得")

    # ── finalize 判定 ─────────────────────────────────────────────
    # 展示データ公開タイミングの実態:
    #   展示航走は締切 約30〜40分前に実施、公開は締切 約15〜20分前
    #   → 「締切15分以内=諦め」では公開直後にfinalizeしてデータを取り逃がす
    # 修正: 展示未取得は「締切5分以内」まで再試行を継続
    now_fin = datetime.now(timezone.utc)
    race_ids_to_finalize: list[str] = []
    retry_count = 0
    for race_id in race_ids_processed:
        if race_id in ex_ok_set:
            race_ids_to_finalize.append(race_id)
        else:
            close_str = close_time_map.get(race_id, "")
            mins_left = 0.0
            if close_str:
                try:
                    close_dt = datetime.fromisoformat(close_str)
                    if close_dt.tzinfo is None:
                        close_dt = close_dt.replace(tzinfo=timezone.utc)
                    mins_left = (close_dt - now_fin).total_seconds() / 60
                except Exception:
                    pass
            if mins_left <= 5:
                # 締切5分以内 → 展示なしで確定（これ以上待てない）
                race_ids_to_finalize.append(race_id)
                logger.info("展示未取得 締切%.0f分前 → final確定(タイムアウト)", mins_left)
            else:
                # 締切5分超え → scheduled維持・次回スキャンで展示を再取得
                retry_count += 1
                logger.info("展示未取得 締切%.0f分前 → scheduled維持・次回再スキャン", mins_left)

    # ── 一括保存 ─────────────────────────────────────────────────
    t0 = time.monotonic()
    if all_entries_payload:
        bulk_upsert_entries(db, all_entries_payload)
    if all_predictions_payload:
        bulk_upsert_predictions(db, all_predictions_payload)
    for race_id in race_ids_to_finalize:
        mark_race_final(db, race_id)
    t_save = time.monotonic() - t0

    total_elapsed = time.monotonic() - scan_start
    processed = len(race_ids_processed)
    logger.info("=== Pre-Race Scan 完了 ===")
    logger.info("今日の全R: %d / 窓内対象: %d / 処理成功: %d (final確定: %d / 再試行待ち: %d)",
                today_total, len(races), processed, len(race_ids_to_finalize), retry_count)
    logger.info("展示取得成功: %d / 失敗(races数-処理数): %d",
                ex_ok_count, len(races) - processed)
    logger.info("buy: %d / candidate: %d / watch: %d / skip: %d",
                counts["buy"], counts["candidate"], counts["watch"], counts["skip"])
    logger.info("fetch: %.1f秒 / DB保存: %.1f秒 / 合計: %.0f秒",
                t_fetch, t_save, total_elapsed)


def pre_race_scan_single(today: date, stadium_name: str, race_no: int) -> None:
    """指定レース1本の直前情報を強制取得 (手動テスト用 --force)"""
    db = get_client()

    res = (db.table("races").select("*")
           .eq("race_date", today.isoformat())
           .eq("stadium", stadium_name)
           .eq("race_no", race_no)
           .execute())
    if not res.data:
        logger.error("レースが見つかりません: %s %dR %s", stadium_name, race_no, today)
        return

    race = res.data[0]
    race_id = race["id"]
    logger.info("=== %s %dR 直前情報テスト取得 ===", stadium_name, race_no)

    # entries: DB から取得、なければ HTTP で取得
    entries_data = get_entries_by_race_ids(db, [race_id]).get(race_id)
    code = _stadium_name_to_code(stadium_name)

    result_tuple = _pre_race_worker(
        (code, stadium_name, race_no, race_id, today, entries_data)
    )
    _, _, _, entries, condition, _ = result_tuple

    if entries is None:
        logger.error("entries の取得に失敗しました")
        return

    ex_ok = any(e.exhibition_time is not None for e in entries)
    if not ex_ok:
        logger.warning("展示タイムが取得できませんでした (レースがまだ先の可能性)")

    scores = score_entries(entries, condition)
    score_map = {s.lane: s.total for s in scores}

    # 1号艇の実際の進入コース（confidence 補正用）
    lane1_entry    = next((e for e in entries if e.lane == 1), None)
    lane1_approach = lane1_entry.approach_lane if lane1_entry else None
    if lane1_approach and lane1_approach >= 3:
        logger.info("⚠️ 1号艇コース%d進入 — インアドバンテージ消失", lane1_approach)

    # 三連複オッズを全20組み合わせ取得してEV計算に使用
    odds = fetch_trifecta_box_odds(code, race_no, today)
    if odds:
        logger.info("三連複オッズ取得: %d組", len(odds))
    else:
        logger.info("三連複オッズ: 取得できませんでした")
    lane1_cls = lane1_entry.racer_class if lane1_entry else None
    pred = decide(scores, condition, lane1_approach=lane1_approach,
                  all_odds=odds if odds else None,
                  stadium=stadium_name, lane1_class=lane1_cls, race_no=race_no)

    reason_lines = pred["reason"]
    if not ex_ok:
        reason_lines = ["[展示未取得]"] + reason_lines

    entries_payload = [{
        "race_id":            race_id,
        "lane":               e.lane,
        "racer_name":         e.racer_name,
        "racer_class":        e.racer_class,
        "racer_no":           e.racer_no,
        "national_win_rate":  e.national_win_rate,
        "national_top2_rate": e.national_top2_rate,
        "national_top3_rate": e.national_top3_rate,
        "local_win_rate":     e.local_win_rate,
        "local_top2_rate":    e.local_top2_rate,
        "local_top3_rate":    e.local_top3_rate,
        "motor_rate":         e.motor_rate,
        "boat_rate":          e.boat_rate,
        "avg_st":             e.avg_st,
        "f_count":            e.f_count,
        "l_count":            e.l_count,
        "c1_win_rate":        e.c1_win_rate,
        "c2_win_rate":        e.c2_win_rate,
        "c3_win_rate":        e.c3_win_rate,
        "c4_win_rate":        e.c4_win_rate,
        "c5_win_rate":        e.c5_win_rate,
        "c6_win_rate":        e.c6_win_rate,
        "exhibition_time":    e.exhibition_time,
        "exhibition_st":      e.exhibition_st,
        "approach_lane":      e.approach_lane,
        "tilt":               e.tilt,
        "entry_score":        score_map.get(e.lane),
    } for e in entries]

    bulk_upsert_entries(db, entries_payload)
    upsert_prediction(db, race_id, {
        "pick":           pred["pick"],
        "confidence":     pred["confidence"],
        "decision":       pred["decision"],
        "reason":         "\n".join(reason_lines),
        "gap":            pred["gap"],
        "best_ev":        pred["best_ev"],
        "kelly_fraction": pred.get("kelly_fraction"),  # ② 欠落していたkelly_fractionを追加
    })
    mark_race_final(db, race_id)

    logger.info("=== 最終判定 ===")
    logger.info("pick: %s / confidence: %.1f / decision: %s / is_watch: %s",
                pred["pick"], pred["confidence"], pred["decision"], pred.get("is_watch"))

    if pred["decision"] == "buy":
        notify_buy(stadium_name, race_no, pred["pick"], pred["confidence"],
                   best_ev=pred.get("best_ev"))
    logger.info("gap(3位-4位): %.1f点 / best_ev: %s",
                pred["gap"], f"{pred['best_ev']:+.4f}" if pred.get("best_ev") is not None else "N/A")
    for r in pred["reason"]:
        logger.info("  reason: %s", r)
    logger.info("スコアTop3:")
    for s in scores[:3]:
        logger.info("  %d号艇 %s: morning=%.1f pre=%.1f total=%.1f",
                    s.lane, s.racer_name,
                    s.morning_score, s.pre_race_score, s.total)


def _save_race_result(db, race_id: str, stadium: str, race_no: int,
                      res: dict) -> None:
    """結果を DB に保存する共通処理 (prediction_hit を計算して更新)"""
    pred = (db.table("predictions")
            .select("pick")
            .eq("race_id", race_id)
            .execute().data)
    is_hit = False
    pick_str = pred[0]["pick"] if pred else "-"
    if pred:
        result_set = set(res.get("trifecta_result", "").split("-"))
        pick_set   = set(pred[0]["pick"].split("-"))
        is_hit = result_set == pick_set

    res["prediction_hit"] = is_hit
    upsert_result(db, race_id, res)
    db.table("predictions").update({"is_hit": is_hit}).eq("race_id", race_id).execute()
    mark_race_finished(db, race_id)
    logger.info("%s %dR 結果: %s 予想:%s → %s 払戻:%s円 人気:%s",
                stadium, race_no, res.get("trifecta_result"),
                pick_str, "的中" if is_hit else "不的中",
                res.get("payout"), res.get("popularity"))

    # BUY だった場合のみ的中/外れ通知
    decision_row = (db.table("predictions")
                    .select("decision")
                    .eq("race_id", race_id)
                    .execute().data)
    if decision_row and decision_row[0].get("decision") == "buy":
        payout = res.get("payout") or 0
        trifecta = res.get("trifecta_result", "")
        if is_hit:
            notify_hit(stadium, race_no, pick_str, int(payout))


def result_scan(today: date) -> None:
    """
    結果スキャン: 締切を過ぎた未確定レースの結果を取得

    対象条件:
      - race_date = today
      - status != 'finished'
      - close_time < now - 10分 (レース終了済み)
      - results テーブルに未登録

    既に results がある場合は再取得しない。
    """
    scan_start = time.monotonic()
    db = get_client()

    # 締切済み・未 finished のレース一覧
    # 10分では早すぎてまだレース中のことが多い → 15分バッファに変更
    past_races = get_races_for_result_scan(db, today, minutes_after=15)

    if not past_races:
        logger.info("=== Result Scan: 対象レースなし ===")
        return

    # 既に results が存在する race_id を除外 ⑫ 200件チャンクで上限回避
    past_ids = [r["id"] for r in past_races]
    has_result_ids: set[str] = set()
    CHUNK = 200
    for i in range(0, len(past_ids), CHUNK):
        chunk = past_ids[i:i + CHUNK]
        rows = (db.table("results")
                .select("race_id")
                .in_("race_id", chunk)
                .execute().data or [])
        has_result_ids.update(row["race_id"] for row in rows)
    to_process = [r for r in past_races if r["id"] not in has_result_ids]

    logger.info("=== Result Scan 開始 ===")
    logger.info("締切済み未処理: %d件 / 既存結果スキップ: %d件 / 取得対象: %d件",
                len(past_races), len(has_result_ids), len(to_process))

    if not to_process:
        logger.info("取得対象なし。終了。")
        return

    # 並列で結果取得
    t0 = time.monotonic()
    worker_args = [
        (_stadium_name_to_code(r["stadium"]), r["stadium"], r["race_no"], r["id"], today)
        for r in to_process
        if _stadium_name_to_code(r["stadium"]) is not None  # ③ 未知場名をスキップ
    ]

    fetch_ok = 0
    hit_count = 0
    miss_count = 0

    with ThreadPoolExecutor(max_workers=MAX_RESULT_WORKERS) as pool:
        futs = {pool.submit(_result_worker, a): a for a in worker_args}
        for fut in as_completed(futs):
            race_id, name, race_no, res = fut.result()
            if not res:
                logger.warning("%s %dR: 結果取得失敗 (未終了の可能性)", name, race_no)
                continue
            _save_race_result(db, race_id, name, race_no, res)
            fetch_ok += 1
            if res.get("prediction_hit"):
                hit_count += 1
            else:
                miss_count += 1

    elapsed = time.monotonic() - scan_start
    logger.info("=== Result Scan 完了 ===")
    logger.info("取得対象:%d / 成功:%d / 的中:%d / 不的中:%d / 経過:%.0f秒",
                len(to_process), fetch_ok, hit_count, miss_count, elapsed)


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


def _stadium_name_to_code(name: str) -> Optional[str]:
    """場名→コード変換。③ 未知の場名は None を返してスキップ（黙ってフォールバックしない）"""
    code = STADIUM_CODE_MAP.get(name)
    if code is None:
        logger.error("未知の場名 '%s' — スキップします（STADIUM_CODE_MAP を確認してください）", name)
        return None
    return code


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
                        help="[morning 手動テスト用] 登録するレース数の上限 例: 10")
    parser.add_argument("--window-minutes", type=int, default=45,
                        help="[pre_race] 締切何分前までを対象にするか (省略時: 45)")
    parser.add_argument("--use-ml", action="store_true",
                        help="ML スコアリング (GradientBoosting) を使用 (model_gbm.pkl 必須)")
    parser.add_argument("--ml-blend", type=float, default=0.5,
                        help="[--use-ml] ML と線形スコアのブレンド比率 0.0〜1.0 (default: 0.5)")
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
                     limit_races=args.limit_races,
                     use_ml=args.use_ml,
                     ml_blend=args.ml_blend)
    elif args.mode == "pre_race":
        if args.force:
            if not args.stadium or not args.race_no:
                parser.error("--force には --stadium と --race-no が必要です")
            pre_race_scan_single(target, args.stadium, args.race_no)
        else:
            pre_race_scan(target, window_minutes=args.window_minutes,
                          use_ml=args.use_ml, ml_blend=args.ml_blend)
    elif args.mode == "result":
        if args.force:
            if not args.stadium or not args.race_no:
                parser.error("--force には --stadium と --race-no が必要です")
            result_scan_single(target, args.stadium, args.race_no)
        else:
            result_scan(target)
