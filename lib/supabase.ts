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
  entry_score: number | null;
};

export type Prediction = {
  id: string;
  race_id: string;
  pick: string;
  confidence: number;
  decision: "buy" | "candidate" | "skip";
  reason: string | null;
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
  reason: string | null;
  gap: number | null;
  has_exhibition: boolean;
  // 結果
  trifecta_result: string | null;
  payout: number | null;
  popularity: number | null;
  prediction_hit: boolean | null;
};

export async function getDebugPredictions(date: string): Promise<DebugRow[]> {
  // getTodayPredictions と同じ races 起点クエリを使う (実績ある構造)
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
    const gapMatch = reasonText.match(/gap=([\d.]+)/);
    const result = race.results as RaceResult | null;
    rows.push({
      race_id:        race.id,
      stadium:        race.stadium,
      race_no:        race.race_no,
      close_time:     race.close_time,
      pick:           pred.pick,
      confidence:     pred.confidence,
      decision:       pred.decision,
      reason:         reasonText,
      gap:            gapMatch ? parseFloat(gapMatch[1]) : null,
      has_exhibition: !reasonText.includes("朝スキャン暫定"),
      trifecta_result: result?.trifecta_result ?? null,
      payout:          result?.payout ?? null,
      popularity:      result?.popularity ?? null,
      prediction_hit:  result?.prediction_hit ?? null,
    });
  }

  rows.sort((a, b) => Number(b.confidence) - Number(a.confidence));
  return rows.slice(0, 50);
}

export async function getStats() {
  // predictions.is_hit が確定したレースを対象に集計
  const { data: preds } = await db()
    .from("predictions")
    .select("decision, is_hit, confidence, race_id")
    .not("is_hit", "is", null);

  if (!preds) return null;

  // 的中レースの払戻金合計 (ROI 計算用)
  const hitRaceIds = preds
    .filter((d) => d.is_hit)
    .map((d) => d.race_id);

  let payoutTotal = 0;
  if (hitRaceIds.length > 0) {
    const { data: resultRows } = await db()
      .from("results")
      .select("payout")
      .in("race_id", hitRaceIds);
    payoutTotal = (resultRows ?? []).reduce(
      (sum, r) => sum + (r.payout ?? 0), 0
    );
  }

  const total = preds.length;
  const hit   = preds.filter((d) => d.is_hit).length;
  const sRank = preds.filter((d) => d.decision === "buy");
  const aRank = preds.filter((d) => d.decision === "candidate");
  const sHit  = sRank.filter((d) => d.is_hit).length;
  const aHit  = aRank.filter((d) => d.is_hit).length;

  const investTotal = total * 100;                        // 1点100円
  const roi = investTotal > 0
    ? ((payoutTotal / investTotal) * 100).toFixed(1)
    : "0.0";

  return {
    total,
    hitCount: hit,
    hitRate: total ? ((hit / total) * 100).toFixed(1) : "0.0",
    sCount: sRank.length,
    sHit,
    aCount: aRank.length,
    aHit,
    payoutTotal,
    investTotal,
    roi,
  };
}

// ─── /ops ページ用 ─────────────────────────────────────────────────────────

export type OpsData = {
  date: string;
  // 処理状況
  racesTotal: number;
  entriesTotal: number;
  predictionsTotal: number;
  resultsTotal: number;
  exhibitionCount: number;  // 展示済みレース数 (pre_race 取得済み)
  finishedCount: number;    // status = finished
  // 判定状況
  buyCount: number;
  candidateCount: number;
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
  let skipCount = 0;
  let confSum = 0;
  let maxConf = 0;
  let verifiedTotal = 0;
  let hitCount = 0;
  let payoutTotal = 0;
  let lastUpdated: Date | null = null;

  for (const race of raceList) {
    if (race.status === "finished") finishedCount++;

    // updated_at の最大値
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
      if (pred.decision === "buy") buyCount++;
      else if (pred.decision === "candidate") candidateCount++;
      else skipCount++;
      // 展示済み = reason に "朝スキャン暫定" がない
      if (pred.reason && !pred.reason.includes("朝スキャン暫定")) exhibitionCount++;
      if (pred.is_hit !== null && pred.is_hit !== undefined) {
        verifiedTotal++;
        if (pred.is_hit) hitCount++;
      }
    }

    const res = race.results as any | null;
    if (res) {
      resultsTotal++;
      if (res.prediction_hit && res.payout) payoutTotal += res.payout;
    }
  }

  const avgConf = predictionsTotal > 0
    ? (confSum / predictionsTotal).toFixed(1)
    : "0.0";
  const hitRate = verifiedTotal > 0
    ? ((hitCount / verifiedTotal) * 100).toFixed(1)
    : "0.0";
  const investTotal = verifiedTotal * 100;
  const roi = investTotal > 0
    ? ((payoutTotal / investTotal) * 100).toFixed(1)
    : "0.0";

  return {
    date,
    racesTotal:  raceList.length,
    entriesTotal,
    predictionsTotal,
    resultsTotal,
    exhibitionCount,
    finishedCount,
    buyCount,
    candidateCount,
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
