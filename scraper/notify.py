"""
ntfy プッシュ通知モジュール

BUY判定が出たときにスマートフォンへ通知を送る。
トピック: ntfy.sh/boat-onepick-takamitsu

環境変数:
  NTFY_TOPIC : ntfy トピック名 (default: boat-onepick-takamitsu)
  NTFY_URL   : ntfy サーバーURL (default: https://ntfy.sh)
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_NTFY_TOPIC = os.getenv("NTFY_TOPIC", "boat-onepick-takamitsu")
_NTFY_BASE  = os.getenv("NTFY_URL",   "https://ntfy.sh")
_NTFY_URL   = f"{_NTFY_BASE}/{_NTFY_TOPIC}"


def _send(title: str, body: str, priority: str = "default", tags: str = "") -> bool:
    """ntfy に POST する低レベル関数。失敗しても例外を投げない。"""
    try:
        import urllib.request
        headers = {
            "Title":    title.encode("utf-8"),
            "Priority": priority.encode("utf-8"),
        }
        if tags:
            headers["Tags"] = tags.encode("utf-8")

        req = urllib.request.Request(
            _NTFY_URL,
            data=body.encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            ok = resp.status == 200
            if not ok:
                logger.warning("ntfy 送信失敗: status=%d", resp.status)
            return ok
    except Exception as e:
        logger.warning("ntfy 送信エラー (無視して続行): %s", e)
        return False


def notify_buy(
    stadium:    str,
    race_no:    int,
    pick:       str,
    confidence: float,
    best_ev:    Optional[float] = None,
    race_time:  Optional[str]   = None,
) -> None:
    """
    BUY 判定通知。

    例:
      🎯 常滑 8R  BUY
      pick: 1-2-4
      confidence: 72.3
      EV: +0.28
      締切: 14:52
    """
    ev_line   = f"EV: {best_ev:+.2f}\n" if best_ev is not None else ""
    time_line = f"締切: {race_time}\n"   if race_time            else ""

    title = f"🎯 {stadium} {race_no}R  BUY"
    body  = (
        f"pick: {pick}\n"
        f"confidence: {confidence:.1f}\n"
        f"{ev_line}"
        f"{time_line}"
    ).strip()

    _send(title, body, priority="high", tags="boat,money_with_wings")
    logger.info("ntfy 送信: %s", title)


def notify_hit(
    stadium:  str,
    race_no:  int,
    pick:     str,
    payout:   int,
) -> None:
    """的中通知（result_scan から呼ぶ）"""
    title = f"✅ {stadium} {race_no}R  的中！"
    body  = f"pick: {pick}\n払戻: ¥{payout:,}"
    _send(title, body, priority="high", tags="tada,yen")
    logger.info("ntfy 的中通知: %s", title)


def notify_miss(
    stadium: str,
    race_no: int,
    pick:    str,
    result:  str,
) -> None:
    """BUY 外れ通知（result_scan から呼ぶ）"""
    title = f"❌ {stadium} {race_no}R  外れ"
    body  = f"予想: {pick}\n結果: {result}"
    _send(title, body, priority="default", tags="x")
    logger.info("ntfy 外れ通知: %s", title)
