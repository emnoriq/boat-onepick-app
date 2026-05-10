import { createClient } from "@supabase/supabase-js";

function db() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) throw new Error("NEXT_PUBLIC_SUPABASE_URL / ANON_KEY が設定されていません");
  // Next.js 14 の Data Cache を無効化 (force-dynamic だけでは fetch キャッシュは無効にならない)
  return createClient(url, key, {
    global: { fetch: (input, init) => fetch(input, { ...init, cache: "no-store" }) },
  });
}

export type Race = {
  id: string;
  race_date: string;
  stadium: string;
  race_no: number;
  close_time: string;
  status: "scheduled" | "final" | "finished";
};

export type Entry = {
  id: string;
  race_id: string;
  lane: number;
  racer_name: string;
  racer_class: string | null;
  national_win_rate: number | null;
  local_win_rate: number | null;
  motor_rate: number | null;
  boat_rate: number | null;
  avg_st: number | null;
  exhibition_time: number | null;
  exhibition_st: number | null;
  approach_lane: number | null;
  tilt: number | null;
  entry_score: number | null;
};

export type Prediction = {
  id: string;
  race_id: string;
  pick: string;
  confidence: number;
  decision: "buy" | "candidate" | "skip";
  reason: string | null;
  gap: number | null;       // 3位-4位スコア差（新設計から保存）
  rank_today: number | null;
  is_hit: boolean | null;
};

export type RaceResult = {
  id: string;
  race_id: string;
  trifecta_result: string | null;
  payout: number | null;
  popularity: number | null;
  prediction_hit: boolean | null;
};

// predictions/results は race_id に unique 制約があるため
// Supabase は配列でなく単一オブジェクト (または null) で返す
export type RaceWithPrediction = Race & {
  predictions: Prediction | null;
  results: RaceResult | null;
};

export async function getTodayPredictions(date: string): Promise<RaceWithPrediction[]> {
  const { data, error } = await db()
    .from("races")
    .select(`
      *,
      predictions(*),
      results(*)
    `)
    .eq("race_date", date)
    .order("close_time", { ascending: true });

  if (error) throw error;
  return (data ?? []) as RaceWithPrediction[];
}

export async function getRaceDetail(raceId: string): Promise<{
  race: Race;
  entries: Entry[];
  prediction: Prediction | null;
  result: RaceResult | null;
} | null> {
  const client = db();
  const [raceRes, entriesRes, predRes, resultRes] = await Promise.all([
    client.from("races").select("*").eq("id", raceId).single(),
    client.from("entries").select("*").eq("race_id", raceId).order("lane"),
    client.from("predictions").select("*").eq("race_id", raceId).maybeSingle(),
    client.from("results").select("*").eq("race_id", raceId).maybeSingle(),
  ]);

  if (raceRes.error || !raceRes.data) return null;
  return {
    race: raceRes.data as Race,
    entries: (entriesRes.data ?? []) as Entry[],
    prediction: predRes.data as Prediction | null,
    result: resultRes.data as RaceResult | null,
  };
}

export type DebugRow = {
  race_id: string;
  stadium: string;
  race_no: number;
  close_time: string;
  pick: string;
  confidence: number;
  decision: "buy" | "candidate" | "skip";
  is_watch: boolean;   // decision=skip かつ reason に "[watch]" を含む検証候補
  reason: string | null;
  gap: number | null;
  has_exhibition: boolean;
  // 結果
  trifecta_result: string | null;
  payout: number | null;
  popularity: number | null;
  prediction_hit: boolean | null;
};

/** reason テキストから gap 値を抽出 (例: "gap=4.1" → 4.1) */
function extractGap(reason: string): number | null {
  const m = reason.match(/gap=([\d.]+)/);
  return m ? parseFloat(m[1]) : null;
}

/**
 * watch 候補かどうかを判定する
 * - reason に "[watch]" マーカーがある場合 (新設計: pre_race_scan から)
 * - または confidence ≥ 55 AND gap ≥ 7 AND skip AND 荒れ要因なし (旧データ互換)
 */
export function isWatchCandidate(
  decision: string,
  confidence: number,
  reason: string | null,
): boolean {
  if (!reason) return false;
  // 新設計: "[watch]" マーカーで判定
  if (reason.includes("[watch]")) return true;
  // 旧データ互換: confidence/gap から推定
  if (decision !== "skip") return false;
  if (confidence < 55) return false;
  if (reason.includes("荒れ要因") || reason.includes("進入が乱れ")) return false;
  const gap = extractGap(reason);
  return gap !== null && gap >= 7;
}

/**
 * 展示データ取得済みかどうかを判定
 * - 旧設計: "朝スキャン暫定" がなければ展示済み
 * - 新設計: "[展示未取得]" がなければ展示済み (pre_race のみが prediction を作成)
 */
function hasExhibitionData(reason: string | null): boolean {
  if (!reason) return false;
  return !reason.includes("朝スキャン暫定") && !reason.includes("[展示未取得]");
}

export async function getDebugPredictions(date: string): Promise<DebugRow[]> {
  const { data, error } = await db()
    .from("races")
    .select(`*, predictions(*), results(*)`)
    .eq("race_date", date)
    .order("close_time", { ascending: true });

  if (error) throw error;

  const rows: DebugRow[] = [];
  for (const race of (data ?? []) as any[]) {
    const pred = race.predictions as Prediction | null;
    if (!pred) continue;
    const reasonText: string = pred.reason ?? "";
    const result = race.results as RaceResult | null;
    rows.push({
      race_id:         race.id,
      stadium:         race.stadium,
      race_no:         race.race_no,
      close_time:      race.close_time,
      pick:            pred.pick,
      confidence:      pred.confidence,
      decision:        pred.decision,
      is_watch:        isWatchCandidate(pred.decision, pred.confidence, reasonText),
      reason:          reasonText,
      gap:             (pred as any).gap ?? extractGap(reasonText),
      has_exhibition:  hasExhibitionData(reasonText),
      trifecta_result: result?.trifecta_result ?? null,
      payout:          result?.payout ?? null,
      popularity:      result?.popularity ?? null,
      prediction_hit:  result?.prediction_hit ?? null,
    });
  }

  rows.sort((a, b) => Number(b.confidence) - Number(a.confidence));
  return rows;
}

export async function getStats() {
  const client = db();

  // predictions + results を JOIN して全件取得（!inner で予想ありのレースのみ）
  const { data: races } = await client
    .from("races")
    .select("id, predictions!inner(*), results(*)");

  if (!races) return null;

  type Row = {
    confidence: number;
    decision: string;
    reason: string | null;
    gap: number | null;
    hit: boolean | null;
    payout: number;
    hasExhibition: boolean;
  };

  const rows: Row[] = [];
  for (const race of races as any[]) {
    const pred = race.predictions;
    const res  = race.results;
    if (!pred) continue;
    const hit = res?.prediction_hit ?? pred.is_hit ?? null;
    rows.push({
      confidence:   Number(pred.confidence) || 0,
      decision:     pred.decision || "skip",
      reason:       pred.reason || "",
      gap:          pred.gap ?? null,
      hit,
      payout:       res?.payout || 0,
      hasExhibition: !(pred.reason || "").includes("[展示未取得]"),
    });
  }

  const confirmed = rows.filter(r => r.hit !== null);
  if (confirmed.length === 0) return null;

  const hitRows      = confirmed.filter(r => r.hit);
  const total        = confirmed.length;
  const hitCount     = hitRows.length;
  // 投資対象は buy + candidate のみ（1点100円）
  const betRows      = confirmed.filter(r => r.decision === "buy" || r.decision === "candidate");
  const payoutTotal  = betRows.filter(r => r.hit).reduce((s, r) => s + r.payout, 0);
  const investTotal  = betRows.length * 100;
  const roi = investTotal > 0 ? ((payoutTotal / investTotal) * 100).toFixed(1) : "0.0";

  // ランク別
  const byDecision = (dec: string) => confirmed.filter(r => r.decision === dec);
  const watchRows  = confirmed.filter(r => r.decision === "skip" && (r.reason || "").includes("[watch]"));
  const skipRows   = confirmed.filter(r => r.decision === "skip" && !(r.reason || "").includes("[watch]"));

  const tierStat = (rows: Row[]) => ({
    count: rows.length,
    hit:   rows.filter(r => r.hit).length,
    rate:  rows.length ? ((rows.filter(r => r.hit).length / rows.length) * 100).toFixed(1) : "0.0",
    roi:   rows.length ? ((rows.filter(r => r.hit).reduce((s, r) => s + r.payout, 0) / (rows.length * 100)) * 100).toFixed(1) : "0.0",
  });

  // confidence 帯別
  const confBands = [
    { label: "≥70",   rows: confirmed.filter(r => r.confidence >= 70) },
    { label: "62-69", rows: confirmed.filter(r => r.confidence >= 62 && r.confidence < 70) },
    { label: "55-61", rows: confirmed.filter(r => r.confidence >= 55 && r.confidence < 62) },
    { label: "<55",   rows: confirmed.filter(r => r.confidence < 55) },
  ].map(b => ({ label: b.label, ...tierStat(b.rows) }));

  // 展示あり vs なし
  const withEx   = confirmed.filter(r => r.hasExhibition);
  const withoutEx = confirmed.filter(r => !r.hasExhibition);

  // 直近7日分の日別的中率（簡易: 全確定レースをまとめて返す — フロントでグループ不要）
  const sRows  = byDecision("buy");
  const aRows  = byDecision("candidate");

  return {
    total, hitCount,
    hitRate: total ? ((hitCount / total) * 100).toFixed(1) : "0.0",
    payoutTotal, investTotal, roi,
    // ランク別
    sCount: sRows.length, sHit: sRows.filter(r => r.hit).length,
    sRate: tierStat(sRows).rate, sRoi: tierStat(sRows).roi,
    aCount: aRows.length, aHit: aRows.filter(r => r.hit).length,
    aRate: tierStat(aRows).rate, aRoi: tierStat(aRows).roi,
    watchCount: watchRows.length, watchHit: watchRows.filter(r => r.hit).length,
    watchRate: tierStat(watchRows).rate,
    skipCount: skipRows.length, skipHit: skipRows.filter(r => r.hit).length,
    // confidence帯別
    confBands,
    // 展示あり vs なし
    withExCount: withEx.length,
    withExHit:   withEx.filter(r => r.hit).length,
    withExRate:  tierStat(withEx).rate,
    withExRoi:   tierStat(withEx).roi,
    withoutExCount: withoutEx.length,
    withoutExHit:   withoutEx.filter(r => r.hit).length,
    withoutExRate:  tierStat(withoutEx).rate,
    withoutExRoi:   tierStat(withoutEx).roi,
  };
}

// ─── /ops ページ用 ─────────────────────────────────────────────────────────

export type OpsData = {
  date: string;
  // 処理状況
  racesTotal: number;        // 今日の全レース数
  entriesTotal: number;      // entries 登録済みレース数
  predictionsTotal: number;  // predictions 登録済み (pre_race 処理済み)
  unevaluatedCount: number;  // まだ予想未作成のレース数
  exhibitionCount: number;   // 展示データ取得済み
  finishedCount: number;     // status = finished
  resultsTotal: number;
  // 判定状況
  buyCount: number;
  candidateCount: number;
  watchCount: number;   // skip だが検証候補 (is_watch)
  skipCount: number;
  maxConf: number;
  avgConf: string;
  // 的中状況
  verifiedTotal: number;
  hitCount: number;
  hitRate: string;
  payoutTotal: number;
  investTotal: number;
  roi: string;
  // 最終更新
  lastUpdatedAt: string | null;
};

export async function getOpsData(date: string): Promise<OpsData> {
  const client = db();

  // races + 埋め込みで predictions / results を一括取得
  const { data: races } = await client
    .from("races")
    .select(`
      id, status, updated_at,
      predictions(decision, confidence, reason, is_hit),
      results(prediction_hit, payout)
    `)
    .eq("race_date", date);

  const raceList = (races ?? []) as any[];
  const raceIds  = raceList.map((r) => r.id);

  // entries 件数を別途カウント (race_date カラムがないため race_id で絞る)
  let entriesTotal = 0;
  if (raceIds.length > 0) {
    const { count } = await client
      .from("entries")
      .select("id", { count: "exact", head: true })
      .in("race_id", raceIds);
    entriesTotal = count ?? 0;
  }

  // 各種集計
  let predictionsTotal = 0;
  let resultsTotal = 0;
  let exhibitionCount = 0;
  let finishedCount = 0;
  let buyCount = 0;
  let candidateCount = 0;
  let watchCount = 0;
  let skipCount = 0;
  let confSum = 0;
  let maxConf = 0;
  let verifiedTotal = 0;
  let hitCount = 0;
  let payoutTotal = 0;
  // 投資額は buy + candidate のみ (1点100円)
  let betVerifiedCount = 0;
  let lastUpdated: Date | null = null;

  for (const race of raceList) {
    if (race.status === "finished") finishedCount++;

    if (race.updated_at) {
      const d = new Date(race.updated_at);
      if (!lastUpdated || d > lastUpdated) lastUpdated = d;
    }

    const pred = race.predictions as any | null;
    if (pred) {
      predictionsTotal++;
      const conf = Number(pred.confidence);
      confSum += conf;
      if (conf > maxConf) maxConf = conf;

      if (pred.decision === "buy") {
        buyCount++;
      } else if (pred.decision === "candidate") {
        candidateCount++;
      } else {
        // skip: watch か純粋な skip かを判定
        if (isWatchCandidate(pred.decision, conf, pred.reason ?? "")) {
          watchCount++;
        } else {
          skipCount++;
        }
      }

      // 展示済み判定 (新旧両方のマーカーに対応)
      if (hasExhibitionData(pred.reason)) exhibitionCount++;

      if (pred.is_hit !== null && pred.is_hit !== undefined) {
        verifiedTotal++;
        if (pred.is_hit) hitCount++;
        // 投資対象 (buy + candidate) のみカウント
        if (pred.decision === "buy" || pred.decision === "candidate") {
          betVerifiedCount++;
        }
      }
    }

    const res = race.results as any | null;
    if (res) {
      resultsTotal++;
      // 払戻は buy + candidate が的中した場合のみ加算
      const predDec = (race.predictions as any)?.decision;
      if (res.prediction_hit && res.payout &&
          (predDec === "buy" || predDec === "candidate")) {
        payoutTotal += res.payout;
      }
    }
  }

  const avgConf = predictionsTotal > 0
    ? (confSum / predictionsTotal).toFixed(1)
    : "0.0";
  const hitRate = verifiedTotal > 0
    ? ((hitCount / verifiedTotal) * 100).toFixed(1)
    : "0.0";
  const investTotal = betVerifiedCount * 100;  // buy+candidate のみ
  const roi = investTotal > 0
    ? ((payoutTotal / investTotal) * 100).toFixed(1)
    : "0.0";

  return {
    date,
    racesTotal:       raceList.length,
    entriesTotal,
    predictionsTotal,
    unevaluatedCount: raceList.length - predictionsTotal,
    resultsTotal,
    exhibitionCount,
    finishedCount,
    buyCount,
    candidateCount,
    watchCount,
    skipCount,
    maxConf,
    avgConf,
    verifiedTotal,
    hitCount,
    hitRate,
    payoutTotal,
    investTotal,
    roi,
    lastUpdatedAt: lastUpdated
      ? lastUpdated.toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" })
      : null,
  };
}

// ─── /bet・/schedule 向けの候補取得関数 ─────────────────────────────────────

export type WatchCandidate = {
  race_id: string;
  stadium: string;
  race_no: number;
  close_time: string;
  pick: string;
  confidence: number;
  decision: "buy" | "candidate" | "skip";
  is_watch: boolean;
  gap: number | null;
  reason: string | null;
};

/**
 * 今日の投票候補 (buy / candidate) と検証候補 (watch) を取得する。
 * 将来の /bet・/schedule ページで使用予定。
 * skip (非watch) は除外。
 */
export async function getWatchCandidates(date: string): Promise<WatchCandidate[]> {
  const { data, error } = await db()
    .from("races")
    .select(`id, stadium, race_no, close_time, predictions(pick, confidence, decision, reason)`)
    .eq("race_date", date)
    .order("close_time", { ascending: true });

  if (error) throw error;

  const result: WatchCandidate[] = [];
  for (const race of (data ?? []) as any[]) {
    const pred = race.predictions as any | null;
    if (!pred) continue;

    const decision: string = pred.decision;
    const confidence: number = Number(pred.confidence);
    const reason: string = pred.reason ?? "";
    const isWatch = isWatchCandidate(decision, confidence, reason);

    // buy / candidate は常に含む。skip は watch のみ含む。
    if (decision === "skip" && !isWatch) continue;

    result.push({
      race_id:    race.id,
      stadium:    race.stadium,
      race_no:    race.race_no,
      close_time: race.close_time,
      pick:       pred.pick,
      confidence,
      decision:   decision as "buy" | "candidate" | "skip",
      is_watch:   isWatch,
      gap:        (pred as any).gap ?? extractGap(reason),
      reason:     reason || null,
    });
  }
  return result;
}

// ─── /schedule ページ用 ───────────────────────────────────────────────────────

export type ScheduleRow = {
  race_id: string;
  stadium: string;
  race_no: number;
  close_time: string;
  status: "scheduled" | "final" | "finished";
  // prediction (null = 未評価)
  pick: string | null;
  confidence: number | null;
  decision: "buy" | "candidate" | "skip" | null;
  is_watch: boolean;
  reason: string | null;
  gap: number | null;
  has_exhibition: boolean;
  // result
  trifecta_result: string | null;
  payout: number | null;
  popularity: number | null;
  prediction_hit: boolean | null;
};

export type ScheduleSummary = {
  totalRaces: number;
  evaluatedRaces: number;
  exhibitionRaces: number;
  buyCount: number;
  candidateCount: number;
  watchCount: number;
  skipCount: number;
  openCount: number;   // status = scheduled
  closedCount: number; // status = final | finished
};

/**
 * 今日の全レース + predictions + results を一括取得して ScheduleRow[] を返す。
 * 未評価レース (predictions なし) も含む。
 */
export async function getScheduleData(date: string): Promise<{
  rows: ScheduleRow[];
  summary: ScheduleSummary;
}> {
  const { data, error } = await db()
    .from("races")
    .select(`
      id, stadium, race_no, close_time, status,
      predictions(pick, confidence, decision, reason, is_hit, gap),
      results(trifecta_result, payout, popularity, prediction_hit)
    `)
    .eq("race_date", date)
    .order("close_time", { ascending: true });

  if (error) throw error;

  const rows: ScheduleRow[] = [];
  for (const race of (data ?? []) as any[]) {
    const pred   = race.predictions as any | null;
    const result = race.results     as any | null;

    const reasonText: string | null = pred?.reason ?? null;
    const conf: number | null       = pred ? Number(pred.confidence) : null;
    const gap                       = (pred as any)?.gap ?? (reasonText ? extractGap(reasonText) : null);
    const isWatch                   = pred
      ? isWatchCandidate(pred.decision, conf!, reasonText)
      : false;

    rows.push({
      race_id:         race.id,
      stadium:         race.stadium,
      race_no:         race.race_no,
      close_time:      race.close_time,
      status:          race.status,
      pick:            pred?.pick            ?? null,
      confidence:      conf,
      decision:        pred?.decision        ?? null,
      is_watch:        isWatch,
      reason:          reasonText,
      gap,
      has_exhibition:  hasExhibitionData(reasonText),
      trifecta_result: result?.trifecta_result ?? null,
      payout:          result?.payout          ?? null,
      popularity:      result?.popularity      ?? null,
      prediction_hit:  result?.prediction_hit  ?? null,
    });
  }

  const evaluated = rows.filter((r) => r.decision !== null);
  const summary: ScheduleSummary = {
    totalRaces:     rows.length,
    evaluatedRaces: evaluated.length,
    exhibitionRaces: rows.filter((r) => r.has_exhibition).length,
    buyCount:       rows.filter((r) => r.decision === "buy").length,
    candidateCount: rows.filter((r) => r.decision === "candidate").length,
    watchCount:     rows.filter((r) => r.is_watch).length,
    skipCount:      evaluated.filter((r) => r.decision === "skip" && !r.is_watch).length,
    openCount:      rows.filter((r) => r.status === "scheduled").length,
    closedCount:    rows.filter((r) => r.status !== "scheduled").length,
  };

  return { rows, summary };
}
