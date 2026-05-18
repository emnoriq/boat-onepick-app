"use client";

import { useState } from "react";
import { RaceWithPrediction } from "@/lib/supabase";
import RaceCard from "@/components/RaceCard";

type Props = {
  buyRaces:  RaceWithPrediction[];
  candRaces: RaceWithPrediction[];
  pending:   RaceWithPrediction[];
  skipRaces: RaceWithPrediction[];
};

export default function HomeList({ buyRaces, candRaces, pending, skipRaces }: Props) {
  const [view, setView] = useState<"rank" | "time">("rank");

  // 時間順: BUY + 検討 + 展示待ち を close_time 昇順
  const timeRows = [...buyRaces, ...candRaces, ...pending].sort(
    (a, b) => a.close_time.localeCompare(b.close_time)
  );

  const hasBets = buyRaces.length > 0 || candRaces.length > 0;

  return (
    <>
      {/* ── 表示切り替えタブ ─────────────────────── */}
      {(hasBets || pending.length > 0) && (
        <div className="flex gap-2 mb-4">
          {[
            { key: "rank" as const, label: "📊 判定順" },
            { key: "time" as const, label: "🕐 時間順" },
          ].map(t => (
            <button
              key={t.key}
              onClick={() => setView(t.key)}
              className={`flex-1 py-2.5 rounded-2xl text-sm font-bold transition-all ${
                view === t.key
                  ? "text-white shadow-sm"
                  : "bg-white text-gray-400 hover:text-gray-600"
              }`}
              style={view === t.key
                ? { background: "linear-gradient(to right, #FF6B6B, #FF8E53)" }
                : {}
              }
            >
              {t.label}
            </button>
          ))}
        </div>
      )}

      {/* ── 判定順 ──────────────────────────────── */}
      {view === "rank" && (
        <>
          {/* データなし */}
          {!hasBets && pending.length === 0 && skipRaces.length === 0 && (
            <div className="text-center py-16">
              <p className="text-4xl mb-3">⛵</p>
              <p className="font-bold text-gray-600 mb-1">本日のデータがまだありません</p>
              <p className="text-sm text-gray-400">朝6時以降にスキャンが始まります</p>
            </div>
          )}

          {/* BUY */}
          {buyRaces.length > 0 && (
            <section className="mb-6">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-1 h-5 rounded-full" style={{ background: "linear-gradient(to bottom, #FF6B6B, #FF8E53)" }} />
                <h2 className="text-sm font-bold text-gray-700">
                  投票確定
                  <span className="ml-2 text-xs font-normal text-gray-400">BUY · {buyRaces.length}件</span>
                </h2>
              </div>
              {buyRaces.map((r, i) => <RaceCard key={r.id} race={r} rank={i + 1} />)}
            </section>
          )}

          {/* CANDIDATE */}
          {candRaces.length > 0 && (
            <section className="mb-6">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-1 h-5 rounded-full" style={{ background: "linear-gradient(to bottom, #FF8E53, #FFBE0B)" }} />
                <h2 className="text-sm font-bold text-gray-700">
                  投票検討
                  <span className="ml-2 text-xs font-normal text-gray-400">CANDIDATE · {candRaces.length}件</span>
                </h2>
              </div>
              {candRaces.map((r, i) => <RaceCard key={r.id} race={r} rank={buyRaces.length + i + 1} />)}
            </section>
          )}

          {/* 展示待ち */}
          {pending.length > 0 && (
            <section className="mb-6">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-1 h-5 rounded-full bg-gray-200" />
                <h2 className="text-sm font-semibold text-gray-400">
                  展示待ち
                  <span className="ml-2 text-xs font-normal">直前スキャン後に更新 · {pending.length}件</span>
                </h2>
              </div>
              {pending.map(r => <RaceCard key={r.id} race={r} />)}
            </section>
          )}

          {/* 見送り */}
          {skipRaces.length > 0 && (
            <details className="mb-6 group">
              <summary className="flex items-center gap-2 cursor-pointer text-xs text-gray-400 hover:text-gray-500 select-none list-none mb-3">
                <span className="group-open:rotate-90 transition-transform inline-block">▶</span>
                <span>見送り {skipRaces.length}件</span>
              </summary>
              <div className="opacity-50">
                {skipRaces.map(r => <RaceCard key={r.id} race={r} />)}
              </div>
            </details>
          )}
        </>
      )}

      {/* ── 時間順 ──────────────────────────────── */}
      {view === "time" && (
        <>
          {timeRows.length === 0 ? (
            <div className="text-center py-16">
              <p className="text-4xl mb-3">⛵</p>
              <p className="font-bold text-gray-600 mb-1">本日のデータがまだありません</p>
              <p className="text-sm text-gray-400">朝6時以降にスキャンが始まります</p>
            </div>
          ) : (
            <>
              <p className="text-xs text-gray-400 mb-3">締切時刻が早い順 · {timeRows.length}件</p>
              {timeRows.map((r, i) => (
                <RaceCard
                  key={r.id}
                  race={r}
                  rank={r.predictions?.decision === "skip" ? undefined : i + 1}
                />
              ))}
            </>
          )}
        </>
      )}
    </>
  );
}
