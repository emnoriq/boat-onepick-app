import { notFound } from "next/navigation";
import { getRaceDetail } from "@/lib/supabase";
import ScoreTable from "@/components/ScoreTable";
import PredictionBadge from "@/components/PredictionBadge";
import { formatCloseTime, rankLabel, rankColor, hitLabel } from "@/lib/format";

export const dynamic = "force-dynamic";

type Props = { params: { id: string } };

export default async function RaceDetailPage({ params }: Props) {
  const detail = await getRaceDetail(params.id);
  if (!detail) notFound();

  const { race, entries, prediction, result } = detail;
  const topLanes = prediction?.pick.split("-").map(Number) ?? [];

  return (
    <main className="max-w-lg mx-auto px-4 py-6">
      <div className="flex gap-4 text-sm mb-4">
        <a href="/schedule" className="text-blue-500 hover:underline">← スケジュール</a>
        <a href="/"         className="text-gray-400 hover:underline">ホーム</a>
      </div>

      <div className="flex items-center justify-between mb-1">
        <h1 className="text-xl font-bold">
          {race.stadium} {race.race_no}R
        </h1>
        {prediction && <PredictionBadge decision={prediction.decision} />}
      </div>
      <p className="text-sm text-gray-400 mb-4">締切 {formatCloseTime(race.close_time)}</p>

      {prediction && (
        <div className="bg-white border rounded-xl p-4 mb-4">
          <div className="flex items-center gap-4 mb-3">
            <span className={`text-4xl font-black ${rankColor(prediction.confidence)}`}>
              {rankLabel(prediction.confidence)}
            </span>
            <div>
              <div className="text-2xl font-bold tracking-widest">
                三連複 {prediction.pick}
              </div>
              <div className="text-sm text-gray-500">
                信頼度 {prediction.confidence}点
              </div>
            </div>
          </div>

          {/* EV + Kelly 表示 */}
          {(prediction.best_ev != null || prediction.kelly_fraction != null) && (
            <div className="flex flex-wrap gap-2 mb-3">
              {prediction.best_ev != null && (
                <div className={`inline-flex items-center gap-1 px-3 py-1 rounded-lg text-sm font-bold ${
                  prediction.best_ev > 0.15 ? "bg-green-100 text-green-700" :
                  prediction.best_ev > 0    ? "bg-emerald-50 text-emerald-600" :
                                              "bg-gray-100 text-gray-400"
                }`}>
                  期待値 {prediction.best_ev >= 0 ? "+" : ""}{(prediction.best_ev * 100).toFixed(1)}%
                </div>
              )}
              {prediction.kelly_fraction != null && prediction.kelly_fraction > 0 && (
                <div className="bg-purple-50 border border-purple-200 rounded-lg px-3 py-1">
                  <div className="text-xs text-purple-500 font-semibold">Kelly推奨賭け率</div>
                  <div className="text-sm font-bold text-purple-700">
                    {(prediction.kelly_fraction * 100).toFixed(1)}%
                    <span className="text-xs font-normal text-purple-500 ml-2">
                      ¥1万→¥{Math.round(10000 * prediction.kelly_fraction / 100) * 100}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}

          {prediction.reason && (
            <ul className="text-sm text-gray-700 list-disc list-inside space-y-1">
              {prediction.reason.split("\n").filter(Boolean).map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          )}

          {result && (
            <div className="mt-3 pt-3 border-t flex items-center gap-3">
              <span className={`font-bold ${result.prediction_hit ? "text-green-600" : "text-gray-400"}`}>
                {hitLabel(result.prediction_hit)}
              </span>
              {result.trifecta_result && (
                <span className="text-sm text-gray-600">
                  結果: {result.trifecta_result}
                  {result.payout && ` (${result.payout.toLocaleString()}円)`}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      <h2 className="text-sm font-semibold text-gray-500 mb-2">各艇スコア</h2>
      <div className="bg-white border rounded-xl overflow-hidden">
        <ScoreTable entries={entries} topLanes={topLanes} />
      </div>
    </main>
  );
}
