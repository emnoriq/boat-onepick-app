"""
Supabase DB 操作ユーティリティ
"""

import os
from datetime import date, datetime, timezone, timedelta
from typing import Optional
from supabase import create_client, Client


def get_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def upsert_race(db: Client, race_date: date, stadium: str, race_no: int,
                close_time: datetime, status: str = "scheduled") -> str:
    """レースを登録または更新してIDを返す"""
    data = {
        "race_date": race_date.isoformat(),
        "stadium": stadium,
        "race_no": race_no,
        "close_time": close_time.isoformat(),
        "status": status,
    }
    res = (
        db.table("races")
        .upsert(data, on_conflict="race_date,stadium,race_no")
        .execute()
    )
    return res.data[0]["id"]


def bulk_upsert_races(db: Client, races: list[dict]) -> list[dict]:
    """複数レースをまとめて upsert してIDリストを返す"""
    if not races:
        return []
    res = db.table("races").upsert(races, on_conflict="race_date,stadium,race_no").execute()
    return res.data or []


def upsert_entry(db: Client, race_id: str, entry: dict) -> None:
    """出走情報を登録または更新（1艇ずつ）"""
    data = {**entry, "race_id": race_id}
    db.table("entries").upsert(data, on_conflict="race_id,lane").execute()


def bulk_upsert_entries(db: Client, entries: list[dict]) -> None:
    """複数艇の出走情報をまとめて upsert（1レース6艇→1 API call）"""
    if not entries:
        return
    db.table("entries").upsert(entries, on_conflict="race_id,lane").execute()


def _strip_unknown_columns(payload: dict, known_err_msg: str) -> dict:
    """
    カラム未存在エラー時にペイロードから未知カラムを除去して返す。
    PostgreSQL エラー: 'column "xxx" of relation "predictions" does not exist'
    """
    import re
    m = re.search(r'column "([^"]+)" of relation', known_err_msg)
    if m:
        col = m.group(1)
        return {k: v for k, v in payload.items() if k != col}
    return payload


def upsert_prediction(db: Client, race_id: str, prediction: dict) -> None:
    """予想を登録または更新。未存在カラムがあれば除去してリトライ。"""
    data = {**prediction, "race_id": race_id}
    try:
        db.table("predictions").upsert(data, on_conflict="race_id").execute()
    except Exception as e:
        err = str(e)
        if "does not exist" in err:
            data2 = _strip_unknown_columns(data, err)
            db.table("predictions").upsert(data2, on_conflict="race_id").execute()
        else:
            raise


def bulk_upsert_predictions(db: Client, predictions: list[dict]) -> None:
    """複数予想をまとめて upsert。未存在カラムがあれば除去してリトライ。"""
    if not predictions:
        return
    try:
        db.table("predictions").upsert(predictions, on_conflict="race_id").execute()
    except Exception as e:
        err = str(e)
        if "does not exist" in err:
            stripped = [_strip_unknown_columns(p, err) for p in predictions]
            db.table("predictions").upsert(stripped, on_conflict="race_id").execute()
        else:
            raise


def upsert_result(db: Client, race_id: str, result: dict) -> None:
    """結果を登録または更新"""
    data = {**result, "race_id": race_id}
    db.table("results").upsert(data, on_conflict="race_id").execute()


def get_open_races(db: Client, race_date: date) -> list[dict]:
    """当日の未確定レース一覧を返す"""
    res = (
        db.table("races")
        .select("*")
        .eq("race_date", race_date.isoformat())
        .neq("status", "finished")
        .execute()
    )
    return res.data


def get_races_near_close(db: Client, race_date: date, minutes_before: int = 10) -> list[dict]:
    """締切 N分前以内のレース一覧"""
    now = datetime.now(timezone.utc)
    cutoff = now.isoformat()
    target_iso = (now + timedelta(minutes=minutes_before)).isoformat()

    res = (
        db.table("races")
        .select("*")
        .eq("race_date", race_date.isoformat())
        .eq("status", "scheduled")
        .gte("close_time", cutoff)
        .lte("close_time", target_iso)
        .execute()
    )
    return res.data


def get_entries_by_race_ids(db: Client, race_ids: list[str]) -> dict[str, list[dict]]:
    """複数レースの entries を一括取得して {race_id: [entry_dict, ...]} を返す"""
    if not race_ids:
        return {}
    res = (db.table("entries")
           .select("*")
           .in_("race_id", race_ids)
           .execute())
    result: dict[str, list[dict]] = {}
    for row in (res.data or []):
        result.setdefault(row["race_id"], []).append(row)
    return result


def get_races_for_result_scan(db: Client, today: date,
                              minutes_after: int = 10) -> list[dict]:
    """
    締切から minutes_after 分以上経過した未確定レース一覧を返す。
    (status=finished のレースと、既に results が存在するレースは除外しない
     — 呼び出し側で results の有無を確認してスキップすること)
    """
    now    = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=minutes_after)).isoformat()
    res = (db.table("races")
           .select("*")
           .eq("race_date", today.isoformat())
           .neq("status", "finished")
           .lt("close_time", cutoff)
           .execute())
    return res.data or []


def get_race_ids_with_entries(db: Client, race_ids: list[str]) -> set[str]:
    """entries が既に存在する race_id の集合を返す（スキップ判定用）"""
    if not race_ids:
        return set()
    res = (
        db.table("entries")
        .select("race_id")
        .in_("race_id", race_ids)
        .execute()
    )
    return {row["race_id"] for row in (res.data or [])}


def mark_race_final(db: Client, race_id: str) -> None:
    db.table("races").update({"status": "final"}).eq("id", race_id).execute()


def mark_race_finished(db: Client, race_id: str) -> None:
    db.table("races").update({"status": "finished"}).eq("id", race_id).execute()
