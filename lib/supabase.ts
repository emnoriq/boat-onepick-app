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
  const { data } = await db()
    .from("predictions")
    .select("decision, is_hit, confidence")
    .not("is_hit", "is", null);

  if (!data) return null;

  const total = data.length;
  const hit   = data.filter((d) => d.is_hit).length;
  // decision ベースで S(buy) / A(candidate) を区別
  const sRank = data.filter((d) => d.decision === "buy");
  const aRank = data.filter((d) => d.decision === "candidate");

  const sHit = sRank.filter((d) => d.is_hit).length;
  const aHit = aRank.filter((d) => d.is_hit).length;

  return {
    total,
    hitCount: hit,
    hitRate: total ? ((hit / total) * 100).toFixed(1) : "0.0",
    sCount: sRank.length,
    sHit,
    aCount: aRank.length,
    aHit,
  };
}
