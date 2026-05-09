"""
展示情報・直前情報を取得してEntryDataに反映する

HTML 構造 (beforeinfo):
  天候: div.weather1 内の
        span.weather1_bodyUnitLabelTitle → ラベル名 (気温 / 風速 / 水温 / 波高)
        span.weather1_bodyUnitLabelData  → 値 (例: 2m, 1cm)
        天候テキスト (晴/曇/雨) は is-weather ブロックの LabelTitle スパン

  展示タイム/チルト: table.is-w748 (1艇=1tbody, tbody内4tr)
        tbody > tr[0] > td[0]=艇番, td[4]=展示タイム, td[5]=チルト

  進入コース/展示ST: table.is-w238 (1行=1コース位置)
        行インデックス+1 = 進入コース番号
        span.table1_boatImage1Number → 艇番
        span.table1_boatImage1Time   → 展示ST (例: .04)

修正履歴:
  - tilt をEntryData に保存するように変更
  - 実際の進入コース並び (t238) からも approach_stable を判定
  - 展示タイムが0件のとき WARNING を出力
"""

import re
import time
import logging
from typing import Optional
from datetime import date
import requests
from bs4 import BeautifulSoup

from scoring import EntryData, RaceCondition

logger = logging.getLogger(__name__)

BASE_URL = "https://www.boatrace.jp"
HEADERS = {"User-Agent": "boat-onepick-bot/1.0 (private research tool)"}
REQUEST_INTERVAL = 2.0

_NUM_RE = re.compile(r"[\d.]+")

# 進入コースの合計偏差がこの値以上なら approach_stable = False
# 例: 1号艇が4コースに入り 4号艇が1コース → 各偏差3+3=6
APPROACH_INSTABILITY_THRESHOLD = 6


def _get(url: str) -> Optional[BeautifulSoup]:
    try:
        time.sleep(REQUEST_INTERVAL)
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.error("GET %s failed: %s", url, e)
        return None


def _extract_number(text: str) -> Optional[float]:
    """テキストから最初の数値を抽出 ('7m/s'→7.0, '.04'→0.04, '15cm'→15.0)"""
    text = text.strip()
    # F/L (フライング/出遅れ) など数値でないケース
    if not text or text.upper() in ("F", "L", "S", "-", "N/A"):
        return None
    if text.startswith("."):
        text = "0" + text
    m = _NUM_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def fetch_exhibition(stadium_code: str, race_no: int, target_date: date,
                     entries: list[EntryData]) -> RaceCondition:
    """
    展示タイム・展示ST・進入コース・チルト・風速・波高を取得して entries を直接更新する。
    RaceCondition を返す。

    approach_stable は以下2条件どちらかで False になる:
      1. 風速 ≥5m/s または波高 ≥15cm
      2. 全艇の進入コース偏差合計 ≥ APPROACH_INSTABILITY_THRESHOLD
    """
    date_str = target_date.strftime("%Y%m%d")
    url = (f"{BASE_URL}/owpc/pc/race/beforeinfo"
           f"?jcd={stadium_code}&hd={date_str}&rno={race_no}")
    soup = _get(url)

    condition = RaceCondition()
    if not soup:
        return condition

    # ====== 天候・風速・波高 ======
    weather_text = ""
    wind_dir = ""

    # 風向き: is-direction{N} クラスの数値
    dir_el = soup.find("p", class_=lambda c: c and any("is-direction" in x for x in c))
    if dir_el:
        for cls in (dir_el.get("class") or []):
            m = re.search(r"is-direction(\d+)", cls)
            if m:
                wind_dir = m.group(1)
                break

    # 天候テキスト (晴/曇/雨)
    weather_unit = soup.find("div", class_=lambda c: c and "is-weather" in (c if isinstance(c, str) else " ".join(c)))
    if weather_unit:
        title_span = weather_unit.find("span", class_="weather1_bodyUnitLabelTitle")
        if title_span:
            weather_text = title_span.get_text(strip=True)

    # 風速・波高
    for span in soup.find_all("span", class_="weather1_bodyUnitLabelData"):
        title_el = span.find_previous("span", class_="weather1_bodyUnitLabelTitle")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        val = _extract_number(span.get_text(strip=True))
        if title == "風速" and val is not None:
            condition.wind_speed = val
        elif title == "波高" and val is not None:
            condition.wave_height = val

    # 風波による approach_stable 判定 (後でコース並びでも再判定)
    if condition.wind_speed >= 5.0 or condition.wave_height >= 15.0:
        condition.approach_stable = False

    # ====== 展示タイム・チルト (table.is-w748) ======
    entry_map = {e.lane: e for e in entries}
    tilt_map: dict[int, float] = {}

    t748 = soup.find("table", class_="is-w748")
    if t748:
        for tbody in t748.find_all("tbody"):
            rows = tbody.find_all("tr")
            if not rows:
                continue
            tds = rows[0].find_all("td")
            if len(tds) < 5:
                continue
            try:
                boat_num = int(tds[0].get_text(strip=True))
            except ValueError:
                continue
            if boat_num not in entry_map:
                continue
            extime = _extract_number(tds[4].get_text(strip=True))
            if extime is not None:
                entry_map[boat_num].exhibition_time = extime
            if len(tds) >= 6:
                tilt_raw = tds[5].get_text(strip=True)
                tilt = _extract_number(tilt_raw)
                if tilt is not None:
                    # チルト角の符号: "-" で始まるテキストは負値
                    if tilt_raw.strip().startswith("-"):
                        tilt = -tilt
                    tilt_map[boat_num] = tilt
                    entry_map[boat_num].tilt = tilt  # EntryData に保存

    # ====== 展示ST・進入コース (table.is-w238) ======
    t238 = soup.find("table", class_="is-w238")
    if t238:
        for course_idx, row in enumerate(t238.select("tbody tr")):
            course = course_idx + 1
            boat_span = row.find("span", class_="table1_boatImage1Number")
            st_span = row.find("span", class_="table1_boatImage1Time")
            if not boat_span:
                continue
            try:
                boat_num = int(boat_span.get_text(strip=True))
            except ValueError:
                continue
            if boat_num not in entry_map:
                continue
            entry_map[boat_num].approach_lane = course
            if st_span:
                st_val = _extract_number(st_span.get_text(strip=True))
                if st_val is not None:
                    entry_map[boat_num].exhibition_st = st_val

    # ====== 進入コース並びによる approach_stable 再判定 ======
    # 全艇の「本来の枠番 vs 実際の進入コース」偏差合計がしきい値を超えたら不安定扱い
    if condition.approach_stable:  # 風波で既に False の場合はスキップ
        total_deviation = sum(
            abs(e.lane - e.approach_lane)
            for e in entries
            if e.approach_lane is not None
        )
        if total_deviation >= APPROACH_INSTABILITY_THRESHOLD:
            condition.approach_stable = False
            logger.warning(
                "進入乱れ検出: 偏差合計=%d (閾値%d) → approach_stable=False",
                total_deviation, APPROACH_INSTABILITY_THRESHOLD
            )

    # ====== 取得結果ログ ======
    extime_count = sum(1 for e in entries if e.exhibition_time is not None)
    if extime_count == 0:
        logger.warning(
            "展示タイムが1艇も取得できませんでした (HTML構造の変化 or 展示未公開) "
            "stadium=%s race_no=%d date=%s",
            stadium_code, race_no, target_date.isoformat()
        )
    logger.info("天候:%s 風向:%s 風速:%.1fm 波高:%.0fcm approach_stable:%s",
                weather_text or "不明", wind_dir or "-",
                condition.wind_speed, condition.wave_height,
                condition.approach_stable)
    logger.info("展示タイム取得: %d/%d艇", extime_count, len(entries))
    for e in sorted(entries, key=lambda x: x.lane):
        tilt_str = f"{tilt_map[e.lane]:+.1f}" if e.lane in tilt_map else "N/A"
        extime_str = f"{e.exhibition_time:.2f}" if e.exhibition_time is not None else "N/A"
        exst_str = f"{e.exhibition_st:.3f}" if e.exhibition_st is not None else "N/A"
        ap_str = str(e.approach_lane) if e.approach_lane is not None else "N/A"
        logger.info("  %d号艇 exhibition_time:%s / チルト:%s / exhibition_st:%s / approach_lane:%s",
                    e.lane, extime_str, tilt_str, exst_str, ap_str)

    return condition
