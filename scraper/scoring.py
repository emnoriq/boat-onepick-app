"""
3着以内スコア計算モジュール
朝スコア(70点満点) + 直前スコア(30点満点) = 総合スコア(100点満点)

【スコア構成】
朝スコア (70点上限):
  選手力  20点  = 級別10 + 全国3連対率7 + ボート2連対率3
  モーター 15点  ← 艦隊平均との相対評価（全艇平均=7.5点）
  枠      8点   ← 枠有利スコア
  コース適性 7点 ← コース別1着率（三連複ベット向け強化）
  スタート 10点
  当地相性 10点  ← 当地3連対率（三連複ベット直結指標）
  合計最大  70点

直前スコア (30点上限, 理論最大33点をcap):
  展示タイム  13点  ← 艦隊平均との相対評価（スケール拡大 25→33）
  展示ST       5点  ← 艦隊平均との相対評価
  チルト補正   4点  ← チルト角から周回安定度を推定
  進入補正     8点  ← 実コース位置ベース（コース1=6pt基準）+コース別実績
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
  v6: 期待値(EV)計算を追加
      全20組み合わせのEVを算出し最大EV組み合わせを推薦
      「強い艇を当てる」→「市場が過小評価する組み合わせを見つける」に転換
  v7: 選手詳細データ統合
      全国3連対率・当地3連対率を三連複ベット向け指標として採用
      コース別1着率（c1_win_rate〜c6_win_rate）をスコアに反映
      朝スコア: 枠10→8pt / コース適性7pt新設 / player内訳変更
  v8: BUY条件厳格化
      1号艇スコア1位時のpick強制1号艇包含 (実績: 1号艇ナシ2% vs 含む26%的中)
      EV閾値 0.15→0.25、conf閾値 65→68
      1号艇がpickに含まれない場合はBUY不可(CANDIDATE止まり)
"""

import math
from dataclasses import dataclass
from itertools import combinations as _combinations
from typing import Optional


@dataclass
class EntryData:
    lane: int
    racer_name: str
    racer_class: str = ""            # A1 / A2 / B1 / B2
    racer_no: str = ""               # 登録番号
    national_win_rate: float = 0.0   # 全国勝率
    national_top2_rate: float = 0.0  # 全国2連対率 (%)
    national_top3_rate: float = 0.0  # 全国3連対率 (%) ← 三連複ベット向け主要指標
    local_win_rate: float = 0.0      # 当地勝率
    local_top2_rate: float = 0.0     # 当地2連対率 (%)
    local_top3_rate: float = 0.0     # 当地3連対率 (%) ← 三連複ベット向け主要指標
    motor_rate: float = 0.0          # モーター2連対率
    boat_rate: float = 0.0           # ボート2連対率
    avg_st: float = 0.15             # 平均スタートタイム
    f_count: int = 0                 # F(フライング)回数
    l_count: int = 0                 # L(出遅れ)回数
    # コース別1着率 (%) — fetch_racer_stats.py で取得
    c1_win_rate: float = 0.0   # コース1からの1着率
    c2_win_rate: float = 0.0   # コース2からの1着率
    c3_win_rate: float = 0.0   # コース3からの1着率
    c4_win_rate: float = 0.0   # コース4からの1着率
    c5_win_rate: float = 0.0   # コース5からの1着率
    c6_win_rate: float = 0.0   # コース6からの1着率
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


def _national_top3_score(rate: float) -> float:
    """
    全国3連対率を0〜7点にマッピング（三連複ベット向け）

    3連対率 (%) の典型値: B2=30%, B1=40%, A2=50%, A1=60%
    50% → 5点、65% → 7点、35% → 0点
    """
    return min(7.0, max(0.0, (rate - 35.0) * 0.467))


def _local_top3_score(rate: float) -> float:
    """
    当地3連対率を0〜10点にマッピング（三連複ベット直結）

    当地は場になれているほど高い。30%未満=苦手場、55%以上=得意場
    55% → 10点、30% → 0点
    """
    return min(10.0, max(0.0, (rate - 30.0) * 0.4))


def _course_affinity_score(entry: "EntryData", lane: int) -> float:
    """
    コース別1着率スコア (0〜7点)

    選手がそのコースから何%勝つかを評価。
    平均的な勝率(16.7%=1/6) を基準に相対評価。
    40% → 7点, 25% → 4点, 16.7% → 1.4点, 5% → 0点

    lane: 出走枠番 (approach_lane が分かるまでは枠番で代用)
    """
    rates = [entry.c1_win_rate, entry.c2_win_rate, entry.c3_win_rate,
             entry.c4_win_rate, entry.c5_win_rate, entry.c6_win_rate]
    # コース別データが全てゼロなら中間値を返す
    if all(r == 0.0 for r in rates):
        return 3.5  # データなし: 中間値
    idx = max(0, min(5, lane - 1))
    rate = rates[idx]
    return min(7.0, max(0.0, rate * 0.175))


def _win_rate_score(rate: float) -> float:
    """全国勝率を0〜5点にマッピング（後方互換・直接は使用しない）"""
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
    1号艇: 8点、以降1.4点ずつ減少 (コース適性7点と合算で最大15点)
    """
    return max(0.0, 8.0 - (lane - 1) * 1.4)


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
    朝スコア計算 (最大70点cap)

    Args:
        race_avg_motor: 艦隊全艇のモーター2連対率平均。
                        指定時は相対評価、None の場合は固定ベースライン(40%)評価。

    【v7 変更点】
    - 選手力: 全国3連対率(7pt)採用 → 三連複ベットに直結した指標
    - 枠: 10pt→8pt (コース適性と合算)
    - コース適性: 7pt新設 → コース別1着率で個人の得手不得手を反映
    - 当地相性: 当地3連対率(10pt) → 三連複ベット直結
    """
    # 選手力 (20点): 級別(10) + 全国3連対率(7) + ボート2連対率(3)
    player = min(20.0,
        _class_score(entry.racer_class)                   # 10
        + _national_top3_score(entry.national_top3_rate)  # 0-7
        + min(3.0, _boat_rate_score(entry.boat_rate))     # 0-3
    )

    # モーター (15点) — 艦隊平均との相対評価
    motor = _motor_score(entry.motor_rate, race_avg_motor if race_avg_motor is not None else 40.0)

    # 枠スコア (8点)
    lane = _lane_score(entry.lane)

    # コース適性 (7点) — コース別1着率（データなし時は中間値3.5）
    course = _course_affinity_score(entry, entry.lane)

    # スタート力 (10点)
    st = _st_score(entry.avg_st, entry.f_count, entry.l_count)

    # 当地相性 (10点) — 当地3連対率（三連複ベット直結）
    local = _local_top3_score(entry.local_top3_rate) if entry.local_top3_rate > 0 \
            else _local_rate_score(entry.local_win_rate)  # フォールバック

    return min(70.0, player + motor + lane + course + st + local)


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
        # コース別1着率ボーナス: 実際の進入コースでの個人実績を反映 (±1.5点)
        course_bonus = _course_affinity_score(entry, entry.approach_lane)
        # course_affinity(0-7pt) を ±1.5pt に変換 (中間3.5→0補正)
        approach_score = min(8.0, max(0.0, approach_score + (course_bonus - 3.5) * 0.3))
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


def calculate_kelly(ev: float, payout: int, fraction: float = 0.25) -> float:
    """
    Kelly基準の最適賭け率を計算する（1/4 Kelly デフォルト）。

    Full Kelly = EV / (net_odds) = EV / (payout/100 - 1)
    1/4 Kelly  = Full Kelly × 0.25  ← 実用上の安全マージン

    Args:
        ev:       期待値 (例: 0.20 = +20%)
        payout:   払戻額 (例: 300 = ¥300/¥100賭け)
        fraction: Kelly分数 (デフォルト 0.25 = 1/4 Kelly)

    Returns:
        推奨賭け率 (0.0〜1.0) = バンクロールの何%
        EV ≤ 0 または payout ≤ 100 の場合は 0.0 を返す。

    使用例:
        kelly = calculate_kelly(0.20, 300)  # → 0.025 (2.5%)
        推奨額 = bankroll × kelly           # ¥10,000 × 0.025 = ¥250
    """
    if ev <= 0 or payout <= 100:
        return 0.0
    b = payout / 100.0 - 1.0  # net odds (¥300 → 2.0)
    if b <= 0:
        return 0.0
    full_kelly = min(1.0, max(0.0, ev / b))
    return round(full_kelly * fraction, 4)


def scores_to_combo_probs(
    scores: list[EntryScore],
    temperature: float = 12.0,
) -> dict[str, float]:
    """
    全三連複組み合わせ（最大20通り）の推定的中確率を返す。

    Softmax変換でボートのスコアを相対強度に変換し、
    3艇組み合わせの確率を積で近似（正規化済み）。

    Args:
        temperature: 大きいほど確率が均等に分散する（デフォルト12）
                     小さくすると上位艇への集中度が増す
    Returns:
        {"1-2-3": 0.312, "1-2-4": 0.087, ...}  合計=1.0
    """
    exps = {s.lane: math.exp(s.total / temperature) for s in scores}
    total_exp = sum(exps.values())
    strength = {lane: v / total_exp for lane, v in exps.items()}

    lanes = sorted(s.lane for s in scores)
    combo_probs: dict[str, float] = {}
    for combo in _combinations(lanes, 3):
        key = "-".join(str(l) for l in combo)
        combo_probs[key] = strength[combo[0]] * strength[combo[1]] * strength[combo[2]]

    total_p = sum(combo_probs.values())
    return {k: v / total_p for k, v in combo_probs.items()} if total_p > 0 else combo_probs


def calculate_combo_ev(
    combo_probs: dict[str, float],
    odds: dict[str, int],
) -> dict[str, float]:
    """
    各三連複組み合わせの期待値(EV)を計算する。

    EV = P_model × (payout / 100) - 1.0
      EV > 0   : 期待値プラス ← 買う価値がある
      EV = 0   : 損益ゼロ（fair な賭け）
      EV ≈ -0.25: 控除率のみ（完全ランダム時の期待値）

    高スコア上位艇の組み合わせでも人気が集中すれば低配当になりEVがマイナスになる。
    逆に「そこそこ強いが過小評価されている」組み合わせはEVがプラスになる。

    Args:
        combo_probs: scores_to_combo_probs() の出力
        odds:        fetch_trifecta_box_odds() の出力 (key="1-2-3", value=¥払戻)
    Returns:
        {"1-2-3": -0.15, "1-3-5": 0.08, ...}
    """
    ev: dict[str, float] = {}
    for combo, prob in combo_probs.items():
        if combo in odds:
            ev[combo] = round(prob * odds[combo] / 100.0 - 1.0, 4)
    return ev


def decide(
    scores: list[EntryScore],
    condition: RaceCondition,
    pick_payout: Optional[int] = None,      # 後方互換（all_odds がない場合のフィルタ用）
    lane1_approach: Optional[int] = None,
    all_odds: Optional[dict[str, int]] = None,  # 全20組み合わせのオッズ（EVモード）
) -> dict:
    """
    買い / 候補 / ウォッチ / 見送り 判定

    decision は "buy" | "candidate" | "skip" の3値。
    watch は decision="skip" の一部で、reason に "[watch]" マーカーを付与。

    # ===== 判定ロジック =====
    #
    # [EVモード] all_odds が提供された場合（pre_race_scan）:
    #   全20組み合わせのEVを計算し、最大EV組み合わせを推薦する。
    #   EV = P_model × (payout / 100) - 1.0
    #   EV > 0.15 かつ confidence ≥ 65 → buy
    #   EV > 0.00                      → candidate
    #   EV > -0.05                     → watch
    #   それ以下                        → skip
    #
    # [スコアモード] all_odds がない場合（morning_scan 等）:
    #   従来の confidence + gap ベースの判定
    #   buy:       confidence ≥ 70 かつ gap ≥ 10
    #   candidate: confidence ≥ 62 かつ gap ≥ 7
    #   watch:     confidence ≥ 55 かつ gap ≥ 7
    #   skip:      それ未満
    #
    # [共通] 1号艇コース補正:
    #   lane1_approach ≥ 3 → confidence × 0.85
    #
    # [後方互換] pick_payout フィルター（all_odds なし時のみ有効）:
    #   buy  < ¥500 → candidate, candidate < ¥300 → skip
    # ======================================================

    Args:
        scores:         EntryScore リスト（スコア降順）
        condition:      レース条件（風速・波高・進入）
        pick_payout:    三連複オッズの払戻額(¥/¥100bet)。all_odds がない時のフォールバック。
        lane1_approach: 1号艇の実際の進入コース番号。None=不明。
        all_odds:       全20組み合わせのオッズ dict。提供時は EV モードで動作。

    Returns:
        {
            "pick":       "1-2-4",          # EV最大の組み合わせ（EVモード時）
            "confidence": 65.0,
            "decision":   "buy" | "candidate" | "skip",
            "is_watch":   False,
            "rank":       "S" | "A" | "B" | "C",
            "reason":     [...],
            "gap":        12.5,
            "best_ev":    0.08,             # EV最大値（EVモード時のみ）
            "ev_pick":    "1-2-4",          # EV最大の組み合わせ
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

    # ── EV モード（全オッズが提供された場合） ────────────────────────────────
    best_ev: Optional[float] = None
    ev_pick: Optional[str]   = None
    kelly_fraction: Optional[float] = None

    if all_odds and not forced_skip:
        combo_probs = scores_to_combo_probs(scores)
        ev_map      = calculate_combo_ev(combo_probs, all_odds)

        if ev_map:
            ev_pick  = max(ev_map, key=lambda k: ev_map[k])
            best_ev  = ev_map[ev_pick]

            # ── 1号艇スコア1位の場合は1号艇を必ずpickに含める ────────────────
            # 実績データより: 1号艇ナシpickは92%のケースで1号艇が3着内に来ており
            # 的中率3% (ほぼランダム)。1号艇含むpickは24%的中。
            # 1号艇がスコア最上位なのにEVモードが1号艇を除外するのは
            # 「オッズが低い=人気=EV低い」と判断するためだが、
            # 実際には1号艇が最も3着内に来やすいため修正が必要。
            top_lane = scores[0].lane if scores else None
            if top_lane == 1 and ev_pick and '1' not in ev_pick.split('-'):
                # 1号艇を含む組み合わせの中から最大EVを選び直す
                ev_with_top = {k: v for k, v in ev_map.items() if '1' in k.split('-')}
                if ev_with_top:
                    alt_pick = max(ev_with_top, key=lambda k: ev_with_top[k])
                    alt_ev   = ev_with_top[alt_pick]
                    reasons.append(
                        f"[1号艇補正] スコア1位(1号艇)をpickに強制追加 "
                        f"(元EV={best_ev:+.2f}→{alt_ev:+.2f} / {ev_pick}→{alt_pick})"
                    )
                    ev_pick = alt_pick
                    best_ev = alt_ev

            # EVモードでは pick を最大EV組み合わせに差し替え
            pick = ev_pick

            # EV ベースの判定（confidence もあわせて参照）
            # BUY条件: EV>0.25 かつ conf>=68 かつ 1号艇がpickに含まれること
            # 実績: 1号艇ナシpickは2%的中、1号艇含むpickは26%的中
            has_lane1_in_pick = ev_pick and '1' in ev_pick.split('-')
            if best_ev > 0.25 and confidence >= 68 and has_lane1_in_pick:
                decision = "buy"
                rank     = "S"
                reasons.append(
                    f"EV={best_ev:+.2f} (期待値+{best_ev*100:.0f}%) / conf={round(confidence,1)} "
                    f"/ gap={gap:.1f} — 市場が過小評価している組み合わせ"
                )
            elif best_ev > 0.15 and confidence >= 65:
                # EV プラスだが1号艇なし or 閾値未満 → CANDIDATE止まり
                decision = "candidate"
                rank     = "A"
                if not has_lane1_in_pick:
                    reasons.append(
                        f"EV={best_ev:+.2f} / conf={round(confidence,1)} "
                        f"/ gap={gap:.1f} — 1号艇未包含のためcandidate止まり"
                    )
                else:
                    reasons.append(
                        f"EV={best_ev:+.2f} (EV or conf 閾値未達) / conf={round(confidence,1)} "
                        f"/ gap={gap:.1f}"
                    )
            elif best_ev > 0.0:
                decision = "candidate"
                rank     = "A"
                reasons.append(
                    f"EV={best_ev:+.2f} (期待値プラス) / conf={round(confidence,1)} "
                    f"/ gap={gap:.1f}"
                )
            elif best_ev > -0.05:
                decision = "skip"
                rank     = "B"
                is_watch = True
                reasons.append(
                    f"[watch] EV={best_ev:+.2f} / conf={round(confidence,1)} / gap={gap:.1f}"
                )
            else:
                decision = "skip"
                rank     = "C"
                reasons.append(
                    f"EV={best_ev:+.2f} — 全組み合わせで期待値マイナス (gap={gap:.1f})"
                )

            # EVトップ3を reason に記録（透明性のため）
            top3_ev = sorted(ev_map.items(), key=lambda x: x[1], reverse=True)[:3]
            ev_summary = " / ".join(f"{c}:EV{v:+.2f}" for c, v in top3_ev)
            reasons.append(f"EV上位3: {ev_summary}")

            # Kelly基準: EV > 0 のときのみ計算
            if best_ev is not None and best_ev > 0 and ev_pick and ev_pick in all_odds:
                kelly_fraction = calculate_kelly(best_ev, all_odds[ev_pick])

    else:
        # ── スコアモード（朝スキャン・オッズ未取得時） ────────────────────────
        # 払戻フィルター（後方互換）
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
        "best_ev":       round(best_ev, 4) if best_ev is not None else None,
        "ev_pick":       ev_pick,
        "kelly_fraction": kelly_fraction,  # 推奨賭け率 (1/4 Kelly)
    }
