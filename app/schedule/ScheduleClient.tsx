"use client";

import { useState, useMemo, useEffect } from "react";
import { useRouter } from "next/navigation";
import type { ScheduleRow, ScheduleSummary } from "@/lib/supabase";

type Tab = "bet" | "time" | "conf";

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("ja-JP", {
    timeZone: "Asia/Tokyo", hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

function offsetDate(base: string, days: number): string {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

// 艇番カラー
const BOAT_BG   = ["bg-white ring-1 ring-gray-200", "bg-neutral-800", "bg-red-500", "bg-sky-500", "bg-yellow-400", "bg-green-500"];
const BOAT_TEXT = ["text-gray-700", "text-white", "text-white", "text-white", "text-gray-800", "text-white"];

function BoatBadge({ lane }: { lane: number }) {
  return (
    <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-sm font-black ${BOAT_BG[lane - 1] ?? BOAT_BG[0]} ${BOAT_TEXT[lane - 1] ?? BOAT_TEXT[0]}`}>
      {lane}
    </span>
  );
}

// レースカード
function RaceCard({ r, onClick }: { r: ScheduleRow; onClick: () => void }) {
  const isBuy  = r.decision === "buy";
  const isCand = r.decision === "candidate";
  const isOpen = r.status === "scheduled";

  const leftBar = isBuy  ? "border-l-4 border-l-rose-400" :
                  isCand ? "border-l-4 border-l-orange-400" :
                           "border-l-4 border-l-gray-100";

  const decLabel = isBuy  ? <span className="text-xs font-bold px-2.5 py-0.5 rounded-full text-white" style={{ background: "linear-gradient(to right,#FF6B6B,#FF8E53)" }}>BUY</span> :
                   isCand ? <span className="text-xs font-bold px-2.5 py-0.5 rounded-full text-white" style={{ background: "linear-gradient(to right,#FF8E53,#FFBE0B)" }}>検討</span> :
                   r.decision === "skip" ? <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-400">見送り</span> :
                   <span className="text-xs text-gray-300">未評価</span>;

  const picks = r.pick ? r.pick.split("-").map(Number) : [];

  return (
    <div
      onClick={onClick}
      className={`bg-white rounded-2xl shadow-sm mb-2.5 overflow-hidden cursor-pointer hover:shadow-md transition-shadow ${leftBar}`}
    >
      <div className="px-4 py-3">
        {/* 上段 */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="font-black text-gray-800">{r.stadium}</span>
            <span className="text-gray-400 font-semibold">{r.race_no}R</span>
            <span className="text-xs text-gray-400">· 締切 {fmtTime(r.close_time)}</span>
            {isOpen
              ? <span className="text-xs bg-emerald-50 text-emerald-500 font-bold px-1.5 py-0.5 rounded-full">受付中</span>
              : <span className="text-xs text-gray-300">締切済</span>
            }
          </div>
          {decLabel}
        </div>

        {/* 艇番 + confidence */}
        {picks.length > 0 && (
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1">
              {picks.map((lane, i) => (
                <span key={i} className="flex items-center gap-1">
                  <BoatBadge lane={lane} />
                  {i < picks.length - 1 && <span className="text-gray-200 text-xs">─</span>}
                </span>
              ))}
            </div>
            <span className="text-xs text-gray-300 ml-1">三連複</span>
            {r.confidence != null && (
              <span className={`ml-auto text-xs font-bold tabular-nums ${
                r.confidence >= 75 ? "text-rose-500" : r.confidence >= 65 ? "text-orange-400" : "text-gray-400"
              }`}>
                {r.confidence.toFixed(1)}点
              </span>
            )}
          </div>
        )}

        {/* 結果 */}
        {r.trifecta_result && (
          <div className={`mt-2 pt-2 border-t border-gray-50 flex items-center gap-2 text-xs ${
            r.prediction_hit ? "text-rose-500 font-bold" : "text-gray-400"
          }`}>
            {r.prediction_hit ? "🎉 的中" : "✗ 外れ"}
            <span className="text-gray-400 font-normal">{r.trifecta_result}</span>
            {r.payout && <span className="font-bold">¥{r.payout.toLocaleString()}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ScheduleClient({ rows, summary, today, date }: {
  rows: ScheduleRow[];
  summary: ScheduleSummary;
  today: string;
  date: string;
}) {
  const [tab, setTab] = useState<Tab>("bet");
  const router = useRouter();

  useEffect(() => {
    if (date !== today || summary.openCount === 0) return;
    const id = setInterval(() => window.location.reload(), 30_000);
    return () => clearInterval(id);
  }, [date, today, summary.openCount]);

  const betRows = useMemo(() =>
    rows.filter(r => r.decision === "buy" || r.decision === "candidate")
        .sort((a, b) => {
          if (a.status === "scheduled" && b.status !== "scheduled") return -1;
          if (a.status !== "scheduled" && b.status === "scheduled") return 1;
          return a.close_time.localeCompare(b.close_time);
        }),
    [rows]);

  const confRows = useMemo(() =>
    [...rows].filter(r => r.decision !== null)
             .sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0)),
    [rows]);

  const TABS: { key: Tab; label: string; count: number; icon: string }[] = [
    { key: "bet",  label: "投票候補", count: betRows.length,  icon: "🎯" },
    { key: "time", label: "全レース", count: rows.length,     icon: "🕐" },
    { key: "conf", label: "精度順",   count: confRows.length, icon: "📈" },
  ];

  const displayRows = tab === "bet" ? betRows : tab === "conf" ? confRows : rows;

  return (
    <main className="max-w-lg mx-auto px-4 py-5">

      {/* ── ヘッダー ───────────────────────────────── */}
      <div
        className="rounded-3xl p-5 mb-4 text-white shadow-lg"
        style={{ background: "linear-gradient(135deg, #FF6B6B 0%, #FF8E53 60%, #FFBE0B 100%)" }}
      >
        <p className="text-white/60 text-xs mb-1">スケジュール</p>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <a
              href={`/schedule?date=${offsetDate(date, -1)}`}
              className="bg-white/20 rounded-full w-8 h-8 flex items-center justify-center text-sm font-bold hover:bg-white/30 transition-colors"
            >‹</a>
            <span className="font-black text-lg">
              {date === today ? "今日" : date.slice(5).replace("-", "/")}
            </span>
            <a
              href={`/schedule?date=${offsetDate(date, 1)}`}
              className={`bg-white/20 rounded-full w-8 h-8 flex items-center justify-center text-sm font-bold transition-colors ${
                date >= today ? "opacity-30 pointer-events-none" : "hover:bg-white/30"
              }`}
            >›</a>
          </div>
          {date === today && summary.openCount > 0 && (
            <span className="bg-white/20 text-xs font-bold px-3 py-1 rounded-full">
              🔄 30秒更新
            </span>
          )}
        </div>

        {/* サマリー数字 */}
        <div className="flex gap-2">
          {[
            { label: "BUY",    v: summary.buyCount,       style: "bg-white/30" },
            { label: "検討",   v: summary.candidateCount, style: "bg-white/20" },
            { label: "展示済", v: summary.exhibitionRaces, style: "bg-white/15" },
            { label: "受付中", v: summary.openCount,      style: "bg-white/15" },
          ].map(c => (
            <div key={c.label} className={`${c.style} rounded-2xl px-3 py-1.5 text-center flex-1`}>
              <div className="text-xl font-black">{c.v}</div>
              <div className="text-xs text-white/70">{c.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── タブ ──────────────────────────────────── */}
      <div className="flex gap-2 mb-4">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-2xl text-sm font-bold transition-all ${
              tab === t.key
                ? "text-white shadow-sm"
                : "bg-white text-gray-400 hover:text-gray-600"
            }`}
            style={tab === t.key ? { background: "linear-gradient(to right, #FF6B6B, #FF8E53)" } : {}}
          >
            <span>{t.icon}</span>
            <span>{t.label}</span>
            <span className={`text-xs ${tab === t.key ? "text-white/80" : "text-gray-300"}`}>
              {t.count}
            </span>
          </button>
        ))}
      </div>

      {/* ── リスト ─────────────────────────────────── */}
      {displayRows.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-4xl mb-3">⛵</p>
          <p className="font-bold text-gray-500">
            {tab === "bet" ? "投票候補がありません" : "データがありません"}
          </p>
          {tab === "bet" && (
            <p className="text-xs text-gray-400 mt-1">展示スキャン後に更新されます</p>
          )}
        </div>
      ) : (
        <div>
          {tab === "bet" && (
            <p className="text-xs text-gray-400 mb-3">
              受付中を先頭に表示 · タップで詳細
            </p>
          )}
          {displayRows.map(r => (
            <RaceCard
              key={r.race_id}
              r={r}
              onClick={() => router.push(`/races/${r.race_id}`)}
            />
          ))}
        </div>
      )}
    </main>
  );
}
