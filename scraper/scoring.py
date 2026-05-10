"""
3着以内スコア計算モジュール
朝スコア(70点満点) + 直前スコア(30点満点) = 総合スコア(100点満点)

【スコア構成】
朝スコア (70点上限):
  選手力  20点  = 級別10 + 全国勝率5 + ボート2連対率5
  モーター 15点
  枠      10点
  スタート 10点
  当地相性 10点
  合計最大  65点 (安定した選手ほど満点に近づく)

直前スコア (30点上限):
  展示タイム  10点  ← 艦隊平均との相対評価
  展示ST       5点  ← 艦隊平均との相対評価
  チルト補正   5点  ← チルト角から周回安定度を推定
  進入補正     5点  ← インへの動き = ボーナス / アウトへの動き = ペナルティ
  風波補正     5点

修正履歴:
  - local_win_rate の二重計上を解消 (player ブロック → national_win_rate + boat_rate に変更)
  - A1/A2 roughness ボーナスを削除 (class_score で既に反映済み)
  - 展示タイム/ST を絶対評価から艦隊平均との相対評価に変更
  - チルト角を scoring に反映 (展示データあり時のみ)
  - 進入コース補正を方向性考慮型に変更 (インへの動き = ボーナス)
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class EntryData:
    lane: int
    racer_name: str
    racer_class: str = ""           # A1 / A2 / B1 / B2
    national_win_rate: float = 0.0  # 全国勝率
    local_win_rate: float = 0.0     # 当地勝率
    motor_rate: float = 0.0         # モーター2連対率
    boat_rate: float = 0.0          # ボート2連対率
    avg_st: float = 0.15            # 平均スタートタイム
    f_count: int = 0                # F(フライング)回数
    l_count: int = 0                # L(出遅れ)回数
    # 直前情報
    exhibition_time: Optional[float] = None   # 展示タイム
    exhibition_st: Optional[float] = None     # 展示スタートタイム
    turn_stability: Optional[float] = None    # 周回展示の安定度 (0〜1, 未使用 → tilt で代替)
    approach_lane: Optional[int] = None       # 進入コース
    tilt: Optional[float] = None              # チルト角 (-3.0〜+3.0)


@dataclass
class RaceCondition:
    wind_speed: float = 0.0    # m/s
    wave_height: float = 0.0   # cm
    approach_stable: bool = True  # 進入が枠なり安定かどうか


@dataclass
class EntryScore:
    lane: int
    racer_name: str
    morning_score: float = 0.0
    pre_race_score: float = 0.0

    @property
    def total(self) -> float:
        return self.morning_score + self.pre_race_score

    def to_dict(self) -> dict:
        return {
            "lane": self.lane,
            "racer_name": self.racer_name,
            "morning_score": round(self.morning_score, 2),
            "pre_race_score": round(self.pre_race_score, 2),
            "total": round(self.total, 2),
        }


def _class_score(racer_class: str) -> float:
    """級別点 (A1最大、B2最小)"""
    table = {"A1": 10.0, "A2": 7.0, "B1": 4.0, "B2": 2.0}
    return table.get(racer_class.upper(), 3.0)


def _win_rate_score(rate: float) -> float:
    """勝率を0〜5点にマッピング"""
    return min(5.0, max(0.0, (rate - 3.0) * 2.0))


def _motor_score(rate: float) -> float:
    """モーター2連対率を0〜15点にマッピング"""
    return min(15.0, max(0.0, (rate - 30.0) * 0.3))


def _boat_rate_score(rate: float) -> float:
    """ボート2連対率を0〜5点にマッピング"""
    return min(5.0, max(0.0, (rate - 30.0) * 0.1))


def _lane_score(lane: int) -> float:
    """
    枠有利不利 (インほど有利)
    1号艇: 10点、以降1.8点ずつ減少
    """
    return max(0.0, 10.0 - (lane - 1) * 1.8)


def _st_score(avg_st: float, f_count: int, l_count: int) -> float:
    """
    平均ST・F/L持ちを0〜10点に変換
    STが小さいほど有利。Fがあると大きく減点
    """
    base = max(0.0, 10.0 - (avg_st - 0.10) * 100.0)
    penalty = f_count * 3.0 + l_count * 2.0
    return max(0.0, base - penalty)


def _local_rate_score(rate: float) -> float:
    """当地成績スコア 0〜10点"""
    return min(10.0, max(0.0, rate * 2.0))


def morning_score(entry: EntryData) -> float:
    """
    朝スコア計算 (最大65点程度 / cap 70点)

    【修正点】
    - player ブロックを national_win_rate + boat_rate に変更
      (旧: national + local → local_win_rate が local ブロックと二重計上だったため修正)
    - roughness ボーナス(旧: A1/A2に+5)を削除
      (class_score と win_rate_score で既に A1 優位が反映されている)
    """
    # 選手力 (20点)
    player = min(20.0,
        _class_score(entry.racer_class)               # 10
        + _win_rate_score(entry.national_win_rate)    # 5 (全国勝率)
        + _boat_rate_score(entry.boat_rate)           # 5 (ボート2連対率: 新規追加)
    )

    # モーター (15点)
    motor = _motor_score(entry.motor_rate)

    # 枠・コース (10点)
    lane = _lane_score(entry.lane)

    # スタート力 (10点)
    st = _st_score(entry.avg_st, entry.f_count, entry.l_count)

    # 当地相性 (10点)  ← local_win_rate はここだけで使用
    local = _local_rate_score(entry.local_win_rate)

    return min(70.0, player + motor + lane + st + local)


def pre_race_score(
    entry: EntryData,
    condition: RaceCondition,
    fleet_avg_ex_time: Optional[float] = None,
    fleet_avg_ex_st: Optional[float] = None,
) -> float:
    """
    直前スコア計算 (最大30点)

    展示タイム10 + 展示ST5 + チルト/周回展示5 + 進入安定5 + 風波5

    【修正点】
    - 展示タイム/ST: 絶対値基準 → 艦隊平均との相対評価に変更
      同じ 6.78s でも艦隊平均が 6.70s の場合と 6.85s の場合で意味が異なる
    - チルト角を scoring に反映: +1.0〜+2.0 が最適ゾーン
    - 進入コース: フラット-1.5 → 方向性考慮 (インへの動き=ボーナス / アウト=ペナルティ)

    Args:
        fleet_avg_ex_time: 同レースの全艇展示タイム平均 (None = フォールバック絶対評価)
        fleet_avg_ex_st:   同レースの全艇展示ST平均    (None = フォールバック絶対評価)
    """
    if entry.exhibition_time is None:
        return 0.0

    # ── 展示タイム (10点) ── 艦隊相対評価 ───────────────────────────────────
    if fleet_avg_ex_time is not None:
        # 艦隊平均より 0.04s 速い → +1.0点 相当 (= 25点/秒スケール)
        # 中間 (= 平均) → 5.0点
        ex_time_score = max(0.0, min(10.0,
            5.0 + (fleet_avg_ex_time - entry.exhibition_time) * 25.0
        ))
    else:
        # フォールバック: 6.90s 基準の絶対評価
        ex_time_score = max(0.0, min(10.0,
            (6.90 - entry.exhibition_time) * 25.0
        ))

    # ── 展示ST (5点) ── 艦隊相対評価 ─────────────────────────────────────────
    if entry.exhibition_st is not None:
        if fleet_avg_ex_st is not None:
            # 艦隊平均より 0.01 早い → +0.5点
            # 中間 (= 平均) → 2.5点
            ex_st_score = max(0.0, min(5.0,
                2.5 + (fleet_avg_ex_st - entry.exhibition_st) * 50.0
            ))
        else:
            # フォールバック: 0.10s 基準
            ex_st_score = max(0.0, min(5.0,
                5.0 - (entry.exhibition_st - 0.10) * 50.0
            ))
    else:
        ex_st_score = 2.5  # データなし: 中間値

    # ── チルト補正 (5点) ── 展示データあり時のみ ────────────────────────────
    # チルト角の意味:
    #   高い正値 (+2〜+3): 強攻めセット → タイムは速いがターン不安定リスク
    #   適度な正値 (+0.5〜+2): 攻め気配 → バランス良く良い
    #   0 付近: 標準セット → 安定
    #   負値 (-3〜0): 守りセット → 安定だが伸び鈍い
    if entry.tilt is not None:
        if 0.5 <= entry.tilt <= 2.0:
            turn_score = 5.0  # 適度な攻めセット: 最良
        elif entry.tilt > 2.0:
            turn_score = 3.5  # 攻めすぎ: ターンリスク
        elif entry.tilt < -1.0:
            turn_score = 3.0  # 強守り: 伸びが鈍い
        else:
            turn_score = 4.5  # neutral 〜 軽い攻め
    else:
        # チルトデータなし: turn_stability フォールバック
        turn_score = (entry.turn_stability or 0.5) * 5.0

    # ── 進入コース補正 (5点) ── 方向性考慮 ──────────────────────────────────
    # deviation = entry.lane - entry.approach_lane
    # 正値 = インに動いた (有利: コース取り成功)
    # 負値 = アウトに動いた (不利: 外に押し出された)
    approach_score = 5.0 if condition.approach_stable else 2.0
    if entry.approach_lane is not None:
        deviation = entry.lane - entry.approach_lane
        if deviation > 0:
            # インに動いた → コース取り成功ボーナス
            # 6枠が1コース進入 (deviation=5) → +4.0点 最大
            approach_score += deviation * 0.8
        elif deviation < 0:
            # アウトに動いた → 外押し出しペナルティ
            # 1枠が2コース以降 (deviation=-1) → -1.2点
            approach_score = max(0.0, approach_score + deviation * 1.2)

    # ── 風・波補正 (5点) ─────────────────────────────────────────────────────
    wind_penalty = min(3.0, condition.wind_speed * 0.4)
    wave_penalty = min(2.0, condition.wave_height * 0.02)
    condition_score = max(0.0, 5.0 - wind_penalty - wave_penalty)

    return min(30.0, ex_time_score + ex_st_score + turn_score + approach_score + condition_score)


def score_entries(entries: list[EntryData], condition: RaceCondition) -> list[EntryScore]:
    """
    全艇のスコアを計算してソート済みリストを返す。

    展示データが揃っている場合は艦隊平均を計算して相対評価に使用する。
    """
    # 艦隊平均を計算 (展示データあり艇のみ)
    ex_times = [e.exhibition_time for e in entries if e.exhibition_time is not None]
    ex_sts   = [e.exhibition_st   for e in entries if e.exhibition_st   is not None]
    fleet_avg_ex_time = sum(ex_times) / len(ex_times) if ex_times else None
    fleet_avg_ex_st   = sum(ex_sts)   / len(ex_sts)   if ex_sts   else None

    scores = []
    for e in entries:
        ms = morning_score(e)
        ps = pre_race_score(e, condition, fleet_avg_ex_time, fleet_avg_ex_st)
        scores.append(EntryScore(lane=e.lane, racer_name=e.racer_name,
                                 morning_score=ms, pre_race_score=ps))
    scores.sort(key=lambda s: s.total, reverse=True)
    return scores


def make_pick(scores: list[EntryScore]) -> str:
    """上位3艇を三連複1点として返す (例: '1-2-4')"""
    top3 = sorted(scores[:3], key=lambda s: s.lane)
    return "-".join(str(s.lane) for s in top3)


def gap_between_3rd_4th(scores: list[EntryScore]) -> float:
    """3番手と4番手のスコア差"""
    if len(scores) < 4:
        return 100.0
    return scores[2].total - scores[3].total


def decide(
    scores: list[EntryScore],
    condition: RaceCondition,
    pick_payout: Optional[int] = None,
) -> dict:
    """
    買い / 候補 / ウォッチ / 見送り 判定

    decision は "buy" | "candidate" | "skip" の3値 (DB制約を維持)。
    watch は decision="skip" の一部で、reason に "[watch]" マーカーを付与。
    フロントエンドは reason の "[watch]" を検出して表示を切り替える。

    # ===== バックテスト調整済み閾値（2026-05-10 / 7日間・1226件） =====
    # confidence = avg_top3 × (1 + gap/200)。avg_top3 の現実的上限 ≈ 75。
    # buy:       confidence ≥ 67 かつ gap ≥ 10  (S ランク) ← 旧70 / ROI -10.6%
    # candidate: confidence ≥ 59 かつ gap ≥ 7   (A ランク) ← 旧62
    # watch:     confidence ≥ 55 かつ gap ≥ 7   (B ランク, decision=skip)
    # skip:      それ未満                         (C ランク)
    # ──────────────────────────────────────────────────────────────────
    # [払戻フィルター] pick_payout が指定された場合、以下を適用:
    #   buy     ← payout < 400円 → candidate に降格
    #   candidate ← payout < 250円 → skip に降格
    #   根拠: 的中率30%で損益分岐 = ¥333/¥100bet。¥400で安全マージン確保。
    # ==============================================================

    Args:
        scores:       EntryScore リスト（スコア降順）
        condition:    レース条件（風速・波高・進入）
        pick_payout:  三連複オッズから取得したpickの払戻額(¥/¥100bet)。
                      None の場合は払戻フィルターをスキップ（朝スキャン等）。

    Returns:
        {
            "pick":       "1-2-4",
            "confidence": 65.0,
            "decision":   "buy" | "candidate" | "skip",
            "is_watch":   False,
            "rank":       "S" | "A" | "B" | "C",
            "reason":     [...],
            "gap":        12.5,
        }
    """
    gap = gap_between_3rd_4th(scores)
    pick = make_pick(scores)
    reasons: list[str] = []

    # 荒れ条件チェック
    wind_rough        = condition.wind_speed  >= 5.0
    wave_rough        = condition.wave_height >= 15.0
    approach_unstable = not condition.approach_stable

    if wind_rough:
        reasons.append(f"風速 {condition.wind_speed}m/s — 荒れ要因")
    if wave_rough:
        reasons.append(f"波高 {condition.wave_height}cm — 荒れ要因")
    if approach_unstable:
        reasons.append("進入が乱れる可能性あり")

    avg_top3   = sum(s.total for s in scores[:3]) / 3 if scores else 0.0
    confidence = min(100.0, avg_top3 * (1 + gap / 200))

    # ── 1号艇インコース補正 ────────────────────────────────────────────────
    # ボートレース三連複において 1号艇1着率は約50〜55%。
    # 1号艇がスコア上位なら信頼度UP、pick外なら波乱リスクとして DOWN。
    lane1_rank = next((i for i, s in enumerate(scores) if s.lane == 1), -1)
    if lane1_rank == 0:    # 1号艇1位 → 逃げ期待大
        lane1_mul = 1.08
    elif lane1_rank == 1:  # 2位 → 差し展開
        lane1_mul = 1.04
    elif lane1_rank == 2:  # 3位 → pick内ギリギリ
        lane1_mul = 1.00
    else:                  # 4位以下（pick外）→ 大波乱リスク
        lane1_mul = 0.90
    confidence = min(100.0, confidence * lane1_mul)

    forced_skip = wind_rough or wave_rough or approach_unstable

    is_watch = False

    # 1号艇ランクを reason に記録（デバッグ・検証用）
    lane1_label = ["1位", "2位", "3位", "4位以下"][min(lane1_rank, 3)] if lane1_rank >= 0 else "不明"

    if not forced_skip and confidence >= 67 and gap >= 10:
        decision = "buy"
        rank = "S"
        reasons.append(f"上位3艇のスコア差が明確 (gap={gap:.1f} / 1号艇{lane1_label})")

    elif not forced_skip and confidence >= 59 and gap >= 7:
        decision = "candidate"
        rank = "A"
        reasons.append(f"上位3艇が安定 (gap={gap:.1f} / 1号艇{lane1_label})")

    elif not forced_skip and confidence >= 55 and gap >= 7:
        # watch: 実投票対象外、検証候補
        decision  = "skip"
        rank      = "B"
        is_watch  = True
        reasons.append(f"[watch] 検証候補 — gap={gap:.1f} / conf={round(confidence, 1)} / 1号艇{lane1_label}")

    else:
        decision = "skip"
        rank = "C"
        if forced_skip:
            reasons.append(f"荒れ条件のため見送り (gap={gap:.1f})")
        else:
            reasons.append(f"上位候補が絞れていない (gap={gap:.1f} / 1号艇{lane1_label})")

    # ── 払戻フィルター（pick_payout が取得できた場合のみ適用）─────────────
    # 低オッズ（人気すぎる組み合わせ）は期待値がマイナスになるため降格する。
    # BUY:       ¥400未満 → candidate に降格（的中率30%での損益分岐は¥333）
    # CANDIDATE: ¥250未満 → skip に降格
    if pick_payout is not None and pick_payout > 0:
        reasons.append(f"三連複オッズ: ¥{pick_payout}/¥100")
        if decision == "buy" and pick_payout < 400:
            decision = "candidate"
            rank = "A"
            reasons.append(f"⚠️ 払戻¥{pick_payout} < ¥400 → candidate に降格")
        elif decision == "candidate" and pick_payout < 250:
            decision = "skip"
            rank = "C"
            reasons.append(f"⚠️ 払戻¥{pick_payout} < ¥250 → skip に降格")

    return {
        "pick":       pick,
        "confidence": round(confidence, 2),
        "decision":   decision,
        "is_watch":   is_watch,
        "rank":       rank,
        "reason":     reasons,
        "scores":     [s.to_dict() for s in scores],
        "gap":        round(gap, 2),
    }
