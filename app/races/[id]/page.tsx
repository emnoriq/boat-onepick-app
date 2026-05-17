import { notFound } from "next/navigation";
import { getRaceDetail } from "@/lib/supabase";
import ScoreTable from "@/components/ScoreTable";
import PredictionBadge from "@/components/PredictionBadge";
import { formatCloseTime, rankLabel, hitLabel, buildBoatraceUrl } from "@/lib/format";

export const dynamic = "force-dynamic";

type Props = { params: { id: string } };

const BOAT: { bg: string; text: string; ring: string }[] = [
  { bg: "bg-white",       text: "text-gray-700",  ring: "ring-1 ring-gray-200 shadow" },
  { bg: "bg-neutral-800", text: "text-white",      ring: "" },
  { bg: "bg-red-500",     text: "text-white",      ring: "" },
  { bg: "bg-sky-500",     text: "text-white",      ring: "" },
  { bg: "bg-yellow-400",  text: "text-gray-800",   ring: "" },
  { bg: "bg-green-500",   text: "text-white",      ring: "" },
];

function BoatBadge({ lane, size = "md" }: { lane: number; size?: "sm" | "md" | "lg" }) {
  const c = BOAT[lane - 1] ?? BOAT[0];
  const sz = size === "lg" ? "w-14 h-14 text-2xl" : size === "sm" ? "w-9 h-9 text-base" : "w-11 h-11 text-xl";
  return (
    <span className={`inline-flex items-center justify-center rounded-full font-black select-none ${sz} ${c.bg} ${c.text} ${c.ring}`}>
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

  const gradientStyle = prediction?.decision === "buy"
    ? "linear-gradient(135deg, #FF6B6B, #FF8E53)"
    : prediction?.decision === "candidate"
    ? "linear-gradient(135deg, #FF8E53, #FFBE0B)"
    : "linear-gradient(135deg, #e0e0e0, #c8c8c8)";

  return (
    <main className="max-w-lg mx-auto px-4 py-5">

      {/* 戻る */}
      <div className="flex gap-3 text-sm mb-4">
        <a href="/" className="text-orange-500 hover:underline font-medium">← ホーム</a>
        <a href="/schedule" className="text-gray-400 hover:text-gray-600">スケジュール</a>
      </div>

      {/* ── メイン予想カード ────────────────────────────────────── */}
      <div className="rounded-3xl overflow-hidden shadow-lg mb-5">

        {/* グラデーションヘッダー */}
        <div className="px-6 pt-6 pb-8 text-white" style={{ background: gradientStyle }}>
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-white/70 text-xs mb-0.5">{race.race_date}</p>
              <h1 className="text-2xl font-black drop-shadow-sm">
                {race.stadium} {race.race_no}R
              </h1>
              <p className="text-white/70 text-sm mt-0.5">締切 {formatCloseTime(race.close_time)}</p>
            </div>
            {prediction && (
              <div className="bg-white/25 rounded-2xl px-3 py-1.5 text-sm font-bold backdrop-blur-sm">
                {prediction.decision === "buy" ? "BUY" : prediction.decision === "candidate" ? "検討" : "見送り"}
              </div>
            )}
          </div>

          {/* 艇番 */}
          {prediction && (
            <div className="flex items-center justify-center gap-3 bg-white/20 rounded-2xl py-4 backdrop-blur-sm">
              {prediction.pick.split("-").map(Number).map((lane, i, arr) => (
                <div key={i} className="flex items-center gap-2">
                  <BoatBadge lane={lane} size="lg" />
                  {i < arr.length - 1 && <span className="text-white/50 font-bold text-lg">─</span>}
                </div>
              ))}
              <span className="text-white/60 text-xs ml-1">三連複</span>
            </div>
          )}
        </div>

        {/* 白いコンテンツ部分 */}
        <div className="bg-white px-6 pt-5 pb-5">
          {prediction && (
            <>
              {/* 信頼度 */}
              <div className="mb-4">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm font-semibold text-gray-500">信頼度</span>
                  <span className="text-xl font-black text-orange-500">
                    {Number(prediction.confidence).toFixed(1)}点
                  </span>
                </div>
                <div className="h-2.5 rounded-full overflow-hidden" style={{ backgroundColor: "#FFF0E8" }}>
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.min(100, (Number(prediction.confidence) - 50) / 35 * 100)}%`,
                      background: gradientStyle,
                    }}
                  />
                </div>
              </div>

              {/* EV + Kelly */}
              {(prediction.best_ev != null || (prediction.kelly_fraction && prediction.kelly_fraction > 0)) && (
                <div className="flex flex-wrap gap-2 mb-4">
                  {prediction.best_ev != null && (
                    <div className={`flex items-center gap-1.5 px-3 py-2 rounded-2xl text-sm font-bold ${
                      prediction.best_ev > 0 ? "bg-rose-50 text-rose-500" : "bg-gray-50 text-gray-400"
                    }`}>
                      期待値 {prediction.best_ev >= 0 ? "+" : ""}{(prediction.best_ev * 100).toFixed(1)}%
                    </div>
                  )}
                  {prediction.kelly_fraction != null && prediction.kelly_fraction > 0 && (
                    <div className="bg-amber-50 rounded-2xl px-3 py-2">
                      <div className="text-xs text-amber-400 font-semibold">Kelly推奨</div>
                      <div className="text-sm font-black text-amber-600">
                        {(prediction.kelly_fraction * 100).toFixed(1)}%
                        <span className="text-xs font-normal text-amber-400 ml-1.5">
                          ¥1万→¥{(Math.round(10000 * prediction.kelly_fraction / 100) * 100).toLocaleString()}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* 理由 */}
              {prediction.reason && (
                <div className="mb-4">
                  <p className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">分析理由</p>
                  <ul className="space-y-1.5">
                    {prediction.reason.split("\n").filter(Boolean).map((r, i) => (
                      <li key={i} className="flex gap-2 text-sm text-gray-600">
                        <span className="text-orange-300 shrink-0 mt-0.5">•</span>
                        <span>{r}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* 結果 */}
              {result && (
                <div className={`flex items-center gap-3 pt-4 border-t border-orange-50 ${
                  result.prediction_hit ? "text-rose-500" : "text-gray-400"
                }`}>
                  <span className="font-bold text-lg">{result.prediction_hit ? "🎉 的中！" : hitLabel(result.prediction_hit)}</span>
                  {result.trifecta_result && (
                    <span className="text-sm text-gray-400">
                      {result.trifecta_result}
                      {result.payout && ` · ¥${result.payout.toLocaleString()}`}
                    </span>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* 投票ボタン */}
        {isBet && (
          <a
            href={boatraceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 py-4 text-sm font-bold text-white transition-opacity hover:opacity-90"
            style={{ background: gradientStyle }}
          >
            boatrace.jp で出走表を確認 →
          </a>
        )}
      </div>

      {/* ── 各艇スコア ────────────────────────────────────────── */}
      <p className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2 px-1">各艇スコア</p>
      <div className="bg-white rounded-3xl border border-orange-50 shadow-sm overflow-hidden">
        <ScoreTable entries={entries} topLanes={topLanes} />
      </div>
    </main>
  );
}
