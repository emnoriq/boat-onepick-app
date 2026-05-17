import Link from "next/link";
import { RaceWithPrediction } from "@/lib/supabase";
import { formatCloseTime, buildBoatraceUrl } from "@/lib/format";

// ── 艇番カラー（ボートレース公式色） ─────────────────────────────────────
const BOAT: { bg: string; text: string; ring: string }[] = [
  { bg: "bg-white",        text: "text-gray-800",  ring: "ring-1 ring-gray-200 shadow" },
  { bg: "bg-neutral-900",  text: "text-white",      ring: "" },
  { bg: "bg-red-500",      text: "text-white",      ring: "" },
  { bg: "bg-sky-500",      text: "text-white",      ring: "" },
  { bg: "bg-yellow-400",   text: "text-gray-900",   ring: "" },
  { bg: "bg-green-500",    text: "text-white",      ring: "" },
];

function BoatBadge({ lane }: { lane: number }) {
  const c = BOAT[lane - 1] ?? BOAT[0];
  return (
    <span
      className={`inline-flex items-center justify-center w-11 h-11 rounded-full text-xl font-black select-none ${c.bg} ${c.text} ${c.ring}`}
    >
      {lane}
    </span>
  );
}

// ── decision ごとの配色 ──────────────────────────────────────────────────
const DEC = {
  buy: {
    leftBar:  "border-l-4 border-l-emerald-500",
    label:    "BUY",
    labelCls: "bg-emerald-500 text-white",
    bar:      "bg-emerald-500",
    btn:      "bg-emerald-500 hover:bg-emerald-600 text-white",
  },
  candidate: {
    leftBar:  "border-l-4 border-l-amber-400",
    label:    "検討",
    labelCls: "bg-amber-400 text-white",
    bar:      "bg-amber-400",
    btn:      "bg-amber-400 hover:bg-amber-500 text-white",
  },
  skip: {
    leftBar:  "border-l-4 border-l-gray-200",
    label:    "見送り",
    labelCls: "bg-gray-100 text-gray-500",
    bar:      "bg-gray-200",
    btn:      "",
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

  // 信頼度バー (50→0%, 85→100%)
  const confPct = Math.min(100, Math.max(0, (Number(pred.confidence) - 50) / 35 * 100));

  // EV (best_ev カラム優先、なければ reason テキストから)
  const ev = pred.best_ev
    ?? (() => { const m = pred.reason?.match(/EV=([+-]?[\d.]+)/); return m ? parseFloat(m[1]) : null; })();
  const kelly = pred.kelly_fraction;

  // reason 先頭1行
  const firstReason = pred.reason?.split("\n").filter(Boolean)[0] ?? null;

  return (
    <div className={`bg-white rounded-2xl ${dec.leftBar} border border-gray-100 shadow-sm mb-4 overflow-hidden`}>

      {/* ── カード本体 → 詳細ページへ ─────────────────────────── */}
      <Link href={`/races/${race.id}`} className="block px-5 pt-4 pb-3">

        {/* 上段: 場・R番号・時刻・バッジ */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2 min-w-0">
            {rank != null && (
              <span className={`text-xs font-black shrink-0 ${
                rank === 1 ? "text-yellow-500" : rank === 2 ? "text-slate-400" : rank === 3 ? "text-amber-700" : "text-gray-300"
              }`}>
                #{rank}
              </span>
            )}
            <span className="font-black text-gray-900 text-base">{race.stadium}</span>
            <span className="font-bold text-gray-400">{race.race_no}R</span>
            <span className="text-xs text-gray-300">·</span>
            <span className="text-xs text-gray-400 shrink-0">締切 {formatCloseTime(race.close_time)}</span>
          </div>
          <span className={`text-xs font-bold px-3 py-1 rounded-full shrink-0 ml-2 ${dec.labelCls}`}>
            {dec.label}
          </span>
        </div>

        {/* 艇番サークル */}
        <div className="flex items-center justify-center gap-2 py-2 mb-4">
          {picks.map((lane, i) => (
            <div key={i} className="flex items-center gap-2">
              <BoatBadge lane={lane} />
              {i < picks.length - 1 && (
                <span className="text-gray-200 font-bold">─</span>
              )}
            </div>
          ))}
          <span className="text-xs text-gray-300 font-medium ml-2">三連複</span>
        </div>

        {/* 信頼度バー */}
        <div className="mb-3">
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-xs text-gray-400 font-medium">信頼度</span>
            <span className={`text-sm font-black tabular-nums ${
              Number(pred.confidence) >= 75 ? "text-emerald-600" :
              Number(pred.confidence) >= 65 ? "text-amber-500" : "text-gray-500"
            }`}>
              {Number(pred.confidence).toFixed(1)}
            </span>
          </div>
          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div className={`h-full rounded-full ${dec.bar}`} style={{ width: `${confPct}%` }} />
          </div>
        </div>

        {/* EV / Kelly / gap ピル */}
        {(ev !== null || (kelly && kelly > 0) || pred.gap != null) && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {ev !== null && (
              <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${
                ev > 0.15 ? "bg-green-100 text-green-700" :
                ev > 0    ? "bg-emerald-50 text-emerald-600" :
                            "bg-gray-100 text-gray-400"
              }`}>
                EV {ev >= 0 ? "+" : ""}{(ev * 100).toFixed(0)}%
              </span>
            )}
            {kelly && kelly > 0 && (
              <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-violet-50 text-violet-600">
                Kelly {(kelly * 100).toFixed(1)}%
              </span>
            )}
            {pred.gap != null && (
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-50 text-slate-400">
                差 {Number(pred.gap).toFixed(1)}
              </span>
            )}
          </div>
        )}

        {/* 理由 (1行) */}
        {firstReason && (
          <p className="text-xs text-gray-400 line-clamp-1 leading-relaxed">
            {firstReason}
          </p>
        )}

        {/* 結果 */}
        {res && (
          <div className={`mt-3 pt-3 border-t border-gray-50 flex items-center gap-2 text-sm font-bold ${
            res.prediction_hit ? "text-emerald-600" : "text-gray-400"
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

      {/* ── 投票リンク（BUY / CANDIDATE のみ） ──────────────────── */}
      {isBet && (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className={`flex items-center justify-center gap-2 py-3 text-sm font-bold transition-colors ${dec.btn}`}
        >
          <span>boatrace.jp で出走表を確認</span>
          <span className="text-base">→</span>
        </a>
      )}
    </div>
  );
}
