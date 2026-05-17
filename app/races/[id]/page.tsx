import { notFound } from "next/navigation";
import { getRaceDetail } from "@/lib/supabase";
import ScoreTable from "@/components/ScoreTable";
import PredictionBadge from "@/components/PredictionBadge";
import { formatCloseTime, rankLabel, rankColor, hitLabel, buildBoatraceUrl } from "@/lib/format";

export const dynamic = "force-dynamic";

type Props = { params: { id: string } };

// 艇番カラー
const BOAT: { bg: string; text: string; ring: string }[] = [
  { bg: "bg-white",       text: "text-gray-800", ring: "ring-1 ring-gray-200 shadow" },
  { bg: "bg-neutral-900", text: "text-white",     ring: "" },
  { bg: "bg-red-500",     text: "text-white",     ring: "" },
  { bg: "bg-sky-500",     text: "text-white",     ring: "" },
  { bg: "bg-yellow-400",  text: "text-gray-900",  ring: "" },
  { bg: "bg-green-500",   text: "text-white",     ring: "" },
];

function BoatBadge({ lane }: { lane: number }) {
  const c = BOAT[lane - 1] ?? BOAT[0];
  return (
    <span className={`inline-flex items-center justify-center w-12 h-12 rounded-full text-2xl font-black ${c.bg} ${c.text} ${c.ring}`}>
      {lane}
    </span>
  );
}

export default async function RaceDetailPage({ params }: Props) {
  const detail = await getRaceDetail(params.id);
  if (!detail) notFound();

  const { race, entries, prediction, result } = detail;
  const topLanes = prediction?.pick.split("-").map(Number) ?? [];
  const boatraceUrl = buildBoatraceUrl(race.stadium, race.race_date, race.race_no);
  const isBet = prediction?.decision === "buy" || prediction?.decision === "candidate";

  return (
    <main className="max-w-lg mx-auto px-4 py-5">
      {/* ── 戻るリンク ─────────────────────────────────────────── */}
      <div className="flex gap-3 text-sm mb-4">
        <a href="/" className="text-sky-500 hover:underline">← ホーム</a>
        <a href="/schedule" className="text-gray-400 hover:text-gray-600">スケジュール</a>
      </div>

      {/* ── レースヘッダー ────────────────────────────────────── */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 mb-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-black text-gray-900">
              {race.stadium} {race.race_no}R
            </h1>
            <p className="text-sm text-gray-400 mt-0.5">締切 {formatCloseTime(race.close_time)}</p>
          </div>
          {prediction && <PredictionBadge decision={prediction.decision} />}
        </div>

        {prediction && (
          <>
            {/* 信頼度ランク + ピック */}
            <div className="flex items-center gap-4 mb-4">
              <div className={`text-5xl font-black ${rankColor(prediction.confidence)}`}>
                {rankLabel(prediction.confidence)}
              </div>
              <div>
                <div className="flex items-center gap-2 mb-1">
                  {prediction.pick.split("-").map(Number).map((lane, i, arr) => (
                    <div key={i} className="flex items-center gap-2">
                      <BoatBadge lane={lane} />
                      {i < arr.length - 1 && <span className="text-gray-200 font-bold">─</span>}
                    </div>
                  ))}
                </div>
                <p className="text-xs text-gray-400">
                  信頼度 {prediction.confidence}点
                  {prediction.gap != null && ` · 差 ${Number(prediction.gap).toFixed(1)}`}
                </p>
              </div>
            </div>

            {/* EV + Kelly */}
            {(prediction.best_ev != null || (prediction.kelly_fraction && prediction.kelly_fraction > 0)) && (
              <div className="flex flex-wrap gap-2 mb-4">
                {prediction.best_ev != null && (
                  <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-sm font-bold ${
                    prediction.best_ev > 0.15 ? "bg-green-100 text-green-700" :
                    prediction.best_ev > 0    ? "bg-emerald-50 text-emerald-600" :
                                                "bg-gray-100 text-gray-400"
                  }`}>
                    <span>期待値</span>
                    <span>{prediction.best_ev >= 0 ? "+" : ""}{(prediction.best_ev * 100).toFixed(1)}%</span>
                  </div>
                )}
                {prediction.kelly_fraction != null && prediction.kelly_fraction > 0 && (
                  <div className="bg-violet-50 border border-violet-100 rounded-xl px-3 py-1.5">
                    <span className="text-xs text-violet-400 font-medium block">Kelly推奨</span>
                    <span className="text-sm font-black text-violet-700">
                      {(prediction.kelly_fraction * 100).toFixed(1)}%
                    </span>
                    <span className="text-xs text-violet-400 ml-2">
                      ¥1万→¥{(Math.round(10000 * prediction.kelly_fraction / 100) * 100).toLocaleString()}
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* 理由 */}
            {prediction.reason && (
              <ul className="text-sm text-gray-600 space-y-1 mb-4">
                {prediction.reason.split("\n").filter(Boolean).map((r, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-gray-300 shrink-0 mt-0.5">•</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            )}

            {/* 結果 */}
            {result && (
              <div className={`flex items-center gap-3 pt-3 border-t border-gray-50 ${
                result.prediction_hit ? "text-emerald-600" : "text-gray-400"
              }`}>
                <span className="font-bold">{result.prediction_hit ? "🎉 的中" : hitLabel(result.prediction_hit)}</span>
                {result.trifecta_result && (
                  <span className="text-sm text-gray-500">
                    {result.trifecta_result}
                    {result.payout && ` · ¥${result.payout.toLocaleString()}`}
                  </span>
                )}
              </div>
            )}
          </>
        )}

        {/* boatrace.jp リンク */}
        {isBet && (
          <a
            href={boatraceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className={`mt-4 flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-bold transition-colors ${
              prediction?.decision === "buy"
                ? "bg-emerald-500 hover:bg-emerald-600 text-white"
                : "bg-amber-400 hover:bg-amber-500 text-white"
            }`}
          >
            boatrace.jp で出走表を確認 →
          </a>
        )}
      </div>

      {/* ── 各艇スコア ────────────────────────────────────────── */}
      <h2 className="text-sm font-bold text-gray-500 mb-2 px-1">各艇スコア</h2>
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        <ScoreTable entries={entries} topLanes={topLanes} />
      </div>
    </main>
  );
}
