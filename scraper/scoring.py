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
  v9: 場別補正 + 1号艇クラス補正
      低パフォーマンス場(びわこ10%/大村12%/津15%/戸田15%)の信頼度ペナルティ追加
      1号艇クラスによる信頼度補正: A1×1.05 / B1×0.88 / B2×0.82
      高精度場(下関32%/福岡29%/常滑28%) BUY条件をより通しやすく
"""

import json
import math
import os
from dataclasses import dataclass
from itertools import combinations as _combinations
from typing import Optional

# ── 動的重み・統計ファイルのロード ────────────────────────────────────────────
_SCORING_DIR = os.path.dirname(__file__)


def _load_json(filename: str, default: dict) -> dict:
    """JSON ファイルを読み込む。存在しなければ default を返す。"""
    path = os.path.join(_SCORING_DIR, filename)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


# 重み乗数 (weights.json が weekly_optimize.yml によって自動更新される)
_WEIGHTS_DEFAULT = {
    "w_player": 1.0, "w_motor": 1.0, "w_lane": 1.0,
    "w_course": 1.0, "w_st": 1.0,   "w_local": 1.0,
}
_WEIGHTS = _load_json("weights.json", _WEIGHTS_DEFAULT)

# 場別・クラス別統計 (stadium_stats.json が update_stats.py によって自動更新される)
_STATS_DEFAULT: dict = {"stadiums": {}, "lane1_class": {}}
_STATS = _load_json("stadium_stats.json", _STATS_DEFAULT)

# BUY判定閾値 (thresholds.json が tune_thresholds.py によって自動更新される)
_THRESHOLDS_DEFAULT: dict = {
    "ev_buy":          0.25,   # EVモード BUY 閾値 (EV > X)
    "ev_buy_max":      0.50,   # EVモード BUY 上限 (EV > X は逆選択リスク → CANDIDATE)
                               # 実績: EV>0.5 → 的中率5.2%, EV 0.25-0.5 → 的中率30%
    "conf_buy":        68.0,   # EVモード BUY confidence 閾値
    "ev_cand":         0.15,   # EVモード CANDIDATE 閾値
    "conf_cand":       65.0,   # EVモード CANDIDATE confidence 閾値
    "score_buy_conf":  70.0,   # スコアモード BUY confidence 閾値
    "score_buy_gap":   10.0,   # スコアモード BUY gap 閾値
    "score_cand_conf": 62.0,   # スコアモード CANDIDATE confidence 閾値
    "score_cand_gap":   7.0,   # スコアモード CANDIDATE gap 閾値
}
_THRESHOLDS = _load_json("thresholds.json", _THRESHOLDS_DEFAULT)


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
    wind_speed: float = 0.0       # m/s
    wave_height: float = 0.0      # cm
    approach_stable: bool = True  # 進入が枠なり安定かどうか
    weather: str = ""             # ⑩ 天候テキスト（晴/曇/雨）— 保存・ログ用、将来的にML特徴量化


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
    モーター2連対率を0〜8.4点にマッピング（艦隊平均との相対評価）

    重み最適化結果 (2199レース): モータースコア×0.56が最適
    → 実効最大値 15pt → 8.4pt に削減
    理由: モーター率は整備・運などランダム要因が大きく、過大評価すると
          選手力・枠の優位性を打ち消してしまう。

    艦隊平均 = 4.2点 (中央値)。
    平均より5%高い → +0.84点 / 平均より5%低い → -0.84点。
    """
    return min(8.4, max(0.0, 4.2 + (rate - race_avg) * 0.168))


def _boat_rate_score(rate: float) -> float:
    """ボート2連対率を0〜5点にマッピング"""
    return min(5.0, max(0.0, (rate - 30.0) * 0.1))


def _lane_score(lane: int) -> float:
    """
    枠有利不利 (インほど有利)
    実績分析 (2199レース) に基づく3着内率:
      1号艇82.1%, 2号艇57.0%, 3号艇52.7%, 4号艇45.7%, 5号艇35.3%, 6号艇27.3%
    重み最適化結果: 枠スコア×1.35が最適 → 1号艇 10.8pt (旧8pt)
    """
    return max(0.0, 10.8 - (lane - 1) * 1.9)


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

    # 動的重み乗数を適用 (weights.json が weekly_optimize.yml によって更新される)
    w = _WEIGHTS
    return min(70.0,
        w.get("w_player", 1.0) * player +
        w.get("w_motor",  1.0) * motor  +
        w.get("w_lane",   1.0) * lane   +
        w.get("w_course", 1.0) * course +
        w.get("w_st",     1.0) * st     +
        w.get("w_local",  1.0) * local
    )


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


def score_entries_ml(
    entries: list[EntryData],
    condition: RaceCondition,
    blend_alpha: float = 0.5,
) -> list[EntryScore]:
    """
    ML モデル (GradientBoosting) + 線形スコアのブレンド版 score_entries()。

    blend_alpha: ML の重み (0.0=線形のみ, 1.0=MLのみ, 0.5=50/50ブレンド)

    model_gbm.pkl が存在しない場合は通常の score_entries() にフォールバック。
    """
    try:
        import pickle
        import numpy as np
        from scoring_ml import predict_scores, load_model
        model = load_model()
        if model is None:
            return score_entries(entries, condition)

        # ML スコア計算
        entries_dict = []
        for e in entries:
            entries_dict.append({
                "lane":                e.lane,
                "racer_class":         e.racer_class,
                "national_top3_rate":  e.national_top3_rate,
                "local_top3_rate":     e.local_top3_rate,
                "local_win_rate":      e.local_win_rate,
                "motor_rate":          e.motor_rate,
                "boat_rate":           e.boat_rate,
                "avg_st":              e.avg_st,
                "f_count":             e.f_count,
                "l_count":             e.l_count,
                "c1_win_rate":         e.c1_win_rate,
                "c2_win_rate":         e.c2_win_rate,
                "c3_win_rate":         e.c3_win_rate,
                "c4_win_rate":         e.c4_win_rate,
                "c5_win_rate":         e.c5_win_rate,
                "c6_win_rate":         e.c6_win_rate,
            })
        ml_probs = predict_scores(entries_dict, model)  # {lane: prob}

        # 線形スコア計算
        linear_scores = score_entries(entries, condition)
        linear_map = {s.lane: s for s in linear_scores}

        # 正規化: ML確率を [0, 70] スケールに変換
        probs_arr = np.array(list(ml_probs.values()))
        p_min, p_max = probs_arr.min(), probs_arr.max()
        if p_max > p_min:
            ml_normalized = {
                lane: (p - p_min) / (p_max - p_min) * 70.0
                for lane, p in ml_probs.items()
            }
        else:
            ml_normalized = {lane: 35.0 for lane in ml_probs}

        # ブレンド
        blended: list[EntryScore] = []
        for e in entries:
            lin = linear_map.get(e.lane)
            ml_score  = ml_normalized.get(e.lane, 35.0)
            lin_score = lin.morning_score if lin else 35.0
            pre_score = lin.pre_race_score if lin else 0.0

            blended_morning = blend_alpha * ml_score + (1.0 - blend_alpha) * lin_score
            blended.append(EntryScore(
                lane=e.lane,
                racer_name=e.racer_name,
                morning_score=blended_morning,
                pre_race_score=pre_score,
            ))

        blended.sort(key=lambda s: s.total, reverse=True)
        return blended

    except Exception as _ml_err:
        # ⑧ MLエラーを可視化（以前は黙って無視していた）
        import logging as _log
        _log.getLogger(__name__).warning(
            "score_entries_ml: ML処理でエラーが発生しました → 線形スコアにフォールバック: %s",
            _ml_err
        )
        return score_entries(entries, condition)


def make_pick(scores: list[EntryScore]) -> str:
    """上位3艇を三連複1点として返す (例: '1-2-4')

    実績分析 (2199レース):
      1号艇の実際の3着内率 = 82.1%
      スコアモデルが1号艇を除外した場合の的中率 = 5.8% (ほぼランダム)
      1号艇を含む場合の的中率 = 20.3%
    → 1号艇が上位3位に入っていない場合は強制包含 (+2.1%的中率改善)
    """
    if not scores:
        return ""

    top3_lanes = {s.lane for s in scores[:3]}

    if 1 in top3_lanes:
        # 1号艇が既にスコア上位3位以内 → そのまま
        top3 = sorted(scores[:3], key=lambda s: s.lane)
    else:
        # 1号艇を強制包含: スコア1位・2位の2艇 + 1号艇
        # (1号艇の3着内率82.1% — 除外すると的中率5.8%にまで落ちる)
        others = [s for s in scores if s.lane != 1][:2]
        combined = sorted([s for s in scores if s.lane == 1] + others,
                          key=lambda s: s.lane)
        top3 = combined

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


# ── 場別・クラス別 補正値 (stadium_stats.json から動的ロード) ───────────────
# 全体平均との差が ±2% 以上あれば補正対象とする閾値
_OVERALL_HIT_RATE = 0.186   # 初期値: 全体平均 (update_stats.py 実行後は実績値で上書きされる)
_BUY_INELIGIBLE_THRESHOLD = 0.110   # この的中率未満の場はBUY絶対不可 (びわこ8.3%/津8.3%等)


def _get_stadium_conf_mul(stadium: Optional[str]) -> tuple[float, str]:
    """
    場名から (confidence乗数, 表示文字列) を返す。
    stadium_stats.json が更新されると自動的に反映される。

    sample=0  → 初期値(硬直値)として信頼し使用
    0<sample<30 → データ不足のため中立扱い
    sample>=30  → 実績値として使用
    """
    if not stadium:
        return 1.0, ""
    entry = _STATS.get("stadiums", {}).get(stadium)
    if not entry:
        return 1.0, ""
    mul = float(entry.get("conf_mul", 1.0))
    hit_rate = float(entry.get("hit_rate", _OVERALL_HIT_RATE))
    sample = int(entry.get("sample", 0))
    if 0 < sample < 30:   # 少量データは中立扱い（初期値=0は初期推定値として使用）
        return 1.0, ""
    return mul, f"{hit_rate*100:.1f}%"


def _is_low_perf_stadium(stadium: Optional[str]) -> bool:
    """的中率が閾値未満の場かどうか"""
    if not stadium:
        return False
    entry = _STATS.get("stadiums", {}).get(stadium)
    if not entry:
        return False
    sample = int(entry.get("sample", 0))
    if 0 < sample < 30:
        return False
    return float(entry.get("hit_rate", _OVERALL_HIT_RATE)) < _BUY_INELIGIBLE_THRESHOLD


def _get_lane1_class_mul(lane1_class: Optional[str]) -> tuple[float, str]:
    """1号艇クラスから (confidence乗数, 的中率表示) を返す"""
    if not lane1_class:
        return 1.0, ""
    cls = lane1_class.upper()
    entry = _STATS.get("lane1_class", {}).get(cls)
    if not entry:
        return 1.0, ""
    mul = float(entry.get("conf_mul", 1.0))
    hit_rate = float(entry.get("hit_rate", _OVERALL_HIT_RATE))
    sample = int(entry.get("sample", 0))
    if 0 < sample < 20:
        return 1.0, ""
    return mul, f"{hit_rate*100:.1f}%"


def decide(
    scores: list[EntryScore],
    condition: RaceCondition,
    pick_payout: Optional[int] = None,      # 後方互換（all_odds がない場合のフィルタ用）
    lane1_approach: Optional[int] = None,
    all_odds: Optional[dict[str, int]] = None,  # 全20組み合わせのオッズ（EVモード）
    stadium: Optional[str] = None,          # 場名（場別補正に使用）
    lane1_class: Optional[str] = None,      # 1号艇の級別（クラス補正に使用）
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

    # ── 場別補正 (stadium_stats.json から動的ロード) ─────────────────────────
    s_mul, s_hit_pct = _get_stadium_conf_mul(stadium)
    low_perf = _is_low_perf_stadium(stadium)
    if s_mul != 1.0 and stadium:
        confidence = min(100.0, confidence * s_mul)
        if low_perf:
            reasons.append(
                f"⚠️ {stadium}は低精度場(的中率{s_hit_pct}) "
                f"— 信頼度×{s_mul:.2f} / BUY不可・CANDIDATE止まり"
            )
        else:
            reasons.append(
                f"✅ {stadium}は高精度場(的中率{s_hit_pct}) "
                f"— 信頼度×{s_mul:.2f}"
            )

    # ── 1号艇クラス補正 (stadium_stats.json から動的ロード) ──────────────────
    cls_mul, cls_hit_pct = _get_lane1_class_mul(lane1_class)
    if cls_mul != 1.0 and lane1_class:
        confidence = min(100.0, confidence * cls_mul)
        reasons.append(
            f"1号艇{lane1_class}級"
            f"{f'(的中率{cls_hit_pct})' if cls_hit_pct else ''}"
            f" — 信頼度×{cls_mul:.2f}"
        )

    forced_skip = wind_rough or wave_rough or approach_unstable
    is_watch    = False

    # BUY/CANDIDATE 閾値 (thresholds.json から動的ロード — tune_thresholds.py が毎週更新)
    _th = _THRESHOLDS
    score_buy_conf  = _th.get("score_buy_conf",  70.0)
    score_buy_gap   = _th.get("score_buy_gap",   10.0)
    score_cand_conf = _th.get("score_cand_conf", 62.0)
    score_cand_gap  = _th.get("score_cand_gap",   7.0)

    lane1_label = ["1位", "2位", "3位", "4位以下"][min(lane1_rank, 3)] if lane1_rank >= 0 else "不明"
    approach_note = f" (コース{lane1_approach}進入)" if lane1_approach else ""

    if not forced_skip and confidence >= score_buy_conf and gap >= score_buy_gap and not low_perf:
        decision = "buy"
        rank = "S"
        reasons.append(f"上位3艇のスコア差が明確 (gap={gap:.1f} / 1号艇{lane1_label}{approach_note})")

    elif not forced_skip and confidence >= score_cand_conf and gap >= score_cand_gap:
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
            # BUY条件: EV>ev_buy かつ conf>=conf_buy かつ 1号艇がpickに含まれること
            # 閾値は thresholds.json (tune_thresholds.py が毎週最適化) から動的ロード
            ev_buy   = _th.get("ev_buy",   0.25)
            conf_buy = _th.get("conf_buy", 68.0)
            ev_cand  = _th.get("ev_cand",  0.15)
            conf_cand = _th.get("conf_cand", 65.0)

            has_lane1_in_pick = ev_pick and '1' in ev_pick.split('-')

            # ── EV上限キャップ: EV > 0.50 は市場が「ほぼ来ない」と判断した組み合わせ
            # 実績: EV>0.5 → 的中率5.2% (59/3), EV 0.25-0.5 → 的中率30.0% (10/3)
            # 高すぎるEVはモデルの確率推定が狂っているサイン → CANDIDATE止まり
            ev_buy_max = _th.get("ev_buy_max", 0.50)   # 上限 (デフォルト0.50)
            ev_is_contrarian = (best_ev > ev_buy_max)

            if best_ev > ev_buy and best_ev <= ev_buy_max and confidence >= conf_buy and has_lane1_in_pick and not low_perf:
                decision = "buy"
                rank     = "S"
                reasons.append(
                    f"EV={best_ev:+.2f} (期待値+{best_ev*100:.0f}%) / conf={round(confidence,1)} "
                    f"/ gap={gap:.1f} — 市場が過小評価している組み合わせ"
                )
            elif best_ev > ev_buy and ev_is_contrarian:
                # EV上限超え → 市場と大きく乖離 = 逆選択リスク → CANDIDATEに降格
                decision = "candidate"
                rank     = "A"
                reasons.append(
                    f"EV={best_ev:+.2f} (EV上限{ev_buy_max:.2f}超 — 逆選択リスク) / conf={round(confidence,1)} "
                    f"/ gap={gap:.1f} → CANDIDATE止まり"
                )
            elif best_ev > ev_cand and confidence >= conf_cand:
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
