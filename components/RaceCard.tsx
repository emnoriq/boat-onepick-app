import Link from "next/link";
import { RaceWithPrediction } from "@/lib/supabase";
import { formatCloseTime, rankColor, hitLabel } from "@/lib/format";
import PredictionBadge from "./PredictionBadge";

type Props = {
  race: RaceWithPrediction;
  /** 信頼度ランキングの順位（1始まり）。省略時は非表示 */
  rank?: number;
};

export default function RaceCard({ race, rank }: Props) {
  const prediction = race.predictions ?? null;
  const result = race.results ?? null;
  if (!prediction) return null;

  const confColor = rankColor(prediction.confidence);

  return (
    <Link href={`/races/${race.id}`}>
      <div className="border rounded-xl p-4 mb-3 hover:shadow-md transition-shadow bg-white cursor-pointer">

        {/* ヘッダー行 */}
        <div className="flex items-center gap-2 mb-2">
          {rank != null && (
            <span className={`text-lg font-black w-7 shrink-0 ${
              rank === 1 ? "text-yellow-500" :
              rank === 2 ? "text-gray-400" :
              rank === 3 ? "text-amber-700" :
              "text-gray-300"
            }`}>
              #{rank}
            </span>
          )}
          <span className="text-sm text-gray-500 flex-1">
            {race.stadium} {race.race_no}R &nbsp;締切 {formatCloseTime(race.close_time)}
          </span>
          <PredictionBadge decision={prediction.decision} />
        </div>

        {/* メイン：pick + confidence + EV */}
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <div className="text-lg font-bold tracking-widest">
              三連複 {prediction.pick}
            </div>
            <div className={`text-sm font-semibold ${confColor}`}>
              信頼度 {Number(prediction.confidence).toFixed(1)}点
              {prediction.gap != null && (
                <span className="text-gray-400 font-normal ml-2">gap {Number(prediction.gap).toFixed(1)}</span>
              )}
            </div>
            {/* EV バッジ */}
            {(() => {
              const evMatch = prediction.reason?.match(/EV=([+-][\d.]+)/);
              const ev = evMatch ? parseFloat(evMatch[1]) : null;
              if (ev === null) return null;
              return (
                <div className={`inline-flex items-center gap-1 mt-1 px-2 py-0.5 rounded text-xs font-bold ${
                  ev > 0.15 ? "bg-green-100 text-green-700" :
                  ev > 0    ? "bg-emerald-50 text-emerald-600" :
                              "bg-gray-100 text-gray-400"
                }`}>
                  EV {ev >= 0 ? "+" : ""}{(ev * 100).toFixed(0)}%
                  {ev > 0 && <span className="font-normal">← 期待値プラス</span>}
                </div>
              );
            })()}
          </div>
          {result && (
            <span className={`text-sm font-semibold shrink-0 ${
              result.prediction_hit ? "text-green-600" : "text-gray-400"
            }`}>
              {hitLabel(result.prediction_hit)}
              {result.prediction_hit && result.payout != null && (
                <span className="ml-1 text-xs">¥{result.payout.toLocaleString()}</span>
              )}
            </span>
          )}
        </div>

        {/* reason（最初の2行） */}
        {prediction.reason && (
          <ul className="mt-2 text-xs text-gray-500 list-disc list-inside space-y-0.5">
            {prediction.reason.split("\n").filter(Boolean).slice(0, 2).map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        )}
      </div>
    </Link>
  );
}
