"use client";

import { useState } from "react";
import type { RollPlan, RollRoute, RollStep, RollTier, RollJudgment } from "@/lib/rollPlan";
import type { ScheduleRow } from "@/lib/supabase";

type Tab = "best" | "backup" | "candidates" | "timeline";

// ── 書式ヘルパー ─────────────────────────────────────────────────────────────

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("ja-JP", {
    timeZone: "Asia/Tokyo",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function fmtInterval(minutes: number | null): string {
  if (minutes === null) return "-";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h > 0 ? `${h}h${m}m` : `${m}分`;
}

// ── バッジコンポーネント ──────────────────────────────────────────────────────

function TierBadge({ tier }: { tier: RollTier | null }) {
  if (!tier)
    return <span className="text-xs text-gray-300">未評価</span>;
  if (tier === "buy")
    return (
      <span className="text-xs bg-red-100 text-red-700 font-bold px-1.5 py-0.5 rounded">
        BUY
      </span>
    );
  if (tier === "candidate")
    return (
      <span className="text-xs bg-orange-100 text-orange-700 font-semibold px-1.5 py-0.5 rounded">
        CAND
      </span>
    );
  return (
    <span className="text-xs bg-blue-100 text-blue-700 font-semibold px-1.5 py-0.5 rounded">
      WATCH
    </span>
  );
}

function DecisionBadge({ row }: { row: ScheduleRow }) {
  const d = row.decision;
  const w = row.is_watch;
  if (!d) return <span className="text-xs text-gray-300">-</span>;
  if (d === "buy")
    return (
      <span className="text-xs bg-red-100 text-red-700 font-bold px-1 py-0.5 rounded">
        BUY
      </span>
    );
  if (d === "candidate")
    return (
      <span className="text-xs bg-orange-100 text-orange-700 px-1 py-0.5 rounded">
        CAND
      </span>
    );
  if (w)
    return (
      <span className="text-xs bg-blue-100 text-blue-700 px-1 py-0.5 rounded">
        WATCH
      </span>
    );
  return (
    <span className="text-xs bg-gray-100 text-gray-400 px-1 py-0.5 rounded">
      SKIP
    </span>
  );
}

function StatusBadge({ status }: { status: RollStep["stepStatus"] }) {
  const map = {
    BUY:         "bg-green-500 text-white font-bold",
    WAIT:        "bg-blue-100 text-blue-700",
    RESULT_WAIT: "bg-yellow-100 text-yellow-700",
    DONE:        "bg-gray-100 text-gray-500",
  } as const;
  const labels = { BUY: "▶ 購入", WAIT: "待機", RESULT_WAIT: "結果待", DONE: "終了" };
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${map[status]}`}>
      {labels[status]}
    </span>
  );
}

function HitBadge({ hit }: { hit: boolean | null }) {
  if (hit === null) return <span className="text-xs text-gray-300">-</span>;
  return hit ? (
    <span className="text-xs bg-green-100 text-green-700 font-bold px-1 rounded">的中</span>
  ) : (
    <span className="text-xs text-gray-400">外れ</span>
  );
}

function RatingBadge({ rating }: { rating: RollRoute["rating"] }) {
  if (rating === "strong")
    return <span className="text-xs bg-red-100 text-red-700 font-bold px-2 py-0.5 rounded-full">強い</span>;
  if (rating === "normal")
    return <span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full">普通</span>;
  return <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">弱い</span>;
}

// ── 判定バナー ───────────────────────────────────────────────────────────────

function JudgmentBanner({
  judgment,
  text,
}: {
  judgment: RollJudgment;
  text: string;
}) {
  const styles: Record<RollJudgment, string> = {
    go:          "bg-green-50 border-green-400 text-green-800",
    conditional: "bg-amber-50 border-amber-400 text-amber-800",
    skip:        "bg-gray-50 border-gray-300 text-gray-600",
  };
  const icons: Record<RollJudgment, string> = {
    go:          "✅",
    conditional: "⚠️",
    skip:        "🚫",
  };
  const labels: Record<RollJudgment, string> = {
    go:          "挑戦可能",
    conditional: "条件付き",
    skip:        "見送り",
  };
  return (
    <div className={`border-l-4 rounded-lg p-4 ${styles[judgment]}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-lg">{icons[judgment]}</span>
        <span className="font-bold text-base">
          今日の4回転がし判定：{labels[judgment]}
        </span>
      </div>
      <p className="text-sm">{text}</p>
      <p className="text-xs mt-2 opacity-75">
        ⚠️ 自動投票ではありません。最終判断は各レースの展示データ取得後に行ってください。
      </p>
    </div>
  );
}

// ── ルートのステップ行 ────────────────────────────────────────────────────────

function StepRow({
  step,
  stepNum,
}: {
  step: RollStep;
  stepNum: number;
}) {
  const stepColors: Record<RollTier, string> = {
    buy:       "border-l-4 border-red-400",
    candidate: "border-l-4 border-orange-400",
    watch:     "border-l-4 border-blue-400",
  };

  return (
    <div
      className={`bg-white rounded-lg p-3 ${stepColors[step.rollTier]} shadow-sm`}
    >
      <div className="flex items-center gap-2 flex-wrap">
        {/* STEP番号 */}
        <span className="text-xs font-bold text-gray-400 w-14 shrink-0">
          STEP {stepNum}
        </span>

        {/* 間隔 */}
        {step.intervalMinutes !== null && (
          <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
            ↑ {fmtInterval(step.intervalMinutes)}
          </span>
        )}

        {/* ステータス */}
        <StatusBadge status={step.stepStatus} />

        {/* Tier */}
        <TierBadge tier={step.rollTier} />

        {/* 場・R・時刻 */}
        <span className="font-medium text-sm">{step.stadium}</span>
        <span className="text-sm text-gray-600">{step.race_no}R</span>
        <span className="text-sm font-mono text-gray-700">{fmtTime(step.close_time)}</span>
      </div>

      {/* 詳細行 */}
      <div className="flex flex-wrap gap-3 mt-2 text-xs text-gray-600">
        <span>
          conf <span className="font-mono font-bold text-gray-800">
            {step.confidence?.toFixed(1) ?? "-"}
          </span>
        </span>
        <span>
          gap <span className="font-mono font-bold text-gray-800">
            {step.gap?.toFixed(1) ?? "-"}
          </span>
        </span>
        <span>
          pick <span className="font-mono font-bold text-gray-800">{step.pick ?? "-"}</span>
        </span>
        <span>
          展示{" "}
          <span className={step.has_exhibition ? "text-green-600" : "text-yellow-600"}>
            {step.has_exhibition ? "済✓" : "未"}
          </span>
        </span>
        {step.trifecta_result && (
          <span>
            結果 <span className="font-mono font-bold">{step.trifecta_result}</span>
          </span>
        )}
        {step.prediction_hit !== null && <HitBadge hit={step.prediction_hit} />}
        {step.payout !== null && (
          <span className="text-green-700 font-bold">
            ¥{step.payout.toLocaleString()}
          </span>
        )}
      </div>
    </div>
  );
}

// ── ルートカード ─────────────────────────────────────────────────────────────

function RouteCard({
  route,
  label,
  defaultOpen = true,
}: {
  route: RollRoute;
  label: string;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border rounded-xl overflow-hidden bg-gray-50 mb-4">
      {/* ヘッダ */}
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 bg-white hover:bg-gray-50 transition-colors text-left"
      >
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-bold text-sm text-gray-700">{label}</span>
          <RatingBadge rating={route.rating} />
          <span className="text-xs text-gray-500">
            {fmtTime(route.steps[0].close_time)}
            {" → "}
            {fmtTime(route.steps[3].close_time)}
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-500 shrink-0">
          <span className="hidden sm:flex gap-2">
            <span className="text-red-600 font-bold">BUY×{route.buyCount}</span>
            {route.candidateCount > 0 && (
              <span className="text-orange-600">CAND×{route.candidateCount}</span>
            )}
            {route.watchCount > 0 && (
              <span className="text-blue-600">WATCH×{route.watchCount}</span>
            )}
            <span>avg conf {route.avgConfidence}</span>
            <span>gap {route.avgGap}</span>
          </span>
          <span>{open ? "▲" : "▼"}</span>
        </div>
      </button>

      {/* ステップ一覧 */}
      {open && (
        <div className="p-3 space-y-2">
          {route.steps.map((step, i) => (
            <StepRow key={step.race_id} step={step} stepNum={i + 1} />
          ))}
          <div className="text-xs text-gray-400 text-right pt-1">
            最短間隔 {fmtInterval(route.minIntervalMinutes)} ／ 想定初期投資額 ¥100
          </div>
        </div>
      )}
    </div>
  );
}

// ── 候補一覧テーブル ──────────────────────────────────────────────────────────

function CandidateTable({
  candidates,
  showSkip,
  allRows,
}: {
  candidates: RollStep[];
  showSkip: boolean;
  allRows: ScheduleRow[];
}) {
  const rows = showSkip
    ? allRows.filter((r) => r.decision !== null)
    : candidates;

  if (rows.length === 0) {
    return (
      <p className="text-center text-gray-400 py-8">
        {showSkip ? "評価済みレースがありません" : "候補レースがありません"}
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-gray-50 text-xs text-gray-500">
            <th className="px-2 py-2 border-b text-left">場</th>
            <th className="px-2 py-2 border-b">R</th>
            <th className="px-2 py-2 border-b">締切</th>
            <th className="px-2 py-2 border-b">判定</th>
            <th className="px-2 py-2 border-b">Tier</th>
            <th className="px-2 py-2 border-b text-right">conf</th>
            <th className="px-2 py-2 border-b text-right">gap</th>
            <th className="px-2 py-2 border-b">pick</th>
            <th className="px-2 py-2 border-b">展示</th>
            <th className="px-2 py-2 border-b">状態</th>
            <th className="px-2 py-2 border-b">結果</th>
            <th className="px-2 py-2 border-b">的中</th>
            <th className="px-2 py-2 border-b text-right">払戻</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const isCandidate = candidates.some((c) => c.race_id === r.race_id);
            const candidate = candidates.find((c) => c.race_id === r.race_id);
            return (
              <tr
                key={`${r.race_id}-${i}`}
                className={`border-b last:border-b-0 ${
                  isCandidate
                    ? candidate?.rollTier === "buy"
                      ? "bg-red-50"
                      : candidate?.rollTier === "candidate"
                      ? "bg-orange-50"
                      : "bg-blue-50"
                    : "hover:bg-gray-50"
                }`}
              >
                <td className="px-2 py-1.5 font-medium">{r.stadium}</td>
                <td className="px-2 py-1.5 text-center">{r.race_no}</td>
                <td className="px-2 py-1.5 text-center font-mono text-xs">
                  {fmtTime(r.close_time)}
                </td>
                <td className="px-2 py-1.5 text-center">
                  <DecisionBadge row={r} />
                </td>
                <td className="px-2 py-1.5 text-center">
                  <TierBadge tier={candidate?.rollTier ?? null} />
                </td>
                <td className="px-2 py-1.5 text-right font-mono text-xs">
                  {r.confidence?.toFixed(1) ?? <span className="text-gray-300">-</span>}
                </td>
                <td className="px-2 py-1.5 text-right font-mono text-xs">
                  {r.gap?.toFixed(1) ?? <span className="text-gray-300">-</span>}
                </td>
                <td className="px-2 py-1.5 font-mono text-xs">
                  {r.pick ?? <span className="text-gray-300">-</span>}
                </td>
                <td className="px-2 py-1.5 text-center">
                  {r.decision && (
                    <span
                      className={`text-xs px-1 rounded ${
                        r.has_exhibition
                          ? "bg-green-100 text-green-700"
                          : "bg-yellow-50 text-yellow-600"
                      }`}
                    >
                      {r.has_exhibition ? "済" : "未"}
                    </span>
                  )}
                </td>
                <td className="px-2 py-1.5 text-center">
                  {r.status === "scheduled" ? (
                    <span className="text-xs bg-green-100 text-green-700 px-1 rounded">
                      締切前
                    </span>
                  ) : (
                    <span className="text-xs text-gray-400">締切済</span>
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
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── タイムライン ─────────────────────────────────────────────────────────────

function TimelineTable({
  allRows,
  bestRoute,
}: {
  allRows: ScheduleRow[];
  bestRoute: RollRoute | null;
}) {
  const bestIds = new Set(bestRoute?.steps.map((s) => s.race_id) ?? []);

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-gray-50 text-xs text-gray-500">
            <th className="px-2 py-2 border-b text-left">締切</th>
            <th className="px-2 py-2 border-b text-left">場</th>
            <th className="px-2 py-2 border-b">R</th>
            <th className="px-2 py-2 border-b">判定</th>
            <th className="px-2 py-2 border-b text-right">conf</th>
            <th className="px-2 py-2 border-b text-right">gap</th>
            <th className="px-2 py-2 border-b">pick</th>
            <th className="px-2 py-2 border-b">展示</th>
            <th className="px-2 py-2 border-b">状態</th>
          </tr>
        </thead>
        <tbody>
          {allRows.map((r, i) => {
            const inBest = bestIds.has(r.race_id);
            const step = bestRoute?.steps.find((s) => s.race_id === r.race_id);
            return (
              <tr
                key={`${r.race_id}-${i}`}
                className={`border-b last:border-b-0 ${
                  inBest
                    ? "bg-amber-50 font-medium"
                    : "hover:bg-gray-50"
                }`}
              >
                <td className="px-2 py-1.5 font-mono text-xs whitespace-nowrap">
                  {fmtTime(r.close_time)}
                  {inBest && step && (
                    <span className="ml-1 text-xs text-amber-600 font-bold">
                      [STEP{bestRoute!.steps.indexOf(step) + 1}]
                    </span>
                  )}
                </td>
                <td className="px-2 py-1.5">{r.stadium}</td>
                <td className="px-2 py-1.5 text-center">{r.race_no}</td>
                <td className="px-2 py-1.5 text-center">
                  <DecisionBadge row={r} />
                </td>
                <td className="px-2 py-1.5 text-right font-mono text-xs">
                  {r.confidence?.toFixed(1) ?? (
                    <span className="text-gray-300">-</span>
                  )}
                </td>
                <td className="px-2 py-1.5 text-right font-mono text-xs">
                  {r.gap?.toFixed(1) ?? (
                    <span className="text-gray-300">-</span>
                  )}
                </td>
                <td className="px-2 py-1.5 font-mono text-xs">
                  {r.pick ?? <span className="text-gray-300">-</span>}
                </td>
                <td className="px-2 py-1.5 text-center">
                  {r.decision && (
                    <span
                      className={`text-xs px-1 rounded ${
                        r.has_exhibition
                          ? "bg-green-100 text-green-700"
                          : "bg-yellow-50 text-yellow-600"
                      }`}
                    >
                      {r.has_exhibition ? "済" : "未"}
                    </span>
                  )}
                </td>
                <td className="px-2 py-1.5 text-center">
                  {r.status === "scheduled" ? (
                    <span className="text-xs bg-green-100 text-green-700 px-1 rounded">
                      締切前
                    </span>
                  ) : r.status === "finished" ? (
                    <span className="text-xs text-gray-400">終了</span>
                  ) : (
                    <span className="text-xs text-yellow-600">結果待</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── メインコンポーネント ──────────────────────────────────────────────────────

export default function RollPlanClient({
  plan,
  today,
}: {
  plan: RollPlan;
  today: string;
}) {
  const [tab, setTab] = useState<Tab>("best");
  const [showSkip, setShowSkip] = useState(false);

  const TABS: { key: Tab; label: string; count?: number }[] = [
    { key: "best",       label: "最有力ルート" },
    { key: "backup",     label: "予備ルート",    count: plan.backupRoutes.length },
    { key: "candidates", label: "候補一覧",      count: plan.allCandidates.length },
    { key: "timeline",   label: "タイムライン",  count: plan.allRows.length },
  ];

  return (
    <main className="max-w-4xl mx-auto px-4 py-6">
      {/* ── ヘッダ ────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-xl font-bold">転がし計画</h1>
        <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">
          {today}
        </span>
      </div>
      <div className="flex gap-3 text-xs text-gray-400 mb-4">
        <a href="/ops"      className="underline hover:text-gray-600">運用</a>
        <a href="/schedule" className="underline hover:text-gray-600">スケジュール</a>
        <a href="/debug"    className="underline hover:text-gray-600">デバッグ</a>
      </div>

      {/* ── サマリカード ──────────────────────────────── */}
      <div className="grid grid-cols-4 sm:grid-cols-8 gap-2 mb-4">
        <div className="col-span-2 bg-white border rounded-lg p-2 text-center">
          <div className="text-xs text-gray-400">全レース</div>
          <div className="text-xl font-bold">{plan.allRows.length}</div>
        </div>
        <div className="col-span-2 bg-white border rounded-lg p-2 text-center">
          <div className="text-xs text-gray-400">評価済み</div>
          <div className="text-xl font-bold">{plan.evaluatedCount}</div>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-lg p-2 text-center">
          <div className="text-xs text-red-400">BUY</div>
          <div className="text-xl font-bold text-red-700">{plan.buyCount}</div>
        </div>
        <div className="bg-orange-50 border border-orange-200 rounded-lg p-2 text-center">
          <div className="text-xs text-orange-400">CAND</div>
          <div className="text-xl font-bold text-orange-700">{plan.candidateCount}</div>
        </div>
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-2 text-center">
          <div className="text-xs text-blue-400">WATCH</div>
          <div className="text-xl font-bold text-blue-700">{plan.watchCount}</div>
        </div>
        <div className="bg-gray-50 border rounded-lg p-2 text-center">
          <div className="text-xs text-gray-400">SKIP</div>
          <div className="text-xl font-bold text-gray-500">{plan.skipCount}</div>
        </div>
      </div>

      {/* ── ルート統計 ────────────────────────────────── */}
      <div className="flex flex-wrap gap-2 mb-4 text-xs">
        <span className="bg-amber-50 border border-amber-200 text-amber-700 px-2 py-1 rounded-full">
          4回転がし候補ルート {plan.backupRoutes.length + (plan.bestRoute ? 1 : 0)} 件
        </span>
        {plan.bestRoute && (
          <>
            <span className="bg-white border text-gray-600 px-2 py-1 rounded-full">
              最有力ルート開始 {fmtTime(plan.bestRoute.steps[0].close_time)}
            </span>
            <span className="bg-white border text-gray-600 px-2 py-1 rounded-full">
              終了 {fmtTime(plan.bestRoute.steps[3].close_time)}
            </span>
          </>
        )}
        <span className="bg-white border text-gray-600 px-2 py-1 rounded-full">
          想定初期投資額 ¥100
        </span>
      </div>

      {/* ── 判定バナー ────────────────────────────────── */}
      <div className="mb-5">
        <JudgmentBanner judgment={plan.judgment} text={plan.judgeText} />
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
            {t.count !== undefined && (
              <span
                className={`text-xs px-1.5 py-0.5 rounded-full ${
                  tab === t.key
                    ? "bg-blue-100 text-blue-600"
                    : "bg-gray-100 text-gray-400"
                }`}
              >
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── 最有力ルート ──────────────────────────────── */}
      {tab === "best" && (
        <section>
          {plan.bestRoute ? (
            <>
              <RouteCard
                route={plan.bestRoute}
                label="最有力ルート"
                defaultOpen
              />
              {plan.backupRoutes.length === 0 && (
                <p className="text-xs text-gray-400 text-center mt-2">
                  予備ルートはありません
                </p>
              )}
            </>
          ) : (
            <div className="text-center py-12">
              <p className="text-gray-500 font-medium">
                4回転がし候補ルートが見つかりません
              </p>
              <p className="text-xs text-gray-400 mt-1">
                buy/candidate/watch のレースが4件以上、各30分以上の間隔が必要です
              </p>
            </div>
          )}
        </section>
      )}

      {/* ── 予備ルート ────────────────────────────────── */}
      {tab === "backup" && (
        <section>
          {plan.backupRoutes.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-500 font-medium">予備ルートはありません</p>
              <p className="text-xs text-gray-400 mt-1">
                候補レース数が少ないか、条件を満たす組み合わせが1件のみです
              </p>
            </div>
          ) : (
            <>
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4 text-xs text-blue-700">
                最有力ルートの第1レースが条件未達・展示で弱くなった場合の代替候補です。
              </div>
              {plan.backupRoutes.map((route, i) => (
                <RouteCard
                  key={route.id}
                  route={route}
                  label={`予備ルート ${i + 1}`}
                  defaultOpen={i === 0}
                />
              ))}
            </>
          )}
        </section>
      )}

      {/* ── 候補一覧 ──────────────────────────────────── */}
      {tab === "candidates" && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="text-sm font-medium">
                buy / candidate / watch の候補レース
              </p>
              <p className="text-xs text-blue-600 mt-0.5">
                ※ WATCH は実投票対象外（検証候補）
              </p>
            </div>
            <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer">
              <input
                type="checkbox"
                checked={showSkip}
                onChange={(e) => setShowSkip(e.target.checked)}
                className="rounded"
              />
              skip も表示
            </label>
          </div>
          <CandidateTable
            candidates={plan.allCandidates}
            showSkip={showSkip}
            allRows={plan.allRows}
          />
        </section>
      )}

      {/* ── タイムライン ──────────────────────────────── */}
      {tab === "timeline" && (
        <section>
          <p className="text-xs text-gray-400 mb-2">
            全 {plan.allRows.length} レース｜締切時刻順
            {plan.bestRoute && (
              <span className="ml-2 text-amber-600">
                ★ 最有力ルートのステップを強調表示
              </span>
            )}
          </p>
          <TimelineTable allRows={plan.allRows} bestRoute={plan.bestRoute} />
        </section>
      )}
    </main>
  );
}
