import Link from "next/link";
import { RaceWithPrediction } from "@/lib/supabase";
import { formatCloseTime, buildBoatraceUrl } from "@/lib/format";

// ── 艇番カラー（ボートレース公式色） ─────────────────────────────────────
const BOAT: { bg: string; text: string; ring: string }[] = [
  { bg: "bg-white",       text: "text-gray-700",  ring: "ring-1 ring-gray-200 shadow-sm" },
  { bg: "bg-neutral-800", text: "text-white",      ring: "" },
  { bg: "bg-red-500",     text: "text-white",      ring: "" },
  { bg: "bg-sky-500",     text: "text-white",      ring: "" },
  { bg: "bg-yellow-400",  text: "text-gray-800",   ring: "" },
  { bg: "bg-green-500",   text: "text-white",      ring: "" },
];

function BoatBadge({ lane }: { lane: number }) {
  const c = BOAT[lane - 1] ?? BOAT[0];
  return (
    <span className={`inline-flex items-center justify-center w-11 h-11 rounded-full text-xl font-black select-none ${c.bg} ${c.text} ${c.ring}`}>
      {lane}
    </span>
  );
}

// ── decision ごとの配色（暖色グラデーション） ────────────────────────────
const DEC = {
  buy: {
    card:     "bg-white border border-rose-100",
    accent:   "bg-gradient-to-r from-rose-500 to-orange-400",
    labelCls: "bg-gradient-to-r from-rose-500 to-orange-400 text-white",
    label:    "BUY",
    bar:      "bg-gradient-to-r from-rose-400 to-orange-400",
    btn:      "bg-gradient-to-r from-rose-500 to-orange-400 text-white hover:opacity-90",
    confText: "text-rose-500",
  },
  candidate: {
    card:     "bg-white border border-orange-100",
    accent:   "bg-gradient-to-r from-orange-400 to-amber-400",
    labelCls: "bg-gradient-to-r from-orange-400 to-amber-400 text-white",
    label:    "検討",
    bar:      "bg-gradient-to-r from-orange-400 to-amber-400",
    btn:      "bg-gradient-to-r from-orange-400 to-amber-400 text-white hover:opacity-90",
    confText: "text-orange-500",
  },
  skip: {
    card:     "bg-white/60 border border-gray-100",
    accent:   "bg-gray-200",
    labelCls: "bg-gray-100 text-gray-400",
    label:    "見送り",
    bar:      "bg-gray-200",
    btn:      "",
    confText: "text-gray-400",
  },
};

type Props = {
  race: RaceWithPrediction;
  rank?: number;
};

export default function RaceCard({ race, rank }: Props) {
  const pred = race.predictions ?? null;
  const res  = race.results    ?? null;
  if (!pred) return null;

  const dec   = DEC[pred.decision as keyof typeof DEC] ?? DEC.skip;
  const isBet = pred.decision === "buy" || pred.decision === "candidate";
  const url   = buildBoatraceUrl(race.stadium, race.race_date, race.race_no);
  const picks = pred.pick.split("-").map(Number);

  const confPct = Math.min(100, Math.max(0, (Number(pred.confidence) - 50) / 35 * 100));

  const ev = pred.best_ev
    ?? (() => { const m = pred.reason?.match(/EV=([+-]?[\d.]+)/); return m ? parseFloat(m[1]) : null; })();
  const kelly = pred.kelly_fraction;
  const firstReason = pred.reason?.split("\n").filter(Boolean)[0] ?? null;

  return (
    <div className={`rounded-3xl shadow-sm mb-4 overflow-hidden ${dec.card}`}>

      {/* ── カード本体 ───────────────────────────────────────────── */}
      <Link href={`/races/${race.id}`} className="block px-5 pt-5 pb-4">

        {/* 上段: 場名・R番号・締切・バッジ */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            {rank != null && (
              <span className={`text-xs font-black w-5 shrink-0 ${
                rank === 1 ? "text-yellow-500" : rank === 2 ? "text-gray-400" : rank === 3 ? "text-orange-400" : "text-gray-300"
              }`}>#{rank}</span>
            )}
            <span className="font-black text-gray-800 text-base">{race.stadium}</span>
            <span className="font-semibold text-gray-400">{race.race_no}R</span>
            <span className="text-xs text-gray-300">·</span>
            <span className="text-xs text-gray-400">締切 {formatCloseTime(race.close_time)}</span>
          </div>
          <span className={`text-xs font-bold px-3 py-1 rounded-full shrink-0 ml-2 ${dec.labelCls}`}>
            {dec.label}
          </span>
        </div>

        {/* 艇番サークル */}
        <div className="flex items-center justify-center gap-3 py-3 mb-4">
          {picks.map((lane, i) => (
            <div key={i} className="flex items-center gap-2">
              <BoatBadge lane={lane} />
              {i < picks.length - 1 && (
                <span className="text-gray-200 font-bold text-lg">─</span>
              )}
            </div>
          ))}
          <span className="text-xs text-gray-300 ml-2">三連複</span>
        </div>

        {/* 信頼度バー */}
        <div className="mb-3">
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-xs text-gray-400">信頼度</span>
            <span className={`text-sm font-black tabular-nums ${dec.confText}`}>
              {Number(pred.confidence).toFixed(1)}
            </span>
          </div>
          <div className="h-2 rounded-full overflow-hidden" style={{ backgroundColor: "#F5E6E0" }}>
            <div className={`h-full rounded-full transition-all ${dec.bar}`} style={{ width: `${confPct}%` }} />
          </div>
        </div>

        {/* EV / Kelly / gap ピル */}
        {(ev !== null || (kelly && kelly > 0) || pred.gap != null) && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {ev !== null && (
              <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${
                ev > 0.15 ? "bg-rose-100 text-rose-600" :
                ev > 0    ? "bg-orange-50 text-orange-500" :
                            "bg-gray-100 text-gray-400"
              }`}>
                EV {ev >= 0 ? "+" : ""}{(ev * 100).toFixed(0)}%
              </span>
            )}
            {kelly && kelly > 0 && (
              <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-amber-50 text-amber-600">
                Kelly {(kelly * 100).toFixed(1)}%
              </span>
            )}
            {pred.gap != null && (
              <span className="text-xs px-2.5 py-1 rounded-full bg-gray-50 text-gray-400">
                差 {Number(pred.gap).toFixed(1)}
              </span>
            )}
          </div>
        )}

        {/* 理由 */}
        {firstReason && (
          <p className="text-xs text-gray-400 line-clamp-1 leading-relaxed">{firstReason}</p>
        )}

        {/* 結果 */}
        {res && (
          <div className={`mt-3 pt-3 border-t border-orange-50 flex items-center gap-2 text-sm font-bold ${
            res.prediction_hit ? "text-rose-500" : "text-gray-300"
          }`}>
            {res.prediction_hit ? "🎉 的中" : "✗ 不的中"}
            {res.trifecta_result && (
              <span className="text-xs font-normal text-gray-400">
                {res.trifecta_result}
                {res.payout && ` · ¥${res.payout.toLocaleString()}`}
              </span>
            )}
          </div>
        )}
      </Link>

      {/* ── 投票ボタン ──────────────────────────────────────────── */}
      {isBet && (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className={`flex items-center justify-center gap-2 py-3.5 text-sm font-bold transition-opacity ${dec.btn}`}
        >
          <span>boatrace.jp で出走表を確認</span>
          <span>→</span>
        </a>
      )}
    </div>
  );
}
