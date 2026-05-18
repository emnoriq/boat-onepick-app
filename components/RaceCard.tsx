import Link from "next/link";
import { RaceWithPrediction } from "@/lib/supabase";
import { formatCloseTime, buildBoatraceUrl } from "@/lib/format";

// ── 艇番カラー（ボートレース公式色） ─────────────────────────────────────
const BOAT: { bg: string; text: string; ring: string }[] = [
  { bg: "bg-white",       text: "text-gray-700",  ring: "ring-1 ring-gray-200" },
  { bg: "bg-neutral-800", text: "text-white",      ring: "" },
  { bg: "bg-red-500",     text: "text-white",      ring: "" },
  { bg: "bg-sky-500",     text: "text-white",      ring: "" },
  { bg: "bg-yellow-400",  text: "text-gray-800",   ring: "" },
  { bg: "bg-green-500",   text: "text-white",      ring: "" },
];

function BoatBadge({ lane, size = "md" }: { lane: number; size?: "md" | "lg" }) {
  const c = BOAT[lane - 1] ?? BOAT[0];
  const sz = size === "lg" ? "w-12 h-12 text-xl" : "w-10 h-10 text-lg";
  return (
    <span className={`inline-flex items-center justify-center rounded-full font-black select-none ${sz} ${c.bg} ${c.text} ${c.ring}`}
      style={{ fontFamily: "var(--font-inter), sans-serif" }}>
      {lane}
    </span>
  );
}

// ── decision ごとの配色 ───────────────────────────────────────────────────
const DEC = {
  buy: {
    border:   "border-l-4 border-l-rose-400",
    badge:    "text-white text-xs font-bold px-2.5 py-0.5 rounded-full",
    badgeBg:  "linear-gradient(to right, #FF6B6B, #FF8E53)",
    label:    "BUY",
    bar:      "from-rose-400 to-orange-400",
    confText: "text-rose-500",
    btnBg:    "linear-gradient(to right, #FF6B6B, #FF8E53)",
    show:     true,
  },
  candidate: {
    border:   "border-l-4 border-l-orange-300",
    badge:    "text-white text-xs font-bold px-2.5 py-0.5 rounded-full",
    badgeBg:  "linear-gradient(to right, #FF8E53, #FFBE0B)",
    label:    "検討",
    bar:      "from-orange-400 to-amber-300",
    confText: "text-orange-500",
    btnBg:    "linear-gradient(to right, #FF8E53, #FFBE0B)",
    show:     true,
  },
  skip: {
    border:   "border-l-4 border-l-gray-100",
    badge:    "text-gray-400 text-xs font-medium px-2.5 py-0.5 rounded-full bg-gray-100",
    badgeBg:  null,
    label:    "見送り",
    bar:      "from-gray-200 to-gray-200",
    confText: "text-gray-400",
    btnBg:    null,
    show:     false,
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
  const firstReason = pred.reason?.split("\n").filter(l =>
    l && !l.startsWith("[") && !l.startsWith("朝") && l.length > 4
  )[0] ?? null;

  return (
    <div className={`bg-white rounded-2xl mb-3 overflow-hidden shadow-[0_2px_16px_rgba(0,0,0,0.06)] ${dec.border}`}>

      {/* ── カード本体 ───────────────────────────────────────────── */}
      <Link href={`/races/${race.id}`} className="block px-4 pt-4 pb-3">

        {/* 上段: 場名・R・締切・バッジ */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-1.5">
            {rank != null && (
              <span className={`text-xs font-black mr-0.5 ${
                rank === 1 ? "text-amber-400" : rank === 2 ? "text-gray-300" : rank === 3 ? "text-orange-300" : "text-gray-200"
              }`} style={{ fontFamily: "var(--font-inter)" }}>#{rank}</span>
            )}
            <span className="font-bold text-gray-900 tracking-tight">{race.stadium}</span>
            <span className="text-gray-400 text-sm font-medium">{race.race_no}R</span>
            <span className="text-xs text-gray-300 mx-0.5">·</span>
            <span className="text-xs text-gray-400">締切 {formatCloseTime(race.close_time)}</span>
          </div>
          {dec.badgeBg ? (
            <span className={dec.badge} style={{ background: dec.badgeBg }}>{dec.label}</span>
          ) : (
            <span className={dec.badge}>{dec.label}</span>
          )}
        </div>

        {/* 艇番サークル */}
        <div className="flex items-center justify-center gap-2.5 py-2 mb-3">
          {picks.map((lane, i) => (
            <div key={i} className="flex items-center gap-2">
              <BoatBadge lane={lane} />
              {i < picks.length - 1 && (
                <span className="text-gray-200 text-base">—</span>
              )}
            </div>
          ))}
          <span className="text-xs text-gray-300 ml-1.5">三連複</span>
        </div>

        {/* 信頼度 */}
        <div className="mb-3">
          <div className="flex justify-between items-center mb-1">
            <span className="text-xs text-gray-400 font-medium">信頼度</span>
            <span className={`text-base font-black tabular-nums ${dec.confText}`}
              style={{ fontFamily: "var(--font-inter)" }}>
              {Number(pred.confidence).toFixed(1)}
            </span>
          </div>
          <div className="h-1.5 rounded-full overflow-hidden bg-gray-100">
            <div className={`h-full rounded-full bg-gradient-to-r ${dec.bar}`} style={{ width: `${confPct}%` }} />
          </div>
        </div>

        {/* EV / Kelly ピル */}
        {(ev !== null || (kelly && kelly > 0)) && (
          <div className="flex flex-wrap gap-1.5 mb-2.5">
            {ev !== null && (
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full tabular-nums ${
                ev > 0.15 ? "bg-rose-50 text-rose-500" :
                ev > 0    ? "bg-orange-50 text-orange-500" :
                            "bg-gray-100 text-gray-400"
              }`}>EV {ev >= 0 ? "+" : ""}{(ev * 100).toFixed(0)}%</span>
            )}
            {kelly && kelly > 0 && (
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-50 text-amber-600 tabular-nums">
                Kelly {(kelly * 100).toFixed(1)}%
              </span>
            )}
            {pred.gap != null && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-gray-50 text-gray-400 tabular-nums">
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
          <div className={`mt-3 pt-2.5 border-t border-gray-50 flex items-center gap-2 text-sm ${
            res.prediction_hit ? "text-rose-500 font-bold" : "text-gray-300 font-medium"
          }`}>
            {res.prediction_hit ? "🎉 的中" : "✗ 不的中"}
            {res.trifecta_result && (
              <span className="text-xs font-normal text-gray-400">
                {res.trifecta_result}
                {res.payout && <span className="font-semibold text-gray-600"> · ¥{res.payout.toLocaleString()}</span>}
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
          className="flex items-center justify-center gap-1.5 mx-4 mb-4 py-2.5 rounded-xl text-sm font-bold text-white transition-opacity hover:opacity-90"
          style={{ background: dec.btnBg ?? undefined }}
        >
          <span>boatrace.jp で投票</span>
          <span className="text-xs opacity-80">→</span>
        </a>
      )}
    </div>
  );
}
