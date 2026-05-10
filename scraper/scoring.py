"""
3着以内スコア計算モジュール
朝スコア(70点満点) + 直前スコア(30点満点) = 総合スコア(100点満点)

【スコア構成】
朝スコア (70点上限):
  選手力  20点  = 級別10 + 全国勝率5 + ボート2連対率5
  モーター 15点  ← 艦隊平均との相対評価（全艇平均=7.5点）
  枠      10点
  スタート 10点
  当地相性 10点
  合計最大  65点 (安定した選手ほど満点に近づく)

直前スコア (30点上限, 理論最大33点をcap):
  展示タイム  13点  ← 艦隊平均との相対評価（スケール拡大 25→33）
  展示ST       5点  ← 艦隊平均との相対評価
  チルト補正   4点  ← チルト角から周回安定度を推定
  進入補正     8点  ← 実コース位置ベース（コース1=6pt基準）
  風波補正     3点

修正履歴:
  v1: local_win_rate の二重計上を解消
  v2: 展示タイム/ST を絶対評価から艦隊平均との相対評価に変更
  v3: チルト角を scoring に反映
  v4: 進入コース補正を方向性考慮型に変更
  v5: モータースコアを艦隊相対評価に変更
      展示タイム識別力を強化 (13点・スケール33)
      進入コースを実コース位置ベースに刷新 (最大8点)
      信頼度のgap重みを強化 (/200→/150)
      1号艇コース3以降進入の信頼度ペナルティを追加
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
    turn_stability: Optional[float] = None    # 周回展示の安定度 (未使用 → tilt で代替)
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


def _motor_score(rate: float, race_avg: float = 40.0) -> float:
    """
    モーター2連対率を0〜15点にマッピング（艦隊平均との相対評価）

    艦隊平均 = 7.5点 (中央値)。
    平均より5%高い → +1.5点 / 平均より5%低い → -1.5点。
    これにより全艇が同レベルの良モーターでも相対差を正しく反映する。
    """
    return min(15.0, max(0.0, 7.5 + (rate - race_avg) * 0.3))


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


def morning_score(entry: EntryData, race_avg_motor: Optional[float] = None) -> float:
    """
    朝スコア計算 (最大65点程度 / cap 70点)

    Args:
        race_avg_motor: 艦隊全艇のモーター2連対率平均。
                        指定時は相対評価、None の場合は固定ベースライン(40%)評価。
    """
    # 選手力 (20点)
    player = min(20.0,
        _class_score(entry.racer_class)               # 10
        + _win_rate_score(entry.national_win_rate)    # 5
        + _boat_rate_score(entry.boat_rate)           # 5
    )

    # モーター (15点) — 艦隊平均との相対評価
    motor = _motor_score(entry.motor_rate, race_avg_motor if race_avg_motor is not None else 40.0)

    # 枠・コース (10点)
    lane = _lane_score(entry.lane)

    # スタート力 (10点)
    st = _st_score(entry.avg_st, entry.f_count, entry.l_count)

    # 当地相性 (10点)
    local = _local_rate_score(entry.local_win_rate)

    return min(70.0, player + motor + lane + st + local)


def pre_race_score(
    entry: EntryData,
    condition: RaceCondition,
    fleet_avg_ex_time: Optional[float] = None,
    fleet_avg_ex_st: Optional[float] = None,
) -> float:
    """
    直前スコア計算 (理論最大33点 → cap 30点)

    【配点】
    展示タイム 13点 (スケール33、艦隊相対評価 — 最も信頼性の高い指標)
    展示ST      5点 (艦隊相対評価)
    チルト補正  4点
    進入補正    8点 (実コース位置ベース — コース1=6点基準)
    風波補正    3点

    【変更点 v5】
    - 展示タイム: 10点→13点、スケール25→33（識別力強化）
    - 進入コース: 方向性ベース→実コース位置ベースに刷新
      「コース1進入=6pt基準、コース6=0pt。インへの移動ボーナス+0.25/枠」
    - チルト: 5点→4点（展示タイムへの重み移動）
    - 風波: 5点→3点（個体差より環境差に過ぎないため軽量化）
    """
    if entry.exhibition_time is None:
        return 0.0

    # ── 展示タイム (13点) ── 艦隊相対評価・識別力強化 ────────────────────────
    if fleet_avg_ex_time is not None:
        # スケール33: 0.03s 速い → +1.0点（旧: 0.04s → +1.0点）
        # 中間(艦隊平均) → 6.5点
        ex_time_score = max(0.0, min(13.0,
            6.5 + (fleet_avg_ex_time - entry.exhibition_time) * 33.0
        ))
    else:
        # フォールバック: 6.90s 基準の絶対評価
        ex_time_score = max(0.0, min(13.0,
            (6.90 - entry.exhibition_time) * 33.0
        ))

    # ── 展示ST (5点) ── 艦隊相対評価 ─────────────────────────────────────────
    if entry.exhibition_st is not None:
        if fleet_avg_ex_st is not None:
            ex_st_score = max(0.0, min(5.0,
                2.5 + (fleet_avg_ex_st - entry.exhibition_st) * 50.0
            ))
        else:
            ex_st_score = max(0.0, min(5.0,
                5.0 - (entry.exhibition_st - 0.10) * 50.0
            ))
    else:
        ex_st_score = 2.5  # データなし: 中間値

    # ── チルト補正 (4点) ── 展示データあり時のみ ─────────────────────────────
    if entry.tilt is not None:
        if 0.5 <= entry.tilt <= 2.0:
            turn_score = 4.0   # 適度な攻めセット: 最良
        elif entry.tilt > 2.0:
            turn_score = 2.8   # 攻めすぎ: ターンリスク
        elif entry.tilt < -1.0:
            turn_score = 2.4   # 強守り: 伸び鈍い
        else:
            turn_score = 3.6   # neutral 〜 軽い攻め
    else:
        turn_score = (entry.turn_stability or 0.5) * 4.0

    # ── 進入コース補正 (最大8点) ── 実コース位置ベース ───────────────────────
    # 設計思想:
    #   コース有利度 = 実際の進入コース番号で決まる（コース1=6pt、コース6=0pt）
    #   「インに動いた」ほど追加ボーナス(+0.25/枠差)
    #   「アウトに動いた」場合は有利度のみ（移動ボーナスなし）
    #
    # 例:
    #   1号艇コース1進入: 6.0点           (インキープ)
    #   6号艇コース1進入: 6.0+1.25=7.25点 (大幅インへ移動)
    #   1号艇コース3進入: 3.6-0.5=3.1点   (大幅アウトに押し出し)
    #   1号艇コース4進入: 2.4-0.75=1.65点 (深刻なアウト進入)
    if entry.approach_lane is not None:
        effective_course_score = max(0.0, 6.0 - (entry.approach_lane - 1) * 1.2)
        movement = (entry.lane - entry.approach_lane) * 0.25  # 正=インへ移動
        approach_score = min(8.0, max(0.0, effective_course_score + movement))
        if not condition.approach_stable:
            approach_score = max(0.0, approach_score - 1.5)
    else:
        # コース情報なし: 枠番から推定
        approach_score = 4.0 if condition.approach_stable else 2.0

    # ── 風・波補正 (3点) ─────────────────────────────────────────────────────
    wind_penalty = min(2.0, condition.wind_speed * 0.3)
    wave_penalty = min(1.0, condition.wave_height * 0.01)
    condition_score = max(0.0, 3.0 - wind_penalty - wave_penalty)

    total = ex_time_score + ex_st_score + turn_score + approach_score + condition_score
    return min(30.0, total)


def score_entries(entries: list[EntryData], condition: RaceCondition) -> list[EntryScore]:
    """
    全艇のスコアを計算してソート済みリストを返す。

    展示データが揃っている場合は艦隊平均を計算して相対評価に使用する。
    モーター2連対率も艦隊平均を計算して相対評価する。
    """
    # 艦隊平均を計算
    ex_times    = [e.exhibition_time for e in entries if e.exhibition_time is not None]
    ex_sts      = [e.exhibition_st   for e in entries if e.exhibition_st   is not None]
    motor_rates = [e.motor_rate      for e in entries if e.motor_rate      > 0]

    fleet_avg_ex_time  = sum(ex_times)    / len(ex_times)    if ex_times    else None
    fleet_avg_ex_st    = sum(ex_sts)      / len(ex_sts)      if ex_sts      else None
    fleet_avg_motor    = sum(motor_rates) / len(motor_rates) if motor_rates else None

    scores = []
    for e in entries:
        ms = morning_score(e, race_avg_motor=fleet_avg_motor)
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
    lane1_approach: Optional[int] = None,
) -> dict:
    """
    買い / 候補 / ウォッチ / 見送り 判定

    decision は "buy" | "candidate" | "skip" の3値。
    watch は decision="skip" の一部で、reason に "[watch]" マーカーを付与。

    # ===== 閾値（2026-05-10 / 3日間420件バックテスト調整済み） =====
    # confidence = avg_top3 × (1 + gap/150) × lane1_mul
    #
    # バックテスト結果（v5モデル・展示データあり100%）:
    #   conf≥70: 98件 / 的中率32.7% / 平均払戻¥281 / ROI -8.2% ← 最良
    #   conf≥67: 185件 / 的中率26.5% / 平均払戻¥303 / ROI -19.8%
    #   BUY判定: 22件 / 的中率18.2% / 平均払戻¥222 / ROI -59.5%（低閾値の罠）
    #   SKIP:   354件 / 的中率22.9% / 平均払戻¥397 / ROI -9.2%（SPIPの方が配当高い）
    #
    # 根本課題: 高confidence = 人気組み合わせ = 低配当。
    # 対策: 閾値引き上げ + ペイロードフィルタ強化（live odds での選別が核心）
    #
    # buy:       confidence ≥ 70 かつ gap ≥ 10  (S ランク) ← 旧67 → 70
    # candidate: confidence ≥ 62 かつ gap ≥ 7   (A ランク) ← 旧59 → 62
    # watch:     confidence ≥ 55 かつ gap ≥ 7   (B ランク, decision=skip)
    # skip:      それ未満                         (C ランク)
    # ──────────────────────────────────────────────────────────
    # [1号艇コース補正 v5]
    #   lane1_approach が指定され、かつ3コース以降に進入している場合:
    #   → 信頼度に 0.85 掛け（旧: 4位以下と同等の0.90）
    # ──────────────────────────────────────────────────────────
    # [払戻フィルター] ← 基準を強化（低配当の罠を回避）
    #   buy   < ¥500 → candidate に降格  (旧: ¥400。BUY平均¥222→損益分岐 100/0.327=¥306)
    #   cand  < ¥300 → skip に降格       (旧: ¥250)
    # ===========================================================

    Args:
        scores:         EntryScore リスト（スコア降順）
        condition:      レース条件（風速・波高・進入）
        pick_payout:    三連複オッズの払戻額(¥/¥100bet)。None=フィルタなし。
        lane1_approach: 1号艇の実際の進入コース番号。None=不明。

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
    gap  = gap_between_3rd_4th(scores)
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
    confidence = min(100.0, avg_top3 * (1 + gap / 150))  # gap重み強化

    # ── 1号艇インコース補正 ────────────────────────────────────────────────
    lane1_rank = next((i for i, s in enumerate(scores) if s.lane == 1), -1)

    # 1号艇の実際の進入コースを確認（lane1_approach が指定された場合）
    lane1_out_of_inside = (lane1_approach is not None and lane1_approach >= 3)

    if lane1_rank == 0:
        if lane1_out_of_inside:
            # 1号艇スコア1位だが実際はコース3以降から発走 → インアドバンテージ消失
            lane1_mul = 0.85
            reasons.append(f"⚠️ 1号艇コース{lane1_approach}進入 — インアドバンテージ消失・波乱リスク")
        else:
            lane1_mul = 1.08   # 1号艇1位 + コース1: 逃げ期待大
    elif lane1_rank == 1:
        lane1_mul = 1.04       # 2位: 差し展開
    elif lane1_rank == 2:
        lane1_mul = 1.00       # 3位: pick内ギリギリ
    else:
        lane1_mul = 0.90       # 4位以下(pick外): 大波乱リスク

    confidence = min(100.0, confidence * lane1_mul)

    forced_skip = wind_rough or wave_rough or approach_unstable
    is_watch    = False

    lane1_label = ["1位", "2位", "3位", "4位以下"][min(lane1_rank, 3)] if lane1_rank >= 0 else "不明"
    approach_note = f" (コース{lane1_approach}進入)" if lane1_approach else ""

    if not forced_skip and confidence >= 70 and gap >= 10:
        decision = "buy"
        rank = "S"
        reasons.append(f"上位3艇のスコア差が明確 (gap={gap:.1f} / 1号艇{lane1_label}{approach_note})")

    elif not forced_skip and confidence >= 62 and gap >= 7:
        decision = "candidate"
        rank = "A"
        reasons.append(f"上位3艇が安定 (gap={gap:.1f} / 1号艇{lane1_label}{approach_note})")

    elif not forced_skip and confidence >= 55 and gap >= 7:
        decision  = "skip"
        rank      = "B"
        is_watch  = True
        reasons.append(
            f"[watch] 検証候補 — gap={gap:.1f} / conf={round(confidence, 1)} "
            f"/ 1号艇{lane1_label}{approach_note}"
        )

    else:
        decision = "skip"
        rank = "C"
        if forced_skip:
            reasons.append(f"荒れ条件のため見送り (gap={gap:.1f})")
        else:
            reasons.append(f"上位候補が絞れていない (gap={gap:.1f} / 1号艇{lane1_label}{approach_note})")

    # ── 払戻フィルター ────────────────────────────────────────────────────────
    if pick_payout is not None and pick_payout > 0:
        reasons.append(f"三連複オッズ: ¥{pick_payout}/¥100")
        if decision == "buy" and pick_payout < 500:
            decision = "candidate"
            rank = "A"
            reasons.append(f"⚠️ 払戻¥{pick_payout} < ¥500 → candidate に降格")
        elif decision == "candidate" and pick_payout < 300:
            decision = "skip"
            rank = "C"
            reasons.append(f"⚠️ 払戻¥{pick_payout} < ¥300 → skip に降格")

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
