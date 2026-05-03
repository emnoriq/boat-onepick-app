"""
出走表を取得してEntryDataのリストに変換する

HTML 構造 (racelist):
  各艇は <tr> を起点に 4行 rowspan を持つ。
  td[0] class="is-boatColor{n} is-fs14" rowspan="4" → 艇番 (全角数字)
  td[1] rowspan="4"  → 選手写真
  td[2] rowspan="4"  → 選手情報 div.is-fs11 (登録番号/級別), div.is-fs18.is-fBold a (選手名)
  td[3] class="is-lineH2" rowspan="4" → F count / L count / 平均ST (br区切り)
  td[4] class="is-lineH2" rowspan="4" → 全国勝率 / 全国2連対率 / 全国3連対率
  td[5] class="is-lineH2" rowspan="4" → 当地勝率 / 当地2連対率 / 当地3連対率
  td[6] class="is-lineH2" rowspan="4" → モーター番号 / モーター2連対率 / モーター3連対率
  td[7] class="is-lineH2" rowspan="4" → ボート番号 / ボート2連対率 / ボート3連対率
"""

import time
import logging
from datetime import date
from typing import Optional
import requests
from bs4 import BeautifulSoup

from scoring import EntryData

logger = logging.getLogger(__name__)

BASE_URL = "https://www.boatrace.jp"
HEADERS = {"User-Agent": "boat-onepick-bot/1.0 (private research tool)"}
REQUEST_INTERVAL = 1.0  # 公式サイトへの負荷を抑えつつ高速化（旧: 2.0s）

_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


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


def _lines(td) -> list[str]:
    """td の中身を <br> 区切りで行リストに変換"""
    return [l.strip() for l in td.get_text(separator="\n").strip().split("\n") if l.strip()]


def _float(lines: list[str], idx: int) -> float:
    try:
        return float(lines[idx])
    except (IndexError, ValueError):
        return 0.0


def fetch_entries(stadium_code: str, race_no: int, target_date: date) -> list[EntryData]:
    """出走表から各艇情報を取得"""
    date_str = target_date.strftime("%Y%m%d")
    url = (f"{BASE_URL}/owpc/pc/race/racelist"
           f"?jcd={stadium_code}&hd={date_str}&rno={race_no}")
    soup = _get(url)
    if not soup:
        return []

    entries = []

    for tr in soup.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 8:
            continue

        # 艇番セル: class に is-boatColor{n} と is-fs14 の両方を持つ
        first_cls = tds[0].get("class") or []
        if not ("is-fs14" in first_cls and any("is-boatColor" in c for c in first_cls)):
            continue

        # 全角艇番 → int
        lane_text = tds[0].get_text(strip=True).translate(_FULLWIDTH_DIGITS)
        try:
            lane = int(lane_text)
        except ValueError:
            continue
        if lane < 1 or lane > 6:
            continue

        # 選手情報 (td[2])
        info_td = tds[2]
        racer_class = ""
        fs11 = info_td.find("div", class_="is-fs11")
        if fs11:
            span = fs11.find("span")
            racer_class = (span.get_text(strip=True) if span else "").upper()

        racer_name = ""
        fs18 = info_td.find("div", class_="is-fs18")
        if fs18:
            a = fs18.find("a")
            racer_name = (a.get_text(strip=True) if a else fs18.get_text(strip=True))

        # F/L/平均ST (td[3])
        fl = _lines(tds[3])
        f_count = 0
        l_count = 0
        avg_st = 0.15
        for token in fl:
            if token.startswith("F"):
                try: f_count = int(token[1:])
                except ValueError: pass
            elif token.startswith("L"):
                try: l_count = int(token[1:])
                except ValueError: pass
            else:
                try: avg_st = float(token)
                except ValueError: pass

        # 全国勝率 (td[4] line0), 当地勝率 (td[5] line0)
        nat = _lines(tds[4])
        loc = _lines(tds[5])
        national_win_rate = _float(nat, 0)
        local_win_rate    = _float(loc, 0)

        # モーター2連対率 (td[6] line1), ボート2連対率 (td[7] line1)
        mot = _lines(tds[6])
        bot = _lines(tds[7])
        motor_rate = _float(mot, 1)
        boat_rate  = _float(bot, 1)

        entries.append(EntryData(
            lane=lane,
            racer_name=racer_name,
            racer_class=racer_class,
            national_win_rate=national_win_rate,
            local_win_rate=local_win_rate,
            motor_rate=motor_rate,
            boat_rate=boat_rate,
            avg_st=avg_st,
            f_count=f_count,
            l_count=l_count,
        ))

    entries.sort(key=lambda e: e.lane)
    return entries
