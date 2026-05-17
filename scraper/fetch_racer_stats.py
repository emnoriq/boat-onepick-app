"""
選手詳細スタッツ取得モジュール

boatrace.jp のコース別成績ページから各コース3連対率を取得する。
URL: https://www.boatrace.jp/owpc/pc/data/racersearch/course?toban={racer_no}

HTML 構造:
    Table 1: コース別3連対率 (1着率・2着率・3着率を内包)
      <th class="is-boatColor{N}"> → コース番号
      <span class="table1_progress2Label">XX.X%</span> → 3連対率合計
      各 <span class="is-progress" style="width: XX.X%"> → 順に 1着率, 2着率, 3着率

取得するデータ:
    c{N}_win_rate = コース N からの3連対率 (%) [三連複ベット向け]
    ※ 命名は win_rate だが実際は top-3 rate = 三連複的中率の近似

キャッシュ:
    同一プロセス内では racer_no → 結果を dict にキャッシュ。
    同じ選手が複数レースに出場しても1回だけリクエストする。
"""

import re
import time
import logging
from typing import Optional
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.boatrace.jp"
HEADERS = {"User-Agent": "boat-onepick-bot/1.0 (private research tool)"}
REQUEST_INTERVAL = 1.2  # 公式サイトへの負荷軽減

# プロセス内キャッシュ: {racer_no: {1: 76.5, 2: 19.0, ...}}
_CACHE: dict[str, dict[int, float]] = {}

_FULLWIDTH = str.maketrans("１２３４５６", "123456")


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


def fetch_course_win_rates(racer_no: str) -> dict[int, float]:
    """
    指定選手のコース別3連対率 (%) を取得して返す。

    三連複ベット向け: コース N に進入したとき何%で3着以内に入るか。

    Args:
        racer_no: 登録番号 (例: "4204")

    Returns:
        {1: 76.5, 2: 19.0, 3: 42.9, 4: 35.0, 5: 30.0, 6: 17.6}
        取得失敗の場合は空 dict。
    """
    if not racer_no:
        return {}

    if racer_no in _CACHE:
        return _CACHE[racer_no]

    url = f"{BASE_URL}/owpc/pc/data/racersearch/course?toban={racer_no}"
    soup = _get(url)
    if not soup:
        _CACHE[racer_no] = {}
        return {}

    result = _parse_course_stats(soup, racer_no)
    _CACHE[racer_no] = result
    return result


def _parse_course_stats(soup: BeautifulSoup, racer_no: str) -> dict[int, float]:
    """
    コース別成績ページから3連対率を抽出する。

    HTML 構造:
        Table 1 (<table class="is-w400">の2番目):
          <tbody>
            <tr>
              <th class="is-boatColor{N} ...">N</th>
              <td>
                <div class="table1_progress2">
                  <span class="table1_progress2Label">76.5%</span>
                </div>
              </td>
            </tr>
          </tbody>

    3連対率 = label テキスト (76.5 % → 76.5)
    """
    result: dict[int, float] = {}

    tables = soup.find_all("table")
    if len(tables) < 2:
        logger.warning("racer %s: コース別成績テーブルが見つかりません (tables=%d)", racer_no, len(tables))
        return result

    # Table 1 = コース別3連対率テーブル (0始まりで index 1)
    table = tables[1]

    for tr in table.find_all("tr"):
        # コース番号を is-boatColor{N} クラスの th から取得
        th = tr.find("th", class_=re.compile(r"is-boatColor\d"))
        if not th:
            continue

        course_text = th.get_text(strip=True).translate(_FULLWIDTH)
        try:
            course = int(course_text)
        except ValueError:
            continue
        if not 1 <= course <= 6:
            continue

        # 3連対率ラベルを取得
        label_span = tr.find("span", class_="table1_progress2Label")
        if not label_span:
            # フォールバック: is-progress の style width から取得
            progress_spans = tr.find_all("span", class_="is-progress")
            if progress_spans:
                total = 0.0
                for span in progress_spans:
                    style = span.get("style", "")
                    m = re.search(r"width:\s*([\d.]+)%", style)
                    if m:
                        total += float(m.group(1))
                result[course] = round(total, 1)
            continue

        rate_text = label_span.get_text(strip=True).rstrip("%").strip()
        try:
            result[course] = float(rate_text)
        except ValueError:
            logger.debug("racer %s コース%d: rate parse失敗 '%s'", racer_no, course, rate_text)

    if result:
        logger.info(
            "racer %s: コース別3連対率取得成功 %s",
            racer_no,
            " ".join(f"{c}C:{v:.1f}%" for c, v in sorted(result.items()))
        )
    else:
        logger.warning("racer %s: コース別成績の解析に失敗", racer_no)

    return result


def apply_course_win_rates(entry, rates: dict[int, float]) -> None:
    """
    EntryData に コース別3連対率を適用する（in-place）。

    Args:
        entry: scoring.EntryData インスタンス
        rates: fetch_course_win_rates() の戻り値
    """
    if not rates:
        return
    entry.c1_win_rate = rates.get(1, 0.0)
    entry.c2_win_rate = rates.get(2, 0.0)
    entry.c3_win_rate = rates.get(3, 0.0)
    entry.c4_win_rate = rates.get(4, 0.0)
    entry.c5_win_rate = rates.get(5, 0.0)
    entry.c6_win_rate = rates.get(6, 0.0)


def clear_cache() -> None:
    """テスト・デバッグ用にキャッシュをクリア"""
    _CACHE.clear()
