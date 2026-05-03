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

const DECISION_STYLE: Record<string, string> = {
  buy:       "bg-red-100 text-red-700 font-bold",
  candidate: "bg-orange-100 text-orange-700 font-semibold",
  skip:      "bg-gray-100 text-gray-500",
};

function HitBadge({ hit }: { hit: boolean | null }) {
  if (hit === null) return <span className="text-xs text-gray-300">未確定</span>;
  return hit
    ? <span className="text-xs bg-green-100 text-green-700 font-bold px-1 rounded">的中</span>
    : <span className="text-xs bg-gray-100 text-gray-500 px-1 rounded">不的中</span>;
}

export default async function DebugPage() {
  const today = todayJST();
  const rows = await getDebugPredictions(today);

  const byDecision = { buy: 0, candidate: 0, skip: 0 };
  for (const r of rows) byDecision[r.decision] = (byDecision[r.decision] ?? 0) + 1;

  const maxConf = rows.length > 0 ? Math.max(...rows.map(r => Number(r.confidence))) : 0;
  const avgConf = rows.length > 0
    ? (rows.reduce((s, r) => s + Number(r.confidence), 0) / rows.length).toFixed(1)
    : "0.0";
  const exhibitionCount = rows.filter(r => r.has_exhibition).length;
  const hitRows = rows.filter(r => r.prediction_hit !== null);
  const hitCount = hitRows.filter(r => r.prediction_hit).length;

  return (
    <main className="max-w-6xl mx-auto px-4 py-6">
      <h1 className="text-xl font-bold mb-1">デバッグ：全予想一覧</h1>
      <p className="text-xs text-gray-400 mb-4">{today}　上位 {rows.length} 件（confidence 降順）</p>

      {/* 判定基準 */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-4 text-sm">
        <p className="font-semibold text-blue-800 mb-2">現在の判定基準（暫定 — MVP30日検証後に再調整）</p>
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className="bg-red-100 rounded p-2">
            <p className="font-bold text-red-700">Sランク BUY</p>
            <p className="text-red-600">confidence ≥ 70</p>
            <p className="text-red-600">gap ≥ 10点</p>
          </div>
          <div className="bg-orange-100 rounded p-2">
            <p className="font-bold text-orange-700">Aランク CANDIDATE</p>
            <p className="text-orange-600">confidence ≥ 62</p>
            <p className="text-orange-600">gap ≥ 7点</p>
          </div>
          <div className="bg-gray-100 rounded p-2">
            <p className="font-bold text-gray-600">SKIP</p>
            <p className="text-gray-500">それ以外（荒天も含む）</p>
          </div>
        </div>
        <p className="text-xs text-gray-500 mt-2">
          confidence = avg_top3_score × (1 + gap/200) ／ gap = 3位スコア − 4位スコア
        </p>
      </div>

      {/* サマリー */}
      <div className="flex flex-wrap gap-3 mb-4 text-sm">
        <span className="bg-red-100 text-red-700 px-2 py-0.5 rounded">buy: {byDecision.buy}</span>
        <span className="bg-orange-100 text-orange-700 px-2 py-0.5 rounded">candidate: {byDecision.candidate}</span>
        <span className="bg-gray-100 text-gray-500 px-2 py-0.5 rounded">skip: {byDecision.skip}</span>
        <span className="bg-white border px-2 py-0.5 rounded text-gray-600">最大 conf: {maxConf.toFixed(1)}</span>
        <span className="bg-white border px-2 py-0.5 rounded text-gray-600">平均 conf: {avgConf}</span>
        <span className="bg-white border px-2 py-0.5 rounded text-gray-600">
          展示済み: {exhibitionCount} / {rows.length}
        </span>
        {hitRows.length > 0 && (
          <span className="bg-green-50 border border-green-200 text-green-700 px-2 py-0.5 rounded">
            的中: {hitCount} / {hitRows.length}
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
              <tr key={`${r.race_id}-${i}`} className="hover:bg-gray-50">
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
                  <span className={`px-1.5 py-0.5 rounded text-xs ${DECISION_STYLE[r.decision] ?? ""}`}>
                    {r.decision}
                  </span>
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
