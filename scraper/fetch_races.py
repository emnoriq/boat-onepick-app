"""
当日のレース一覧をボートレース公式サイトから取得する
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
REQUEST_INTERVAL = 1.0  # 公式サイトへの負荷を抑えつつ高速化（旧: 2.0s）

_RACE_NO_RE = re.compile(r"^(\d{1,2})R$")


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


def fetch_today_schedule(target_date: date) -> list[dict]:
    """
    当日の開催場一覧を取得する。
    戻り値: [{"stadium_code": "01", "stadium": "桐生"}, ...]

    HTML 構造:
      各場は <tbody> を持つ。
      <td class="is-arrow1 ..."><a href="javascript:..."><img alt="桐生" .../></a></td>
      <td class="is-alignL is-fBold is-p10-7"><a href="/owpc/pc/race/raceindex?jcd=01&hd=...">競走名</a></td>
    """
    date_str = target_date.strftime("%Y%m%d")
    url = f"{BASE_URL}/owpc/pc/race/index?hd={date_str}"
    soup = _get(url)
    if not soup:
        return []

    stadiums = []
    seen_codes: set[str] = set()

    for tbody in soup.find_all("tbody"):
        # 場名: td.is-arrow1 の img[alt]
        img = tbody.find("img", alt=lambda a: a and a.strip())
        if not img:
            continue
        name = img["alt"].strip()

        # 場コード: raceindex リンクの jcd=XX
        link = tbody.find("a", href=lambda h: h and "raceindex" in h and "jcd=" in h)
        if not link:
            continue
        m = re.search(r"jcd=(\d+)", link["href"])
        if not m:
            continue
        code = m.group(1)

        if code in seen_codes:
            continue
        seen_codes.add(code)
        stadiums.append({"stadium_code": code, "stadium": name})

    logger.info("本日の開催場: %d場", len(stadiums))
    return stadiums


def fetch_race_list(stadium_code: str, target_date: date) -> list[dict]:
    """
    指定場の当日全レース一覧を取得する。
    戻り値: [{"race_no": 1, "close_time_str": "15:48"}, ...]

    HTML 構造 (raceindex):
      <td class="is-fs14 is-fBold">1R</td>  → td[0]: "1R"
      <td>15:48</td>                          → td[1]: 締切時刻
    """
    date_str = target_date.strftime("%Y%m%d")
    url = f"{BASE_URL}/owpc/pc/race/raceindex?jcd={stadium_code}&hd={date_str}"
    soup = _get(url)
    if not soup:
        return []

    races = []
    seen: set[int] = set()

    for td in soup.find_all("td"):
        text = td.get_text(strip=True)
        m = _RACE_NO_RE.match(text)
        if not m:
            continue
        race_no = int(m.group(1))
        if race_no in seen:
            continue

        tr = td.find_parent("tr")
        if not tr:
            continue
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue

        time_text = tds[1].get_text(strip=True)[:5]
        if not re.match(r"\d{2}:\d{2}", time_text):
            continue

        seen.add(race_no)
        races.append({"race_no": race_no, "close_time_str": time_text})

    races.sort(key=lambda r: r["race_no"])
    return races
