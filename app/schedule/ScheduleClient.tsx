"use client";

import { useState, useMemo } from "react";
import type { ScheduleRow, ScheduleSummary } from "@/lib/supabase";

type Tab = "time" | "conf" | "bet" | "watch";

// ── 小コンポーネント ──────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  return status === "scheduled" ? (
    <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded font-medium">
      締切前
    </span>
  ) : (
    <span className="text-xs bg-gray-100 text-gray-400 px-1.5 py-0.5 rounded">
      締切済
    </span>
  );
}

function DecisionBadge({
  decision,
  isWatch,
}: {
  decision: string | null;
  isWatch: boolean;
}) {
  if (decision === null)
    return <span className="text-xs text-gray-300">未評価</span>;
  if (decision === "buy")
    return (
      <span className="text-xs bg-red-100 text-red-700 font-bold px-1.5 py-0.5 rounded">
        BUY
      </span>
    );
  if (decision === "candidate")
    return (
      <span className="text-xs bg-orange-100 text-orange-700 font-semibold px-1.5 py-0.5 rounded">
        CAND
      </span>
    );
  if (isWatch)
    return (
      <span className="text-xs bg-blue-100 text-blue-700 font-semibold px-1.5 py-0.5 rounded">
        WATCH
      </span>
    );
  return (
    <span className="text-xs bg-gray-100 text-gray-400 px-1.5 py-0.5 rounded">
      SKIP
    </span>
  );
}

function HitBadge({ hit }: { hit: boolean | null }) {
  if (hit === null) return <span className="text-gray-300 text-xs">-</span>;
  return hit ? (
    <span className="text-xs bg-green-100 text-green-700 font-bold px-1 py-0.5 rounded">
      的中
    </span>
  ) : (
    <span className="text-xs text-gray-400">外れ</span>
  );
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("ja-JP", {
    timeZone: "Asia/Tokyo",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function rowBg(r: ScheduleRow): string {
  if (r.decision === "buy") return "bg-red-50";
  if (r.decision === "candidate") return "bg-orange-50";
  if (r.is_watch) return "bg-blue-50";
  return "";
}

// ── テーブル ─────────────────────────────────────────────────────────────────

function RaceTable({ rows }: { rows: ScheduleRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-gray-50 text-xs text-gray-500">
            <th className="px-2 py-2 border-b text-left">場</th>
            <th className="px-2 py-2 border-b">R</th>
            <th className="px-2 py-2 border-b">締切</th>
            <th className="px-2 py-2 border-b">状態</th>
            <th className="px-2 py-2 border-b">判定</th>
            <th className="px-2 py-2 border-b text-right">conf</th>
            <th className="px-2 py-2 border-b text-right">gap</th>
            <th className="px-2 py-2 border-b">pick</th>
            <th className="px-2 py-2 border-b">展示</th>
            <th className="px-2 py-2 border-b">結果</th>
            <th className="px-2 py-2 border-b">的中</th>
            <th className="px-2 py-2 border-b text-right">払戻</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={`${r.race_id}-${i}`}
              className={`border-b last:border-b-0 hover:brightness-95 transition-colors cursor-pointer ${rowBg(r)}`}
              onClick={() => { window.location.href = `/races/${r.race_id}`; }}
            >
              <td className="px-2 py-1.5 font-medium">{r.stadium}</td>
              <td className="px-2 py-1.5 text-center">{r.race_no}</td>
              <td className="px-2 py-1.5 text-center font-mono text-xs">
                {fmtTime(r.close_time)}
              </td>
              <td className="px-2 py-1.5 text-center">
                <StatusBadge status={r.status} />
              </td>
              <td className="px-2 py-1.5 text-center">
                <DecisionBadge decision={r.decision} isWatch={r.is_watch} />
              </td>
              <td className="px-2 py-1.5 text-right font-mono text-xs">
                {r.confidence !== null ? r.confidence.toFixed(1) : (
                  <span className="text-gray-300">-</span>
                )}
              </td>
              <td className="px-2 py-1.5 text-right font-mono text-xs">
                {r.gap !== null ? r.gap.toFixed(1) : (
                  <span className="text-gray-300">-</span>
                )}
              </td>
              <td className="px-2 py-1.5 font-mono text-xs">
                {r.pick ?? <span className="text-gray-300">-</span>}
              </td>
              <td className="px-2 py-1.5 text-center">
                {r.decision !== null ? (
                  <span
                    className={`text-xs px-1 rounded ${
                      r.has_exhibition
                        ? "bg-green-100 text-green-700"
                        : "bg-yellow-50 text-yellow-600"
                    }`}
                  >
                    {r.has_exhibition ? "済" : "未"}
                  </span>
                ) : (
                  <span className="text-gray-300 text-xs">-</span>
                )}
              </td>
              <td className="px-2 py-1.5 font-mono text-xs text-center">
                {r.trifecta_result ?? <span className="text-gray-300">-</span>}
              </td>
              <td className="px-2 py-1.5 text-center">
                <HitBadge hit={r.prediction_hit} />
              </td>
              <td className="px-2 py-1.5 text-right font-mono text-xs">
                {r.payout !== null ? (
                  `¥${r.payout.toLocaleString()}`
                ) : (
                  <span className="text-gray-300">-</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── サマリカード ──────────────────────────────────────────────────────────────

function SummaryCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: number;
  sub?: string;
  color?: string;
}) {
  return (
    <div className={`rounded-lg border p-2 text-center ${color ?? "bg-white"}`}>
      <div className="text-xs text-gray-400 leading-tight">{label}</div>
      <div className="text-xl font-bold mt-0.5">{value}</div>
      {sub && <div className="text-xs text-gray-400">{sub}</div>}
    </div>
  );
}

// ── メインコンポーネント ──────────────────────────────────────────────────────

export default function ScheduleClient({
  rows,
  summary,
  today,
}: {
  rows: ScheduleRow[];
  summary: ScheduleSummary;
  today: string;
}) {
  const [tab, setTab] = useState<Tab>("time");

  // 精度順: 評価済みを confidence desc / gap desc でソート
  const confRows = useMemo(
    () =>
      [...rows]
        .filter((r) => r.decision !== null)
        .sort((a, b) => {
          const cd = (b.confidence ?? 0) - (a.confidence ?? 0);
          return cd !== 0 ? cd : (b.gap ?? 0) - (a.gap ?? 0);
        }),
    [rows],
  );

  // 投票候補: buy / candidate のみ。締切前を先頭に。
  const betRows = useMemo(
    () =>
      rows
        .filter((r) => r.decision === "buy" || r.decision === "candidate")
        .sort((a, b) => {
          if (a.status === "scheduled" && b.status !== "scheduled") return -1;
          if (a.status !== "scheduled" && b.status === "scheduled") return 1;
          return a.close_time.localeCompare(b.close_time);
        }),
    [rows],
  );

  // 検証候補: watch のみ
  const watchRows = useMemo(() => rows.filter((r) => r.is_watch), [rows]);

  const TABS: { key: Tab; label: string; count: number }[] = [
    { key: "time",  label: "時間順",   count: rows.length },
    { key: "conf",  label: "精度順",   count: confRows.length },
    { key: "bet",   label: "投票候補", count: betRows.length },
    { key: "watch", label: "検証候補", count: watchRows.length },
  ];

  return (
    <main className="max-w-5xl mx-auto px-4 py-6">
      {/* ── ヘッダ ────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-xl font-bold">レーススケジュール</h1>
        <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">
          {today}
        </span>
      </div>
      <div className="flex gap-3 text-xs text-gray-400 mb-5">
        <a href="/ops"       className="underline hover:text-gray-600">運用チェック</a>
        <a href="/roll-plan" className="underline hover:text-gray-600">転がし計画</a>
        <a href="/debug"     className="underline hover:text-gray-600">デバッグ</a>
        <a href="/stats"     className="underline hover:text-gray-600">長期統計</a>
      </div>

      {/* ── サマリ ────────────────────────────────────── */}
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-2 mb-3">
        <SummaryCard label="全レース"  value={summary.totalRaces} />
        <SummaryCard label="評価済み"  value={summary.evaluatedRaces}
          sub={`/ ${summary.totalRaces}`} />
        <SummaryCard label="展示済み"  value={summary.exhibitionRaces}
          sub={`/ ${summary.evaluatedRaces}`} />
        <SummaryCard label="締切前"    value={summary.openCount}
          color="bg-green-50 border-green-200" />
        <SummaryCard label="締切済み"  value={summary.closedCount}
          color="bg-gray-50" />
      </div>
      <div className="flex flex-wrap gap-2 mb-5">
        <span className="inline-flex items-center gap-1 bg-red-100 text-red-700 px-2.5 py-1 rounded-full text-xs font-bold">
          BUY <span className="bg-red-200 rounded-full px-1.5">{summary.buyCount}</span>
        </span>
        <span className="inline-flex items-center gap-1 bg-orange-100 text-orange-700 px-2.5 py-1 rounded-full text-xs font-semibold">
          CANDIDATE <span className="bg-orange-200 rounded-full px-1.5">{summary.candidateCount}</span>
        </span>
        <span className="inline-flex items-center gap-1 bg-blue-100 text-blue-700 px-2.5 py-1 rounded-full text-xs font-semibold">
          WATCH <span className="bg-blue-200 rounded-full px-1.5">{summary.watchCount}</span>
        </span>
        <span className="inline-flex items-center gap-1 bg-gray-100 text-gray-500 px-2.5 py-1 rounded-full text-xs">
          SKIP <span className="bg-gray-200 rounded-full px-1.5">{summary.skipCount}</span>
        </span>
      </div>

      {/* ── タブ ──────────────────────────────────────── */}
      <div className="flex border-b mb-4 overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex-none flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium -mb-px border-b-2 transition-colors whitespace-nowrap ${
              tab === t.key
                ? "border-blue-500 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            {t.label}
            <span
              className={`text-xs px-1.5 py-0.5 rounded-full ${
                tab === t.key
                  ? "bg-blue-100 text-blue-600"
                  : "bg-gray-100 text-gray-400"
              }`}
            >
              {t.count}
            </span>
          </button>
        ))}
      </div>

      {/* ── 時間順 ────────────────────────────────────── */}
      {tab === "time" && (
        <section>
          <p className="text-xs text-gray-400 mb-2">
            全 {rows.length} レース｜締切時刻が早い順
          </p>
          <RaceTable rows={rows} />
          {rows.length === 0 && (
            <p className="text-center text-gray-400 py-12">
              本日のレースデータがありません
            </p>
          )}
        </section>
      )}

      {/* ── 精度順 ────────────────────────────────────── */}
      {tab === "conf" && (
        <section>
          <p className="text-xs text-gray-400 mb-2">
            評価済み {confRows.length} レース｜confidence → gap の降順
          </p>
          <RaceTable rows={confRows} />
          {confRows.length === 0 && (
            <p className="text-center text-gray-400 py-12">
              評価済みレースがありません
            </p>
          )}
        </section>
      )}

      {/* ── 投票候補 ──────────────────────────────────── */}
      {tab === "bet" && (
        <section>
          {betRows.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-500 font-medium">今日の投票候補はありません</p>
              <p className="text-xs text-gray-300 mt-1">
                buy: confidence ≥ 70 かつ gap ≥ 10 ／ candidate: confidence ≥ 62 かつ gap ≥ 7
              </p>
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-3 mb-3">
                <p className="text-sm text-gray-700">
                  投票候補 <span className="font-bold">{betRows.length} 件</span>
                </p>
                <span className="text-xs bg-amber-50 border border-amber-200 text-amber-700 px-2.5 py-1 rounded-full">
                  想定投資額 ¥{(betRows.length * 100).toLocaleString()}（1点100円）
                </span>
              </div>
              <RaceTable rows={betRows} />
            </>
          )}
        </section>
      )}

      {/* ── 検証候補 ──────────────────────────────────── */}
      {tab === "watch" && (
        <section>
          <div className="flex items-start gap-2 bg-blue-50 border border-blue-200 rounded-lg p-3 mb-3 text-xs text-blue-700">
            <span className="text-base leading-none mt-0.5">🔍</span>
            <div>
              <span className="font-bold">検証候補（WATCH）は実投票対象外です。</span>
              <span className="ml-1">
                confidence ≥ 55 かつ gap ≥ 7 を満たすが buy / candidate 基準未満のレース。
                将来の閾値調整のために記録しています。
              </span>
            </div>
          </div>
          {watchRows.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-500 font-medium">今日の検証候補はありません</p>
              <p className="text-xs text-gray-300 mt-1">
                watch: confidence ≥ 55 かつ gap ≥ 7（荒れなし）
              </p>
            </div>
          ) : (
            <>
              <p className="text-xs text-gray-400 mb-2">
                {watchRows.length} 件の検証候補｜実投票対象外
              </p>
              <RaceTable rows={watchRows} />
            </>
          )}
        </section>
      )}
    </main>
  );
}
