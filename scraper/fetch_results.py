"""
レース結果を取得してDBに保存する
"""

import time
import logging
from typing import Optional
from datetime import date
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.boatrace.jp"
HEADERS = {"User-Agent": "boat-onepick-bot/1.0 (private research tool)"}
REQUEST_INTERVAL = 2.0


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


def _to_int(text: str) -> Optional[int]:
    try:
        # "¥310" / "1,234" などを処理
        cleaned = text.strip().replace(",", "").replace("¥", "").replace("￥", "")
        return int(cleaned)
    except (ValueError, AttributeError):
        return None


def fetch_result(stadium_code: str, race_no: int, target_date: date) -> Optional[dict]:
    """
    三連複の結果・払戻・人気を取得する。
    戻り値: {"trifecta_result": "1-2-3", "payout": 310, "popularity": 1}
    """
    date_str = target_date.strftime("%Y%m%d")
    url = (f"{BASE_URL}/owpc/pc/race/raceresult"
           f"?jcd={stadium_code}&hd={date_str}&rno={race_no}")
    logger.info("結果ページ取得: %s", url)
    soup = _get(url)
    if not soup:
        return None

    # 払戻テーブルを探す: "勝式" ヘッダを含む table.is-w495
    payout_table = None
    for tbl in soup.select("table.is-w495"):
        header_text = tbl.get_text()
        if "勝式" in header_text:
            payout_table = tbl
            break

    if not payout_table:
        logger.warning("払戻テーブルが見つかりません (url=%s)", url)
        return None

    result = {}
    for tr in payout_table.select("tbody tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        label = tds[0].get_text(strip=True)
        # HTMLでは "3連複" (漢字でなく数字)
        if "3連複" not in label:
            continue
        if len(tds) >= 3:
            # "1=2=3" → "1-2-3"
            combination = tds[1].get_text(strip=True).replace("=", "-")
            payout = _to_int(tds[2].get_text(strip=True))
            result["trifecta_result"] = combination
            result["payout"] = payout
            logger.info("3連複: %s 払戻: %s円", combination, payout)
        if len(tds) >= 4:
            result["popularity"] = _to_int(tds[3].get_text(strip=True))
            logger.info("人気: %s", result["popularity"])
        break

    return result if result else None
