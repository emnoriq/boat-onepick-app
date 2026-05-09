import { getStats } from "@/lib/supabase";

export const dynamic = "force-dynamic";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border p-4 mb-4">
      <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3">{title}</h2>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function Row({ label, value, highlight, warn, sub }: {
  label: string; value: string; highlight?: boolean; warn?: boolean; sub?: string;
}) {
  return (
    <div className="flex justify-between items-baseline border-b pb-1.5">
      <span className="text-sm text-gray-600">{label}</span>
      <span className={`font-bold tabular-nums ${highlight ? "text-blue-600 text-lg" : warn ? "text-orange-500" : "text-gray-800"}`}>
        {value}
        {sub && <span className="text-xs font-normal text-gray-400 ml-1">{sub}</span>}
      </span>
    </div>
  );
}

function TierCard({ color, label, count, hit, rate, roi, isBet = true }: {
  color: string; label: string; count: number; hit: number; rate: string; roi?: string; isBet?: boolean;
}) {
  const roiNum = parseFloat(roi ?? "0");
  return (
    <div className={`rounded-lg border p-3 ${color}`}>
      <div className="text-xs font-bold mb-1">{label}</div>
      <div className="text-2xl font-black">{count > 0 ? `${rate}%` : "-"}</div>
      <div className="text-xs mt-0.5">{hit}/{count} 的中</div>
      {isBet ? (
        <div className={`text-xs mt-0.5 font-semibold ${roiNum >= 100 ? "text-green-700" : "text-gray-500"}`}>
          回収率 {count > 0 ? `${roi}%` : "-"}
        </div>
      ) : (
        <div className="text-xs mt-0.5 text-gray-400">非投票対象</div>
      )}
    </div>
  );
}

export default async function StatsPage() {
  const stats = await getStats();
  const roiNum = stats ? parseFloat(stats.roi) : 0;

  return (
    <main className="max-w-2xl mx-auto px-4 py-6">
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-xl font-bold">長期統計</h1>
        <span className="text-xs text-gray-400">結果確定レースのみ</span>
      </div>
      <p className="text-xs text-gray-400 mb-4">
        三連複1点 100円想定 ／ buy&amp;candidate のみ投票対象
      </p>

      {!stats || stats.total === 0 ? (
        <p className="text-gray-400 text-sm text-center py-12">まだデータがありません</p>
      ) : (
        <>
          {/* ── 全体サマリー ── */}
          <Section title="全体">
            <Row label="結果確定レース数" value={`${stats.total} 件`} />
            <Row label="的中数"           value={`${stats.hitCount} 件`} />
            <Row label="的中率（全体）"   value={`${stats.hitRate}%`} highlight />
            <Row label="投資額"           value={`¥${stats.investTotal.toLocaleString()}`} sub="1点100円" />
            <Row label="払戻合計"         value={`¥${stats.payoutTotal.toLocaleString()}`} />
            <Row
              label="仮回収率"
              value={`${stats.roi}%`}
              highlight={roiNum >= 100}
              warn={roiNum > 0 && roiNum < 100}
            />
          </Section>

          {/* ── ランク別 ── */}
          <Section title="ランク別的中率">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <TierCard color="bg-red-50 border-red-200 text-red-700"    label="BUY (S)"       count={stats.sCount}     hit={stats.sHit}     rate={stats.sRate}     roi={stats.sRoi} />
              <TierCard color="bg-orange-50 border-orange-200 text-orange-700" label="CANDIDATE (A)" count={stats.aCount} hit={stats.aHit} rate={stats.aRate} roi={stats.aRoi} />
              <TierCard color="bg-blue-50 border-blue-200 text-blue-700" label="WATCH (B)"     count={stats.watchCount} hit={stats.watchHit} rate={stats.watchRate}  isBet={false} />
              <TierCard color="bg-gray-50 border-gray-200 text-gray-500" label="SKIP (C)"      count={stats.skipCount}  hit={stats.skipHit}  rate={tierRateStr(stats.skipCount, stats.skipHit)} isBet={false} />
            </div>
          </Section>

          {/* ── confidence帯別 ── */}
          <Section title="confidence 帯別的中率">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-gray-400 border-b">
                    <th className="text-left py-1">信頼度</th>
                    <th className="text-right py-1">件数</th>
                    <th className="text-right py-1">的中</th>
                    <th className="text-right py-1">的中率</th>
                    <th className="text-right py-1">回収率</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.confBands.map(b => (
                    <tr key={b.label} className="border-b last:border-0">
                      <td className="py-1.5 font-mono text-xs text-gray-600">{b.label}</td>
                      <td className="py-1.5 text-right">{b.count}</td>
                      <td className="py-1.5 text-right">{b.hit}</td>
                      <td className={`py-1.5 text-right font-bold ${parseFloat(b.rate) >= 30 ? "text-green-600" : "text-gray-700"}`}>
                        {b.count > 0 ? `${b.rate}%` : "-"}
                      </td>
                      <td className={`py-1.5 text-right font-bold ${parseFloat(b.roi) >= 100 ? "text-green-600" : parseFloat(b.roi) > 0 ? "text-orange-500" : "text-gray-400"}`}>
                        {b.count > 0 ? `${b.roi}%` : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-gray-400 mt-2">
              ※ confidence と的中率の相関が確認できれば閾値を再調整します（MVP 30日後）
            </p>
          </Section>

          {/* ── 展示データあり vs なし ── */}
          <Section title="展示データ有無別">
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                <div className="text-xs font-bold text-green-700 mb-1">展示あり（直前更新済み）</div>
                <div className="text-xl font-black text-green-700">
                  {stats.withExCount > 0 ? `${stats.withExRate}%` : "-"}
                </div>
                <div className="text-xs text-green-600">{stats.withExHit}/{stats.withExCount} 的中</div>
                <div className="text-xs text-green-600">回収率 {stats.withExCount > 0 ? `${stats.withExRoi}%` : "-"}</div>
              </div>
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
                <div className="text-xs font-bold text-yellow-700 mb-1">展示なし（朝スキャンのみ）</div>
                <div className="text-xl font-black text-yellow-700">
                  {stats.withoutExCount > 0 ? `${stats.withoutExRate}%` : "-"}
                </div>
                <div className="text-xs text-yellow-600">{stats.withoutExHit}/{stats.withoutExCount} 的中</div>
                <div className="text-xs text-yellow-600">回収率 {stats.withoutExCount > 0 ? `${stats.withoutExRoi}%` : "-"}</div>
              </div>
            </div>
          </Section>
        </>
      )}

      <div className="flex gap-4 justify-center text-xs text-gray-400 mt-4">
        <a href="/ops"   className="underline hover:text-gray-600">運用チェック</a>
        <a href="/debug" className="underline hover:text-gray-600">デバッグ一覧</a>
        <a href="/schedule" className="underline hover:text-gray-600">スケジュール</a>
      </div>
    </main>
  );
}

function tierRateStr(count: number, hit: number): string {
  return count > 0 ? ((hit / count) * 100).toFixed(1) : "0.0";
}
