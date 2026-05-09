/**
 * 三連複1点・4回転がしルート計算ロジック
 *
 * ロールプラン専用の判定閾値（scoring.py より厳しい）:
 *   buy tier:       decision=buy       && confidence≥75 && gap≥12
 *   candidate tier: decision=candidate && confidence≥65 && gap≥10
 *   watch tier:     is_watch=true      && confidence≥55 && gap≥7（荒れ要因は除外）
 */

import type { ScheduleRow } from "./supabase";

// ── 型定義 ──────────────────────────────────────────────────────────────────

export type RollTier = "buy" | "candidate" | "watch";

/** ルート内の1ステップ */
export type RollStep = ScheduleRow & {
  rollTier: RollTier;
  /** 前ステップの締切時刻からの間隔（分）。STEP1 は null。 */
  intervalMinutes: number | null;
  /** ステップの状態 */
  stepStatus: "DONE" | "RESULT_WAIT" | "BUY" | "WAIT";
};

/** 4本の組み合わせで構成される転がしルート */
export type RollRoute = {
  id: number;
  steps: RollStep[];
  avgConfidence: number;
  avgGap: number;
  buyCount: number;
  candidateCount: number;
  watchCount: number;
  /** 連続するステップ間の最短間隔（分） */
  minIntervalMinutes: number;
  rating: "strong" | "normal" | "weak";
  score: number;
};

export type RollJudgment = "go" | "conditional" | "skip";

/** buildRollPlan() の戻り値 */
export type RollPlan = {
  judgment: RollJudgment;
  judgeText: string;
  bestRoute: RollRoute | null;
  backupRoutes: RollRoute[];  // 最大3件
  allCandidates: RollStep[];  // buy / candidate / watch 全件（close_time 昇順）
  allRows: ScheduleRow[];     // 全レース（close_time 昇順）
  evaluatedCount: number;
  buyCount: number;
  candidateCount: number;
  watchCount: number;
  skipCount: number;
};

// ── ヘルパー ────────────────────────────────────────────────────────────────

function minutesBetween(a: string, b: string): number {
  return (new Date(b).getTime() - new Date(a).getTime()) / 60000;
}

/**
 * ScheduleRow をロールプランの tier に分類する。
 * null = roll-plan の対象外（skip 扱い）
 */
export function getRollTier(row: ScheduleRow): RollTier | null {
  const conf = row.confidence ?? 0;
  const gap  = row.gap        ?? 0;
  if (!row.decision || !row.pick) return null;

  if (row.decision === "buy"       && conf >= 75 && gap >= 12) return "buy";
  if (row.decision === "candidate" && conf >= 65 && gap >= 10) return "candidate";
  // row.is_watch は isWatchCandidate() で計算済み（荒れ要因は除外済み）
  if (row.decision === "skip" && row.is_watch && conf >= 55 && gap >= 7) return "watch";
  return null;
}

function getStepStatus(
  row: ScheduleRow,
  isNextBuy: boolean,
): RollStep["stepStatus"] {
  if (row.status === "finished") return "DONE";
  if (row.status === "final")    return "RESULT_WAIT";
  if (isNextBuy)                 return "BUY";
  return "WAIT";
}

function buildStep(
  row: ScheduleRow,
  tier: RollTier,
  prev: ScheduleRow | null,
  isNextBuy: boolean,
): RollStep {
  return {
    ...row,
    rollTier: tier,
    intervalMinutes:
      prev !== null ? Math.round(minutesBetween(prev.close_time, row.close_time)) : null,
    stepStatus: getStepStatus(row, isNextBuy),
  };
}

function computeRouteScore(
  steps: { rollTier: RollTier; confidence: number | null; gap: number | null; close_time: string }[],
): number {
  const buyCount   = steps.filter((s) => s.rollTier === "buy").length;
  const candCount  = steps.filter((s) => s.rollTier === "candidate").length;
  const watchCount = steps.filter((s) => s.rollTier === "watch").length;
  const avgConf    = steps.reduce((s, r) => s + (r.confidence ?? 0), 0) / 4;
  const avgGap     = steps.reduce((s, r) => s + (r.gap ?? 0), 0) / 4;
  // 開始が早いほど微小ボーナス（時間で比較）
  const startHour  = new Date(steps[0].close_time).getUTCHours() + 9; // JST

  return (
    buyCount   * 10000 +
    (4 - candCount)  * 100 +
    (watchCount === 0 ? 500 : 0) +
    avgConf    * 10 +
    avgGap          +
    Math.max(0, 18 - startHour) // 早い開始に微小加点（最大 18 点）
  );
}

// ── メイン関数 ────────────────────────────────────────────────────────────

/**
 * 今日の全レース一覧から4回転がしルートを計算する。
 * @param allRows     getScheduleData() の rows（close_time 昇順）
 * @param minGapMin   連続ステップ間の最短間隔（分）。デフォルト 30。
 */
export function buildRollPlan(
  allRows: ScheduleRow[],
  minGapMin = 30,
): RollPlan {
  // ── 候補分類 ─────────────────────────────────────────────────────────────
  type Candidate = ScheduleRow & { rollTier: RollTier };
  const candidates: Candidate[] = [];
  for (const row of allRows) {
    const tier = getRollTier(row);
    if (tier) candidates.push({ ...row, rollTier: tier });
  }
  // close_time 昇順（DB からの並びを維持するが念のため）
  candidates.sort((a, b) => a.close_time.localeCompare(b.close_time));

  // 統計カウント
  const evaluatedCount = allRows.filter((r) => r.decision !== null).length;
  const buyCount       = allRows.filter((r) => r.decision === "buy").length;
  const candidateCount = allRows.filter((r) => r.decision === "candidate").length;
  const watchCount     = allRows.filter((r) => r.is_watch).length;
  const skipCount      = allRows.filter((r) => r.decision === "skip" && !r.is_watch).length;

  // ── 全 4-tuple を列挙 ──────────────────────────────────────────────────
  // 候補が多すぎると O(n^4) が爆発するため上位 MAX_CANDIDATES_FOR_ENUM 件に絞る
  const MAX_CANDIDATES_FOR_ENUM = 30;
  const cappedCandidates =
    candidates.length > MAX_CANDIDATES_FOR_ENUM
      ? candidates.slice(0, MAX_CANDIDATES_FOR_ENUM)
      : candidates;

  const routes: RollRoute[] = [];
  const n = cappedCandidates.length;

  for (let i = 0; i < n - 3; i++) {
    for (let j = i + 1; j < n - 2; j++) {
      if (minutesBetween(cappedCandidates[i].close_time, cappedCandidates[j].close_time) < minGapMin) continue;
      for (let k = j + 1; k < n - 1; k++) {
        if (minutesBetween(cappedCandidates[j].close_time, cappedCandidates[k].close_time) < minGapMin) continue;
        for (let l = k + 1; l < n; l++) {
          if (minutesBetween(cappedCandidates[k].close_time, cappedCandidates[l].close_time) < minGapMin) continue;

          const idxs = [i, j, k, l];

          // 最初の「締切前」ステップ = 次に買うべきステップ
          const nextBuyIdx = idxs.find((idx) => cappedCandidates[idx].status === "scheduled") ?? -1;

          const steps = idxs.map((idx, pos) =>
            buildStep(
              cappedCandidates[idx],
              cappedCandidates[idx].rollTier,
              pos > 0 ? cappedCandidates[idxs[pos - 1]] : null,
              cappedCandidates[idx].status === "scheduled" && idx === nextBuyIdx,
            ),
          );

          const buyCount_r   = steps.filter((s) => s.rollTier === "buy").length;
          const candCount_r  = steps.filter((s) => s.rollTier === "candidate").length;
          const watchCount_r = steps.filter((s) => s.rollTier === "watch").length;
          const avgConf      = parseFloat(
            (steps.reduce((s, r) => s + (r.confidence ?? 0), 0) / 4).toFixed(1),
          );
          const avgGap       = parseFloat(
            (steps.reduce((s, r) => s + (r.gap ?? 0), 0) / 4).toFixed(1),
          );
          const intervals    = [
            minutesBetween(cappedCandidates[i].close_time, cappedCandidates[j].close_time),
            minutesBetween(cappedCandidates[j].close_time, cappedCandidates[k].close_time),
            minutesBetween(cappedCandidates[k].close_time, cappedCandidates[l].close_time),
          ];
          const minIntervalMinutes = Math.round(Math.min(...intervals));

          routes.push({
            id: routes.length,
            steps,
            avgConfidence: avgConf,
            avgGap,
            buyCount: buyCount_r,
            candidateCount: candCount_r,
            watchCount: watchCount_r,
            minIntervalMinutes,
            rating: buyCount_r >= 3 ? "strong" : buyCount_r >= 2 ? "normal" : "weak",
            score: computeRouteScore(steps),
          });
        }
      }
    }
  }

  routes.sort((a, b) => b.score - a.score);

  // ── 候補一覧（all candidates with step status） ───────────────────────
  const firstScheduledIdx = candidates.findIndex(
    (c) => c.status === "scheduled",
  );
  const allCandidates: RollStep[] = candidates.map((c, idx) =>
    buildStep(
      c,
      c.rollTier,
      null,
      idx === firstScheduledIdx,
    ),
  );

  // ── ルート判定 ────────────────────────────────────────────────────────
  const bestRoute    = routes[0] ?? null;
  const backupRoutes = routes.slice(1, 4);

  let judgment: RollJudgment;
  let judgeText: string;

  if (!bestRoute) {
    judgment  = "skip";
    judgeText = "今日は4回転がしに適したルートがありません。";
  } else if (
    // 「go」条件を緩和: STEP1 が buy でなくても、全体が強ければ go とする
    bestRoute.watchCount === 0 &&
    bestRoute.buyCount + bestRoute.candidateCount === 4 &&
    bestRoute.buyCount >= 2 &&
    bestRoute.avgConfidence >= 68
  ) {
    judgment  = "go";
    judgeText =
      "今日は4回転がし候補があります。ただし、最終判断は各レースの展示データ取得後に行ってください。";
  } else {
    judgment  = "conditional";
    judgeText =
      "4本の仮ルートはありますが、条件付きです。実投票は慎重に判断してください。";
  }

  return {
    judgment,
    judgeText,
    bestRoute,
    backupRoutes,
    allCandidates,
    allRows,
    evaluatedCount,
    buyCount,
    candidateCount,
    watchCount,
    skipCount,
  };
}
