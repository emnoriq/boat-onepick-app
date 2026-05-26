#!/usr/bin/env python3
"""
機械学習スコアリングモジュール (勾配ブースティング)

線形スコア式 (scoring.py) の代わりに GradientBoostingClassifier を使い、
三連複的中率を最大化する。

【アーキテクチャ】
  - 1艇ごとに「この艇が3着以内に入る確率」を予測
  - レース内で確率上位3艇を pick とする
  - EV計算・decide() との統合は scoring.py の既存ロジックを流用

【特徴量 (per entry)】
  lane                  : 枠番 (1-6)
  racer_class_enc       : 級別 (A1=3, A2=2, B1=1, B2=0)
  national_top3_rate    : 全国3連対率
  local_top3_rate       : 当地3連対率 (なければ local_win_rate*2 で近似)
  motor_rate_rel        : モーター率 - 艦隊平均
  boat_rate             : ボート2連対率
  avg_st                : 平均ST
  f_count               : F回数
  l_count               : L回数
  course_win_rate       : 実際の出走コース別1着率
  fleet_size            : 艦隊艇数 (通常6)

【学習データ】
  entries テーブル + results テーブルから自動生成
  Target: was_top3 (trifecta_result に艇番が含まれるか)

【使い方】
  # 学習
  cd scraper && python3 scoring_ml.py train
  cd scraper && python3 scoring_ml.py train --days 180

  # テスト予測
  cd scraper && python3 scoring_ml.py evaluate

  # main.py と統合 (--use-ml フラグ)
  python3 main.py pre_race --use-ml
"""

import argparse
import json
import logging
import os
import pickle
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model_gbm.pkl")
META_PATH  = os.path.join(os.path.dirname(__file__), "model_meta.json")

# 級別エンコーディング
CLASS_ENC = {"A1": 3, "A2": 2, "B1": 1, "B2": 0}


# ── 特徴量エンジニアリング ────────────────────────────────────────────────────

def entry_to_features(e: dict, fleet_avg_motor: float) -> list[float]:
    """
    1艇のDB行から特徴量ベクトルを生成する。

    Returns:
        list of 11 floats
    """
    lane           = int(e.get("lane") or 4)
    cls_raw        = (e.get("racer_class") or "B1").upper()
    cls_enc        = CLASS_ENC.get(cls_raw, 1)
    nat_top3       = float(e.get("national_top3_rate") or 0.0)
    loc_top3       = float(e.get("local_top3_rate") or 0.0)
    if loc_top3 == 0.0:
        loc_top3   = float(e.get("local_win_rate") or 0.0) * 2.0
    motor_rel      = float(e.get("motor_rate") or 40.0) - fleet_avg_motor
    boat_rate      = float(e.get("boat_rate") or 0.0)
    avg_st         = float(e.get("avg_st") or 0.15)
    f_count        = int(e.get("f_count") or 0)
    l_count        = int(e.get("l_count") or 0)
    # 出走コース別1着率 (lane番に対応する cx_win_rate)
    course_key     = f"c{lane}_win_rate"
    course_wr      = float(e.get(course_key) or 0.0)

    return [
        lane,
        cls_enc,
        nat_top3,
        loc_top3,
        motor_rel,
        boat_rate,
        avg_st,
        float(f_count),
        float(l_count),
        course_wr,
    ]


FEATURE_NAMES = [
    "lane", "class_enc", "national_top3_rate", "local_top3_rate",
    "motor_rate_rel", "boat_rate", "avg_st", "f_count", "l_count",
    "course_win_rate",
]


# ── データ取得 ────────────────────────────────────────────────────────────────

def pull_training_data(db, days: Optional[int] = None):
    """
    (X, y, race_ids, lanes) を返す。
    X: np.ndarray (n_samples, n_features)
    y: np.ndarray (n_samples,) 0/1
    race_ids: list[str]
    lanes: list[int]
    """
    logger.info("学習データ取得開始...")
    JST = timezone(timedelta(hours=9))

    # ── 結果取得 ─────────────────────────────────────────────────────────────
    results_raw: list[dict] = []
    offset = 0
    while True:
        q = db.table("results").select("race_id,trifecta_result")
        if days:
            # race_id から日付を逆引きするのが手間なので全件取ってフィルタ
            pass
        batch = q.range(offset, offset + 999).execute().data
        if not batch:
            break
        results_raw.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    valid_results = {
        r["race_id"]: set(r["trifecta_result"].split("-"))
        for r in results_raw
        if r.get("trifecta_result") and "-" in r["trifecta_result"]
    }

    if days:
        cutoff = (datetime.now(JST).date() - timedelta(days=days)).isoformat()
        races_raw: list[dict] = []
        offset = 0
        while True:
            batch = (db.table("races").select("id,race_date")
                     .gte("race_date", cutoff)
                     .range(offset, offset + 999).execute().data)
            if not batch:
                break
            races_raw.extend(batch)
            if len(batch) < 1000:
                break
            offset += 1000
        recent_ids = {r["id"] for r in races_raw}
        valid_results = {k: v for k, v in valid_results.items() if k in recent_ids}
        logger.info("日付フィルタ後: %d件 (%d日)", len(valid_results), days)

    race_id_list = list(valid_results.keys())
    logger.info("有効レース: %d件", len(race_id_list))

    # ── entries 一括取得 ──────────────────────────────────────────────────────
    entries_by_race: dict[str, list[dict]] = {}
    for i in range(0, len(race_id_list), 50):
        chunk = race_id_list[i:i + 50]
        batch = (db.table("entries").select("*")
                 .in_("race_id", chunk).execute().data)
        for e in batch:
            entries_by_race.setdefault(e["race_id"], []).append(e)

    # ── 特徴量・ラベル生成 ────────────────────────────────────────────────────
    X_rows, y_rows, race_ids_out, lanes_out = [], [], [], []

    for race_id, top3_set in valid_results.items():
        entries = entries_by_race.get(race_id, [])
        if len(entries) < 4:
            continue

        motor_rates = [float(e.get("motor_rate") or 40.0) for e in entries]
        fleet_avg   = sum(motor_rates) / len(motor_rates)

        for e in entries:
            features = entry_to_features(e, fleet_avg)
            was_top3 = 1 if str(e.get("lane")) in top3_set else 0
            X_rows.append(features)
            y_rows.append(was_top3)
            race_ids_out.append(race_id)
            lanes_out.append(int(e.get("lane") or 0))

    X = np.array(X_rows, dtype=np.float32)
    y = np.array(y_rows, dtype=np.int32)
    logger.info("学習データ: %d艇 (top3率=%.1f%%)", len(y), y.mean() * 100)
    return X, y, race_ids_out, lanes_out


# ── 学習 ─────────────────────────────────────────────────────────────────────

def train(db, days: Optional[int] = None):
    """モデルを学習してファイルに保存する。"""
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    from sklearn.preprocessing import StandardScaler
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.pipeline import Pipeline

    X, y, race_ids, lanes = pull_training_data(db, days=days)

    if len(X) < 500:
        logger.error("データが少なすぎます (%d件)。学習を中止。", len(X))
        return None

    # ── モデル定義 ────────────────────────────────────────────────────────────
    # GBM + Isotonic Calibration でよく較正された確率を出力
    base_gbm = GradientBoostingClassifier(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=4,
        min_samples_leaf=20,
        subsample=0.8,
        random_state=42,
    )
    # 確率較正 (Isotonic) で confidence と実際の的中率を一致させる
    model = CalibratedClassifierCV(base_gbm, method="isotonic", cv=3)

    # ── クロスバリデーション ────────────────────────────────────────────────
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(
        GradientBoostingClassifier(
            n_estimators=200, learning_rate=0.05, max_depth=4,
            min_samples_leaf=20, subsample=0.8, random_state=42,
        ),
        X, y, cv=skf, scoring="roc_auc",
    )
    logger.info("CV AUC: %.3f ± %.3f", cv_scores.mean(), cv_scores.std())

    # ── 全データで再学習 ──────────────────────────────────────────────────────
    logger.info("全データで最終学習...")
    model.fit(X, y)

    # ── 特徴量重要度の確認 ───────────────────────────────────────────────────
    try:
        fi = model.calibrated_classifiers_[0].estimator.feature_importances_
        logger.info("特徴量重要度:")
        for name, imp in sorted(zip(FEATURE_NAMES, fi), key=lambda x: -x[1]):
            logger.info("  %-22s %.4f", name, imp)
    except Exception:
        pass

    # ── 保存 ──────────────────────────────────────────────────────────────────
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    JST = timezone(timedelta(hours=9))
    meta = {
        "trained_at":  datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
        "n_samples":   int(len(X)),
        "n_features":  int(X.shape[1]),
        "feature_names": FEATURE_NAMES,
        "cv_auc_mean": round(float(cv_scores.mean()), 4),
        "cv_auc_std":  round(float(cv_scores.std()),  4),
        "days":        days,
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    logger.info("モデル保存: %s", MODEL_PATH)
    logger.info("メタ情報 : %s", META_PATH)
    return model


# ── 推論 ─────────────────────────────────────────────────────────────────────

def load_model():
    """保存済みモデルをロードする。存在しなければ None を返す。"""
    if not os.path.exists(MODEL_PATH):
        return None
    try:
        with open(MODEL_PATH, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        logger.warning("モデルロード失敗: %s", e)
        return None


def predict_scores(entries: list[dict], model) -> dict[int, float]:
    """
    エントリリストに対して ML スコア (top3確率) を返す。

    Returns:
        {lane: prob_top3}
    """
    motor_rates = [float(e.get("motor_rate") or 40.0) for e in entries]
    fleet_avg   = sum(motor_rates) / len(motor_rates)

    X = np.array([entry_to_features(e, fleet_avg) for e in entries], dtype=np.float32)
    probs = model.predict_proba(X)[:, 1]  # P(top3)

    return {int(e.get("lane", i + 1)): float(p)
            for i, (e, p) in enumerate(zip(entries, probs))}


# ── 評価 ──────────────────────────────────────────────────────────────────────

def evaluate(db, days: Optional[int] = None):
    """ML モデルと線形スコアの精度を比較する。"""
    from scoring import EntryData, score_entries, RaceCondition, make_pick

    model = load_model()
    if model is None:
        logger.error("モデルが見つかりません。先に python3 scoring_ml.py train を実行してください。")
        return

    X, y, race_ids, lanes = pull_training_data(db, days=days)

    # ── レースごとに top3 予測を評価 ─────────────────────────────────────────
    race_ids_uniq = list(dict.fromkeys(race_ids))  # 順序保持の重複除去
    idx_map: dict[str, list[int]] = {}
    for i, rid in enumerate(race_ids):
        idx_map.setdefault(rid, []).append(i)

    ml_hits    = 0
    score_hits = 0
    n_races    = 0

    # 結果セット取得
    valid_results: dict[str, set] = {}
    offset = 0
    while True:
        batch = db.table("results").select("race_id,trifecta_result").range(offset, offset + 999).execute().data
        if not batch:
            break
        for r in batch:
            if r.get("trifecta_result") and "-" in r["trifecta_result"]:
                valid_results[r["race_id"]] = set(r["trifecta_result"].split("-"))
        if len(batch) < 1000:
            break
        offset += 1000

    # entries も取得（線形スコア計算用）
    entries_by_race: dict[str, list[dict]] = {}
    for i in range(0, len(race_ids_uniq), 50):
        chunk = race_ids_uniq[i:i + 50]
        batch = db.table("entries").select("*").in_("race_id", chunk).execute().data
        for e in batch:
            entries_by_race.setdefault(e["race_id"], []).append(e)

    # ML スコア
    for race_id in race_ids_uniq:
        actual = valid_results.get(race_id)
        entries = entries_by_race.get(race_id, [])
        if not actual or len(entries) < 4:
            continue

        motor_rates = [float(e.get("motor_rate") or 40.0) for e in entries]
        fleet_avg   = sum(motor_rates) / len(motor_rates)
        X_race = np.array([entry_to_features(e, fleet_avg) for e in entries], dtype=np.float32)
        probs = model.predict_proba(X_race)[:, 1]
        top3_idx = sorted(range(len(probs)), key=lambda i: -probs[i])[:3]
        ml_top3 = {str(entries[i]["lane"]) for i in top3_idx}

        # 線形スコア
        entry_objs = [EntryData(
            lane=int(e["lane"]),
            racer_name=e.get("racer_name", ""),
            racer_class=e.get("racer_class") or "",
            national_top3_rate=float(e.get("national_top3_rate") or 0),
            local_top3_rate=float(e.get("local_top3_rate") or 0),
            local_win_rate=float(e.get("local_win_rate") or 0),
            motor_rate=float(e.get("motor_rate") or 0),
            boat_rate=float(e.get("boat_rate") or 0),
            avg_st=float(e.get("avg_st") or 0.15),
            f_count=int(e.get("f_count") or 0),
            l_count=int(e.get("l_count") or 0),
            c1_win_rate=float(e.get("c1_win_rate") or 0),
            c2_win_rate=float(e.get("c2_win_rate") or 0),
            c3_win_rate=float(e.get("c3_win_rate") or 0),
            c4_win_rate=float(e.get("c4_win_rate") or 0),
            c5_win_rate=float(e.get("c5_win_rate") or 0),
            c6_win_rate=float(e.get("c6_win_rate") or 0),
        ) for e in entries]
        scores = score_entries(entry_objs, RaceCondition())
        score_top3 = {str(s.lane) for s in scores[:3]}

        if ml_top3 == actual:
            ml_hits += 1
        if score_top3 == actual:
            score_hits += 1
        n_races += 1

    logger.info("=== 比較評価 (%d レース) ===", n_races)
    logger.info("ML  スコア的中率: %.1f%%  (%d/%d)",
                ml_hits / n_races * 100, ml_hits, n_races)
    logger.info("線形スコア的中率: %.1f%%  (%d/%d)",
                score_hits / n_races * 100, score_hits, n_races)
    improvement = (ml_hits - score_hits) / n_races
    logger.info("差: %+.1f%%  (%s)",
                improvement * 100, "ML優位" if improvement > 0 else "線形スコア優位" if improvement < 0 else "同等")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    from dotenv import load_dotenv
    load_dotenv()
    sys.path.insert(0, os.path.dirname(__file__))
    from db import get_client

    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["train", "evaluate"],
                        help="train: 学習して保存 / evaluate: 線形スコアと比較")
    parser.add_argument("--days", type=int, default=None,
                        help="直近N日のみ使用 (省略時: 全件)")
    args = parser.parse_args()

    db = get_client()

    if args.command == "train":
        train(db, days=args.days)
    elif args.command == "evaluate":
        evaluate(db, days=args.days)


if __name__ == "__main__":
    main()
