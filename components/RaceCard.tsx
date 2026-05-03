import Link from "next/link";
import { RaceWithPrediction } from "@/lib/supabase";
import { formatCloseTime, decisionLabel, rankLabel, rankColor, hitLabel } from "@/lib/format";
import PredictionBadge from "./PredictionBadge";

type Props = { race: RaceWithPrediction };

export default function RaceCard({ race }: Props) {
  const prediction = race.predictions ?? null;
  const result = race.results ?? null;
  if (!prediction) return null;

  const rank = rankLabel(prediction.confidence);
  const colorClass = rankColor(prediction.confidence);

  return (
    <Link href={`/races/${race.id}`}>
      <div className="border rounded-xl p-4 mb-3 hover:shadow-md transition-shadow bg-white cursor-pointer">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-gray-500">
            {race.stadium} {race.race_no}R &nbsp;締切 {formatCloseTime(race.close_time)}
          </span>
          <PredictionBadge decision={prediction.decision} />
        </div>

        <div className="flex items-center gap-4">
          <span className={`text-3xl font-black ${colorClass}`}>{rank}</span>
          <div>
            <div className="text-lg font-bold tracking-widest">
              三連複 {prediction.pick}
            </div>
            <div className="text-sm text-gray-500">
              信頼度 {prediction.confidence}点
            </div>
          </div>
          {result && (
            <span className={`ml-auto text-sm font-semibold ${
              result.prediction_hit ? "text-green-600" : "text-gray-400"
            }`}>
              {hitLabel(result.prediction_hit)}
            </span>
          )}
        </div>

        {prediction.reason && (
          <ul className="mt-2 text-xs text-gray-600 list-disc list-inside space-y-0.5">
            {prediction.reason.split("\n").filter(Boolean).slice(0, 2).map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        )}
      </div>
    </Link>
  );
}
