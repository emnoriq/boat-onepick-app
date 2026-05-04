"""
3着以内スコア計算モジュール
朝スコア(70点満点) + 直前スコア(30点満点) = 総合スコア(100点満点)
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
    turn_stability: Optional[float] = None    # 周回展示の安定度 (0〜1)
    approach_lane: Optional[int] = None       # 進入コース


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


def _lane_score(lane: int) -> float:
    """
    枠有利不利 (インほど有利)
    1号艇: 10点、以降1点ずつ減少
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
    朝スコア計算 (最大70点)
    選手力20 + モーター15 + 枠10 + スタート力10 + 当地相性10 + 荒れにくさ5
    """
    # 選手力 (20点)
    player = (
        _class_score(entry.racer_class)        # 10
        + _win_rate_score(entry.national_win_rate)  # 5
        + _win_rate_score(entry.local_win_rate)     # 5
    )
    player = min(20.0, player)

    # モーター (15点)
    motor = _motor_score(entry.motor_rate)

    # 枠・コース (10点)
    lane = _lane_score(entry.lane)

    # スタート力 (10点)
    st = _st_score(entry.avg_st, entry.f_count, entry.l_count)

    # 当地相性 (10点)
    local = _local_rate_score(entry.local_win_rate)

    # 荒れにくさ: 全項目のばらつきが小さい場合に加点 (最大5点)
    roughness = 5.0 if entry.racer_class.upper() in ("A1", "A2") else 2.5

    return min(70.0, player + motor + lane + st + local + roughness)


def pre_race_score(entry: EntryData, condition: RaceCondition) -> float:
    """
    直前スコア計算 (最大30点)
    展示タイム10 + 展示ST5 + 周回展示5 + 進入安定5 + 風波5
    """
    if entry.exhibition_time is None:
        return 0.0

    # 展示タイム (10点) — タイムが小さいほど足が良い
    # 標準的な展示タイム帯: 6.50〜6.90秒 程度
    ex_time_score = max(0.0, min(10.0, (6.90 - entry.exhibition_time) * 25.0))

    # 展示ST (5点)
    if entry.exhibition_st is not None:
        ex_st_score = max(0.0, min(5.0, 5.0 - (entry.exhibition_st - 0.10) * 50.0))
    else:
        ex_st_score = 2.5  # データなし: 中間値

    # 周回展示安定度 (5点)
    turn_score = (entry.turn_stability or 0.5) * 5.0

    # 進入安定 (5点)
    approach_score = 5.0 if condition.approach_stable else 2.0
    if entry.approach_lane is not None and entry.approach_lane != entry.lane:
        approach_score -= 1.5  # コース変更時は減点

    # 風・波補正 (5点) — レース全体の補正なので均等に配分
    wind_penalty = min(3.0, condition.wind_speed * 0.4)
    wave_penalty = min(2.0, condition.wave_height * 0.02)
    condition_score = max(0.0, 5.0 - wind_penalty - wave_penalty)

    return min(30.0, ex_time_score + ex_st_score + turn_score + approach_score + condition_score)


def score_entries(entries: list[EntryData], condition: RaceCondition) -> list[EntryScore]:
    """全艇のスコアを計算してソート済みリストを返す"""
    scores = []
    for e in entries:
        ms = morning_score(e)
        ps = pre_race_score(e, condition)
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


def decide(scores: list[EntryScore], condition: RaceCondition) -> dict:
    """
    買い / 候補 / ウォッチ / 見送り 判定

    decision は "buy" | "candidate" | "skip" の3値 (DB制約を維持)。
    watch は decision="skip" の一部で、reason に "[watch]" マーカーを付与。
    フロントエンドは reason の "[watch]" を検出して表示を切り替える。

    # ===== MVP検証用の暫定閾値（30日分データ蓄積後に再調整する） =====
    # confidence = avg_top3 × (1 + gap/200)。avg_top3 の現実的上限 ≈ 75。
    # buy:       confidence ≥ 70 かつ gap ≥ 10  (S ランク)
    # candidate: confidence ≥ 62 かつ gap ≥ 7   (A ランク)
    # watch:     confidence ≥ 55 かつ gap ≥ 7   (B ランク, decision=skip)
    # skip:      それ未満                         (C ランク)
    # ==============================================================

    Returns:
        {
            "pick":       "1-2-4",
            "confidence": 65.0,
            "decision":   "buy" | "candidate" | "skip",
            "is_watch":   False,   # True = watch 候補 (decision=skip のまま)
            "rank":       "S" | "A" | "B" | "C",
            "reason":     [...],   # "[watch]" が含まれる場合は watch 候補
            "gap":        12.5,
        }
    """
    gap = gap_between_3rd_4th(scores)
    pick = make_pick(scores)
    reasons: list[str] = []

    # 荒れ条件チェック
    wind_rough      = condition.wind_speed  >= 5.0
    wave_rough      = condition.wave_height >= 15.0
    approach_unstable = not condition.approach_stable

    if wind_rough:
        reasons.append(f"風速 {condition.wind_speed}m/s — 荒れ要因")
    if wave_rough:
        reasons.append(f"波高 {condition.wave_height}cm — 荒れ要因")
    if approach_unstable:
        reasons.append("進入が乱れる可能性あり")

    avg_top3   = sum(s.total for s in scores[:3]) / 3 if scores else 0.0
    confidence = min(100.0, avg_top3 * (1 + gap / 200))
    forced_skip = wind_rough or wave_rough or approach_unstable

    is_watch = False

    if not forced_skip and confidence >= 70 and gap >= 10:
        decision = "buy"
        rank = "S"
        reasons.append(f"上位3艇のスコア差が明確 (gap={gap:.1f})")

    elif not forced_skip and confidence >= 62 and gap >= 7:
        decision = "candidate"
        rank = "A"
        reasons.append(f"上位3艇が安定 (gap={gap:.1f})")

    elif not forced_skip and confidence >= 55 and gap >= 7:
        # watch: 実投票対象外、検証候補
        decision  = "skip"
        rank      = "B"
        is_watch  = True
        reasons.append(f"[watch] 検証候補 — gap={gap:.1f} / conf={round(confidence, 1)}")

    else:
        decision = "skip"
        rank = "C"
        if forced_skip:
            reasons.append(f"荒れ条件のため見送り (gap={gap:.1f})")
        else:
            reasons.append(f"上位候補が絞れていない (gap={gap:.1f})")

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
