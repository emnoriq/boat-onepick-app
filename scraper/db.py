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


def upsert_prediction(db: Client, race_id: str, prediction: dict) -> None:
    """予想を登録または更新"""
    data = {**prediction, "race_id": race_id}
    db.table("predictions").upsert(data, on_conflict="race_id").execute()


def bulk_upsert_predictions(db: Client, predictions: list[dict]) -> None:
    """複数予想をまとめて upsert（スタジアム単位でまとめる）"""
    if not predictions:
        return
    db.table("predictions").upsert(predictions, on_conflict="race_id").execute()


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
