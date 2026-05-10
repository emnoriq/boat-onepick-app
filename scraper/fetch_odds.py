"""
三連複オッズを取得する

URL: https://www.boatrace.jp/owpc/pc/race/odds3f?jcd={code}&hd={date}&rno={race_no}

HTML構造 (tbody[1]):
  20組み合わせが以下の順で10行に格納される:
  row0: 1-2-3                       (floats: 1個)
  row1: 1-2-4                       (floats: 1個)
  row2: 1-2-5                       (floats: 1個)
  row3: 1-2-6                       (floats: 1個)
  row4: 1-3-4, 2-3-4                (floats: 2個)
  row5: 1-3-5, 2-3-5                (floats: 2個)
  row6: 1-3-6, 2-3-6                (floats: 2個)
  row7: 1-4-5, 2-4-5, 3-4-5        (floats: 3個)
  row8: 1-4-6, 2-4-6, 3-4-6        (floats: 3個)
  row9: 1-5-6, 2-5-6, 3-5-6, 4-5-6 (floats: 4個)

  各セルのfloat値 × 100 = ¥払戻額 (per ¥100 bet)
  例: 13.3 → ¥1,330
"""

import re
import time
import logging
from datetime import date
from typing import Optional
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.boatrace.jp"
HEADERS = {"User-Agent": "boat-onepick-bot/1.0 (private research tool)"}
REQUEST_INTERVAL = 1.0

# 三連複20組み合わせの行別マッピング（固定レイアウト）
_COMBOS_BY_ROW: list[list[str]] = [
    ["1-2-3"],
    ["1-2-4"],
    ["1-2-5"],
    ["1-2-6"],
    ["1-3-4", "2-3-4"],
    ["1-3-5", "2-3-5"],
    ["1-3-6", "2-3-6"],
    ["1-4-5", "2-4-5", "3-4-5"],
    ["1-4-6", "2-4-6", "3-4-6"],
    ["1-5-6", "2-5-6", "3-5-6", "4-5-6"],
]

_FLOAT_RE = re.compile(r"^\d+\.\d+$")


def _get(url: str) -> Optional[BeautifulSoup]:
    try:
        time.sleep(REQUEST_INTERVAL)
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.debug("GET %s failed: %s", url, e)
        return None


def _normalize_pick(pick: str) -> str:
    """ピック文字列を昇順ソートした正規化済み文字列に変換 ('2-1-3' → '1-2-3')"""
    parts = sorted(int(x) for x in pick.split("-"))
    return "-".join(str(p) for p in parts)


def fetch_trifecta_box_odds(
    stadium_code: str,
    race_no: int,
    target_date: date,
) -> dict[str, int]:
    """
    三連複オッズを全20組み合わせ分取得する。

    戻り値:
        {"1-2-3": 1830, "1-2-4": 640, ...}
        key: 艇番の昇順ソート (例: "1-2-3")
        value: ¥100ベット時の払戻額 (例: 1830)
        データなし/ページ未公開の場合は空dict
    """
    date_str = target_date.strftime("%Y%m%d")
    url = (
        f"{BASE_URL}/owpc/pc/race/odds3f"
        f"?jcd={stadium_code}&hd={date_str}&rno={race_no}"
    )
    soup = _get(url)
    if not soup:
        return {}

    # データなしチェック
    body_text = soup.get_text()
    if "データがありません" in body_text:
        logger.debug("オッズデータなし: %s %dR %s", stadium_code, race_no, target_date)
        return {}

    tbodies = soup.find_all("tbody")
    if len(tbodies) < 2:
        logger.debug("oddsテーブル未検出: %s %dR", stadium_code, race_no)
        return {}

    tb = tbodies[1]
    rows = tb.find_all("tr")
    result: dict[str, int] = {}

    for row_idx, tr in enumerate(rows):
        if row_idx >= len(_COMBOS_BY_ROW):
            break

        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        # floatパターンのセルがオッズ値
        odds_values: list[float] = []
        for td in tds:
            if _FLOAT_RE.match(td):
                try:
                    odds_values.append(float(td))
                except ValueError:
                    pass

        combos = _COMBOS_BY_ROW[row_idx]
        for combo, odds in zip(combos, odds_values):
            payout = round(odds * 100)
            if payout >= 100:   # 最低払戻チェック
                result[combo] = payout

    if result:
        logger.info("三連複オッズ取得: %s %dR %d組 (最安¥%d / 最高¥%d)",
                    stadium_code, race_no, len(result),
                    min(result.values()), max(result.values()))
    else:
        logger.warning("三連複オッズ空: %s %dR", stadium_code, race_no)

    return result


def get_pick_payout(
    odds: dict[str, int],
    pick: str,
) -> Optional[int]:
    """
    pickに対応する払戻額を返す。
    pickは任意順 ('2-1-3' でも '1-2-3' でも可)。
    オッズが取得できていない場合は None。
    """
    if not odds:
        return None
    key = _normalize_pick(pick)
    return odds.get(key)
