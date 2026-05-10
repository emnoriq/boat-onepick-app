import { getDebugPredictions } from "@/lib/supabase";

export const dynamic = "force-dynamic";

function todayJST(): string {
  return new Date().toLocaleDateString("ja-JP", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).replace(/\//g, "-");
}

function isValidDate(s: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(s) && !isNaN(Date.parse(s));
}

function offsetDate(base: string, days: number): string {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function DecisionBadge({ decision, isWatch }: { decision: string; isWatch: boolean }) {
  if (decision === "buy")
    return <span className="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 font-bold">buy</span>;
  if (decision === "candidate")
    return <span className="px-1.5 py-0.5 rounded text-xs bg-orange-100 text-orange-700 font-semibold">candidate</span>;
  if (isWatch)
    return (
      <span className="px-1.5 py-0.5 rounded text-xs bg-blue-100 text-blue-700 font-semibold">
        watch
      </span>
    );
  return <span className="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-500">skip</span>;
}

function HitBadge({ hit }: { hit: boolean | null }) {
  if (hit === null) return <span className="text-xs text-gray-300">未確定</span>;
  return hit
    ? <span className="text-xs bg-green-100 text-green-700 font-bold px-1 rounded">的中</span>
    : <span className="text-xs bg-gray-100 text-gray-500 px-1 rounded">不的中</span>;
}

type Props = { searchParams: { date?: string } };

export default async function DebugPage({ searchParams }: Props) {
  const today = todayJST();
  const reqDate = searchParams.date;
  const date = reqDate && isValidDate(reqDate) ? reqDate : today;
  const rows = await getDebugPredictions(date);

  const byDecision = { buy: 0, candidate: 0, watch: 0, skip: 0 };
  for (const r of rows) {
    if (r.decision === "buy") byDecision.buy++;
    else if (r.decision === "candidate") byDecision.candidate++;
    else if (r.is_watch) byDecision.watch++;
    else byDecision.skip++;
  }

  const maxConf = rows.length > 0 ? Math.max(...rows.map(r => Number(r.confidence))) : 0;
  const avgConf = rows.length > 0
    ? (rows.reduce((s, r) => s + Number(r.confidence), 0) / rows.length).toFixed(1)
    : "0.0";
  const exhibitionCount = rows.filter(r => r.has_exhibition).length;
  const hitRows = rows.filter(r => r.prediction_hit !== null);
  const hitCount = hitRows.filter(r => r.prediction_hit).length;

  return (
    <main className="max-w-6xl mx-auto px-4 py-6">
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-xl font-bold">デバッグ：全予想一覧</h1>
        <div className="flex gap-3 text-xs text-blue-500">
          <a href="/ops"       className="underline hover:text-blue-700">運用チェック</a>
          <a href="/roll-plan" className="underline hover:text-blue-700">転がし計画</a>
          <a href="/schedule"  className="underline hover:text-blue-700">スケジュール</a>
        </div>
      </div>

      {/* 日付ナビゲーション */}
      <div className="flex items-center gap-1 mb-3">
        <a
          href={`/debug?date=${offsetDate(date, -1)}`}
          className="px-2 py-1 text-xs border rounded hover:bg-gray-50 text-gray-500"
        >← 前日</a>
        <span className={`text-xs px-2 py-1 rounded font-mono ${
          date === today ? "bg-blue-100 text-blue-700 font-bold" : "bg-gray-100 text-gray-600"
        }`}>
          {date}{date === today && " (今日)"}
        </span>
        <a
          href={`/debug?date=${offsetDate(date, 1)}`}
          className={`px-2 py-1 text-xs border rounded hover:bg-gray-50 text-gray-500 ${
            date >= today ? "opacity-40 pointer-events-none" : ""
          }`}
        >翌日 →</a>
      </div>

      <p className="text-xs text-gray-400 mb-4">全 {rows.length} 件（confidence 降順）</p>

      {/* 判定基準 */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-4 text-sm">
        <p className="font-semibold text-blue-800 mb-2">現在の判定基準（v5 / 2026-05-10 バックテスト調整済み）</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
          <div className="bg-red-100 rounded p-2">
            <p className="font-bold text-red-700">Sランク BUY</p>
            <p className="text-red-600">confidence ≥ 67</p>
            <p className="text-red-600">gap ≥ 10点</p>
            <p className="text-red-500 mt-0.5 font-semibold">展示確認必須</p>
          </div>
          <div className="bg-orange-100 rounded p-2">
            <p className="font-bold text-orange-700">Aランク CANDIDATE</p>
            <p className="text-orange-600">confidence ≥ 59</p>
            <p className="text-orange-600">gap ≥ 7点</p>
            <p className="text-orange-500 mt-0.5 font-semibold">展示確認必須</p>
          </div>
          <div className="bg-blue-100 rounded p-2">
            <p className="font-bold text-blue-700">Bランク WATCH</p>
            <p className="text-blue-600">confidence ≥ 55</p>
            <p className="text-blue-600">gap ≥ 7点</p>
            <p className="text-blue-500 mt-0.5">検証候補・投票対象外</p>
          </div>
          <div className="bg-gray-100 rounded p-2">
            <p className="font-bold text-gray-600">SKIP</p>
            <p className="text-gray-500">それ以外（荒天も含む）</p>
          </div>
        </div>
        <p className="text-xs text-gray-500 mt-2">
          confidence = avg_top3 × (1 + gap/<strong>150</strong>) × 1号艇補正
          ／ モータースコア艦隊相対評価・展示タイム13点(スケール33)・1号艇コース3以降進入は0.85ペナルティ
        </p>
      </div>

      {/* サマリー */}
      <div className="flex flex-wrap gap-3 mb-4 text-sm">
        <span className="bg-red-100 text-red-700 px-2 py-0.5 rounded">buy: {byDecision.buy}</span>
        <span className="bg-orange-100 text-orange-700 px-2 py-0.5 rounded">candidate: {byDecision.candidate}</span>
        <span className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded">watch: {byDecision.watch}</span>
        <span className="bg-gray-100 text-gray-500 px-2 py-0.5 rounded">skip: {byDecision.skip}</span>
        <span className="bg-white border px-2 py-0.5 rounded text-gray-600">最大 conf: {maxConf.toFixed(1)}</span>
        <span className="bg-white border px-2 py-0.5 rounded text-gray-600">平均 conf: {avgConf}</span>
        <span className="bg-white border px-2 py-0.5 rounded text-gray-600">
          展示済み: {exhibitionCount} / {rows.length}
        </span>
        {hitRows.length > 0 && (
          <span className="bg-green-50 border border-green-200 text-green-700 px-2 py-0.5 rounded">
            的中: {hitCount} / {hitRows.length} ({hitRows.length > 0 ? ((hitCount / hitRows.length) * 100).toFixed(1) : "-"}%)
          </span>
        )}
      </div>

      {/* テーブル */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-100 text-left text-xs">
              <th className="px-2 py-2 border">場</th>
              <th className="px-2 py-2 border">R</th>
              <th className="px-2 py-2 border">締切(JST)</th>
              <th className="px-2 py-2 border">conf</th>
              <th className="px-2 py-2 border">gap</th>
              <th className="px-2 py-2 border">展示</th>
              <th className="px-2 py-2 border">decision</th>
              <th className="px-2 py-2 border">pick</th>
              <th className="px-2 py-2 border">結果</th>
              <th className="px-2 py-2 border">的中</th>
              <th className="px-2 py-2 border">払戻</th>
              <th className="px-2 py-2 border">人気</th>
              <th className="px-2 py-2 border">reason</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr
                key={`${r.race_id}-${i}`}
                className="hover:bg-gray-50 cursor-pointer"
                onClick={() => { window.location.href = `/races/${r.race_id}`; }}
              >
                <td className="px-2 py-1.5 border">{r.stadium}</td>
                <td className="px-2 py-1.5 border text-center">{r.race_no}</td>
                <td className="px-2 py-1.5 border text-center">
                  {r.close_time
                    ? new Date(r.close_time).toLocaleTimeString("ja-JP", {
                        timeZone: "Asia/Tokyo",
                        hour: "2-digit",
                        minute: "2-digit",
                        hour12: false,
                      })
                    : "-"}
                </td>
                <td className="px-2 py-1.5 border text-right font-mono">
                  {Number(r.confidence).toFixed(1)}
                </td>
                <td className="px-2 py-1.5 border text-right font-mono">
                  {r.gap !== null ? r.gap.toFixed(1) : "-"}
                </td>
                <td className="px-2 py-1.5 border text-center">
                  <span className={`text-xs px-1 rounded ${r.has_exhibition ? "bg-green-100 text-green-700" : "bg-yellow-50 text-yellow-600"}`}>
                    {r.has_exhibition ? "展示済" : "朝のみ"}
                  </span>
                </td>
                <td className="px-2 py-1.5 border text-center">
                  <DecisionBadge decision={r.decision} isWatch={r.is_watch} />
                </td>
                <td className="px-2 py-1.5 border font-mono">{r.pick}</td>
                <td className="px-2 py-1.5 border font-mono text-center">
                  {r.trifecta_result ?? <span className="text-gray-300">-</span>}
                </td>
                <td className="px-2 py-1.5 border text-center">
                  <HitBadge hit={r.prediction_hit} />
                </td>
                <td className="px-2 py-1.5 border text-right font-mono">
                  {r.payout !== null ? `¥${r.payout.toLocaleString()}` : <span className="text-gray-300">-</span>}
                </td>
                <td className="px-2 py-1.5 border text-center">
                  {r.popularity ?? <span className="text-gray-300">-</span>}
                </td>
                <td className="px-2 py-1.5 border text-xs text-gray-500 max-w-xs">
                  {r.reason?.split("\n").filter(Boolean).join(" / ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {rows.length === 0 && (
        <p className="text-center text-gray-400 py-12">本日の予想データがありません</p>
      )}
    </main>
  );
}
