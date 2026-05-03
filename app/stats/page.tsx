import { getStats } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export default async function StatsPage() {
  const stats = await getStats();

  return (
    <main className="max-w-lg mx-auto px-4 py-6">
      <h1 className="text-xl font-bold mb-1">検証データ</h1>
      <p className="text-xs text-gray-400 mb-4">結果が確定したレースのみ集計</p>

      {!stats || stats.total === 0 ? (
        <p className="text-gray-400 text-sm">まだデータがありません</p>
      ) : (
        <div className="space-y-3">
          <StatRow label="対象レース数" value={`${stats.total} レース`} />
          <StatRow label="的中数" value={`${stats.hitCount} レース`} />
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
        </div>
      )}

      <div className="mt-8 text-center">
        <a href="/debug" className="text-xs text-gray-400 underline hover:text-gray-600">
          デバッグ一覧を見る
        </a>
      </div>
    </main>
  );
}

function StatRow({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="flex justify-between items-center border-b pb-2">
      <span className="text-sm text-gray-600">{label}</span>
      <span
        className={`font-bold ${
          highlight ? "text-blue-600 text-lg" : "text-gray-800"
        }`}
      >
        {value}
      </span>
    </div>
  );
}
