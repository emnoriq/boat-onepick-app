"""
メインエントリポイント
コマンドライン引数で処理モードを切り替える:
  morning   - 朝スキャン (出走表 + 仮スコア)
  pre_race  - 直前スキャン (展示 + 最終判定)
  result    - 結果スキャン (的中判定)
"""

import argparse
import logging
from datetime import date, datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv()  # ローカル実行時に .env を読み込む

from db import (get_client, upsert_race, upsert_entry, upsert_prediction,
                upsert_result, get_open_races, get_races_near_close,
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


def morning_scan(today: date) -> None:
    """朝スキャン: 出走表取得 & 仮スコア計算"""
    db = get_client()
    stadiums = fetch_today_schedule(today)
    logger.info("開催場 %d場", len(stadiums))

    for st in stadiums:
        code = st["stadium_code"]
        name = st["stadium"]
        races = fetch_race_list(code, today)
        logger.info("%s: %dレース", name, len(races))

        for r in races:
            race_no = r["race_no"]
            time_str = r["close_time_str"]
            try:
                # 公式サイトの時刻はJST → UTCに変換して保存
                close_dt = datetime.strptime(
                    f"{today.isoformat()} {time_str}", "%Y-%m-%d %H:%M"
                ).replace(tzinfo=JST).astimezone(timezone.utc)
            except ValueError:
                continue

            race_id = upsert_race(db, today, name, race_no, close_dt)
            entries = fetch_entries(code, race_no, today)

            scores = score_entries(entries, RaceCondition())
            score_map = {s.lane: s.total for s in scores}

            for e in entries:
                upsert_entry(db, race_id, {
                    "lane": e.lane,
                    "racer_name": e.racer_name,
                    "racer_class": e.racer_class,
                    "national_win_rate": e.national_win_rate,
                    "local_win_rate": e.local_win_rate,
                    "motor_rate": e.motor_rate,
                    "boat_rate": e.boat_rate,
                    "avg_st": e.avg_st,
                    "entry_score": score_map.get(e.lane),
                })

            result = decide(scores, RaceCondition())
            upsert_prediction(db, race_id, {
                "pick": result["pick"],
                "confidence": result["confidence"],
                "decision": result["decision"],
                "reason": "\n".join(result["reason"]),
            })
            logger.info("%s %dR 仮判定: %s %s (信頼度: %s)",
                        name, race_no, result["decision"], result["pick"],
                        result["confidence"])


def pre_race_scan(today: date, minutes_before: int = 10) -> None:
    """直前スキャン: 展示取得 & 最終判定"""
    db = get_client()
    races = get_races_near_close(db, today, minutes_before)
    logger.info("締切%d分前対象: %dレース", minutes_before, len(races))

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
        logger.info("%s %dR 最終判定: %s %s (信頼度: %s)",
                    stadium, race_no, result["decision"], result["pick"],
                    result["confidence"])


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
    db = get_client()
    races = get_open_races(db, today)
    final_races = [r for r in races if r["status"] == "final"]
    logger.info("結果取得対象: %dレース", len(final_races))

    for race in final_races:
        race_id = race["id"]
        stadium = race["stadium"]
        race_no = race["race_no"]
        stadium_code = _stadium_name_to_code(stadium)

        res = fetch_result(stadium_code, race_no, today)
        if not res:
            continue

        _save_race_result(db, race_id, stadium, race_no, res)


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
                        help="[--force 用] 場名 例: 常滑")
    parser.add_argument("--race-no", type=int, default=None,
                        help="[--force 用] レース番号 例: 1")
    parser.add_argument("--force", action="store_true",
                        help="時刻チェックを無視して指定レースを強制取得 (--stadium / --race-no 必須)")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()

    if args.mode == "morning":
        morning_scan(target)
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
