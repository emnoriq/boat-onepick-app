import { getStats } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export default async function StatsPage() {
  const stats = await getStats();

  const roiNum = stats ? parseFloat(stats.roi) : 0;

  return (
    <main className="max-w-lg mx-auto px-4 py-6">
      <h1 className="text-xl font-bold mb-1">長期統計</h1>
      <p className="text-xs text-gray-400 mb-4">結果が確定したレースのみ集計</p>

      {!stats || stats.total === 0 ? (
        <p className="text-gray-400 text-sm">まだデータがありません</p>
      ) : (
        <div className="space-y-3">

          <StatRow label="対象レース数" value={`${stats.total} レース`} />
          <StatRow label="的中数"       value={`${stats.hitCount} レース`} />
          <StatRow label="的中率（全体）" value={`${stats.hitRate}%`} highlight />

          <div className="pt-2 border-t">
            <p className="text-xs text-gray-400 mb-2">ランク別</p>
            <StatRow
              label="Sランク（buy）的中率"
              value={
                stats.sCount > 0
                  ? `${((stats.sHit / stats.sCount) * 100).toFixed(1)}%　(${stats.sHit} / ${stats.sCount})`
                  : "データなし"
              }
              highlight
            />
            <StatRow
              label="Aランク（candidate）的中率"
              value={
                stats.aCount > 0
                  ? `${((stats.aHit / stats.aCount) * 100).toFixed(1)}%　(${stats.aHit} / ${stats.aCount})`
                  : "データなし"
              }
            />
          </div>

          <div className="pt-2 border-t">
            <p className="text-xs text-gray-400 mb-2">回収率（1点100円）</p>
            <StatRow label="投資額合計"  value={`¥${stats.investTotal.toLocaleString()}`} />
            <StatRow label="払戻金合計"  value={`¥${stats.payoutTotal.toLocaleString()}`} />
            <StatRow
              label="回収率"
              value={`${stats.roi}%`}
              highlight={roiNum >= 100}
              warn={roiNum > 0 && roiNum < 100}
            />
          </div>
        </div>
      )}

      <div className="mt-8 flex gap-4 justify-center text-xs text-gray-400">
        <a href="/ops"   className="underline hover:text-gray-600">運用チェック</a>
        <a href="/debug" className="underline hover:text-gray-600">デバッグ一覧</a>
      </div>
    </main>
  );
}

function StatRow({
  label,
  value,
  highlight,
  warn,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  warn?: boolean;
}) {
  return (
    <div className="flex justify-between items-center border-b pb-2">
      <span className="text-sm text-gray-600">{label}</span>
      <span
        className={`font-bold ${
          highlight
            ? "text-blue-600 text-lg"
            : warn
            ? "text-orange-500"
            : "text-gray-800"
        }`}
      >
        {value}
      </span>
    </div>
  );
}
