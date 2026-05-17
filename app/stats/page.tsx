import { getStats } from "@/lib/supabase";

export const dynamic = "force-dynamic";

function BigStat({ label, value, sub, gradient = false }: {
  label: string; value: string; sub?: string; gradient?: boolean;
}) {
  return (
    <div className="bg-white rounded-2xl p-4 shadow-sm text-center">
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      <p
        className={`text-3xl font-black ${gradient ? "" : "text-gray-800"}`}
        style={gradient ? { background: "linear-gradient(to right,#FF6B6B,#FF8E53)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" } : {}}
      >
        {value}
      </p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

function RateBar({ rate, label, hit, count }: { rate: string; label: string; hit: number; count: number }) {
  const r = parseFloat(rate);
  return (
    <div className="mb-3">
      <div className="flex justify-between items-center mb-1">
        <span className="text-sm font-medium text-gray-700">{label}</span>
        <span className={`text-sm font-black tabular-nums ${r >= 35 ? "text-rose-500" : r >= 25 ? "text-orange-400" : "text-gray-400"}`}>
          {count > 0 ? `${rate}%` : "-"}
        </span>
      </div>
      <div className="h-2 rounded-full overflow-hidden" style={{ backgroundColor: "#FFF0E8" }}>
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${Math.min(100, r * 2)}%`,
            background: r >= 35 ? "linear-gradient(to right,#FF6B6B,#FF8E53)" :
                        r >= 25 ? "linear-gradient(to right,#FF8E53,#FFBE0B)" : "#e5e7eb",
          }}
        />
      </div>
      <p className="text-xs text-gray-400 mt-0.5">{hit}/{count} 的中</p>
    </div>
  );
}

function CheckItem({ ok, label, value, note }: { ok: boolean; label: string; value: string; note: string }) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-orange-50 last:border-0">
      <span className={`text-lg shrink-0 mt-0.5 ${ok ? "" : "opacity-30"}`}>{ok ? "✅" : "⭕"}</span>
      <div className="flex-1 min-w-0">
        <div className="flex justify-between items-center">
          <span className={`text-sm font-medium ${ok ? "text-gray-800" : "text-gray-400"}`}>{label}</span>
          <span className={`text-sm font-black tabular-nums shrink-0 ml-2 ${ok ? "text-rose-500" : "text-gray-400"}`}>{value}</span>
        </div>
        <p className="text-xs text-gray-400 mt-0.5">{note}</p>
      </div>
    </div>
  );
}

export default async function StatsPage() {
  const stats = await getStats();
  const roiNum = stats ? parseFloat(stats.roi) : 0;

  return (
    <main className="max-w-lg mx-auto px-4 py-5">

      {/* ── ヘッダー ───────────────────────────────── */}
      <div
        className="rounded-3xl p-5 mb-5 text-white shadow-lg"
        style={{ background: "linear-gradient(135deg, #FF6B6B 0%, #FF8E53 60%, #FFBE0B 100%)" }}
      >
        <p className="text-white/60 text-xs mb-1">累計パフォーマンス</p>
        <h1 className="text-2xl font-black mb-3">長期統計</h1>
        {stats && stats.total > 0 ? (
          <div className="flex gap-3">
            <div className="bg-white/25 rounded-2xl px-4 py-2 text-center flex-1">
              <div className="text-3xl font-black">{stats.hitRate}%</div>
              <div className="text-xs text-white/70">全体的中率</div>
            </div>
            <div className="bg-white/25 rounded-2xl px-4 py-2 text-center flex-1">
              <div className={`text-3xl font-black ${roiNum >= 100 ? "text-yellow-300" : ""}`}>{stats.roi}%</div>
              <div className="text-xs text-white/70">回収率</div>
            </div>
            <div className="bg-white/15 rounded-2xl px-4 py-2 text-center flex-1">
              <div className="text-3xl font-black">{stats.total}</div>
              <div className="text-xs text-white/70">確定レース</div>
            </div>
          </div>
        ) : (
          <div className="bg-white/20 rounded-2xl px-4 py-3 text-sm font-bold">
            データ収集中…
          </div>
        )}
      </div>

      {!stats || stats.total === 0 ? (
        <p className="text-center text-gray-400 py-12">まだデータがありません</p>
      ) : (
        <>
          {/* ── 投資サマリー ─────────────────────────── */}
          <div className="grid grid-cols-2 gap-3 mb-5">
            <BigStat label="投資額合計" value={`¥${stats.investTotal.toLocaleString()}`} sub="1点100円" />
            <BigStat label="払戻合計"   value={`¥${stats.payoutTotal.toLocaleString()}`} gradient={roiNum >= 100} />
          </div>

          {/* ── ランク別的中率 ─────────────────────── */}
          <div className="bg-white rounded-3xl p-5 shadow-sm mb-4">
            <h2 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4">ランク別的中率</h2>
            <RateBar label="🎯 BUY（投票確定）"       rate={stats.sRate} hit={stats.sHit} count={stats.sCount} />
            <RateBar label="📌 CANDIDATE（投票検討）"  rate={stats.aRate} hit={stats.aHit} count={stats.aCount} />
            <RateBar label="👁 WATCH"                  rate={stats.watchRate} hit={stats.watchHit} count={stats.watchCount} />

            <div className="mt-3 pt-3 border-t border-orange-50">
              <div className="flex justify-between text-xs text-gray-400">
                <span>BUY 回収率</span>
                <span className={`font-bold ${parseFloat(stats.sRoi) >= 100 ? "text-rose-500" : "text-gray-500"}`}>{stats.sRoi}%</span>
              </div>
              <div className="flex justify-between text-xs text-gray-400 mt-1">
                <span>CANDIDATE 回収率</span>
                <span className={`font-bold ${parseFloat(stats.aRoi) >= 100 ? "text-rose-500" : "text-gray-500"}`}>{stats.aRoi}%</span>
              </div>
            </div>
          </div>

          {/* ── confidence 帯別 ──────────────────────── */}
          <div className="bg-white rounded-3xl p-5 shadow-sm mb-4">
            <h2 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4">信頼度帯別</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-gray-400 border-b border-orange-50">
                    <th className="text-left pb-2">信頼度</th>
                    <th className="text-right pb-2">件数</th>
                    <th className="text-right pb-2">的中率</th>
                    <th className="text-right pb-2">回収率</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.confBands.map(b => (
                    <tr key={b.label} className="border-b border-orange-50 last:border-0">
                      <td className="py-2 font-mono text-xs text-gray-600 font-bold">{b.label}</td>
                      <td className="py-2 text-right text-gray-500">{b.count}</td>
                      <td className={`py-2 text-right font-bold ${parseFloat(b.rate) >= 30 ? "text-rose-500" : "text-gray-500"}`}>
                        {b.count > 0 ? `${b.rate}%` : "-"}
                      </td>
                      <td className={`py-2 text-right font-bold ${parseFloat(b.roi) >= 100 ? "text-orange-500" : "text-gray-400"}`}>
                        {b.count > 0 ? `${b.roi}%` : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* ── EV帯別（データある場合のみ） ─────────── */}
          {stats.evKnownCount > 0 && (
            <div className="bg-white rounded-3xl p-5 shadow-sm mb-4">
              <h2 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4">期待値（EV）帯別</h2>
              {stats.evBands.map(b => (
                <RateBar key={b.label} label={b.label} rate={b.rate} hit={b.hit} count={b.count} />
              ))}
              {stats.avgKellyPct && (
                <div className="mt-3 pt-3 border-t border-orange-50 flex items-center justify-between">
                  <span className="text-xs text-gray-400">平均Kelly賭け率</span>
                  <span className="text-sm font-black text-amber-500">{stats.avgKellyPct}%</span>
                </div>
              )}
            </div>
          )}

          {/* ── 投資準備チェック ──────────────────────── */}
          <div className="bg-white rounded-3xl p-5 shadow-sm mb-4">
            <h2 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-1">投資準備チェック</h2>
            {(() => {
              const items = [
                { ok: stats.sCount >= 30,           label: "BUYデータ 30件以上",  value: `${stats.sCount}件`,        note: "統計信頼性の最低ライン" },
                { ok: parseFloat(stats.sRate) >= 35, label: "BUY 的中率 ≥ 35%",   value: `${stats.sRate}%`,           note: "回収率損益分岐の目安" },
                { ok: parseFloat(stats.sRoi) >= 100, label: "BUY 回収率 ≥ 100%",  value: `${stats.sRoi}%`,            note: "投資対象として最低条件" },
                { ok: stats.evPositiveCount >= 10 && parseFloat(stats.evPositiveRate) >= 30,
                                                     label: "EV>0% 的中率 ≥ 30%", value: stats.evPositiveCount > 0 ? `${stats.evPositiveRate}%` : "-", note: "EV計算精度の検証" },
              ];
              const pass = items.filter(i => i.ok).length;
              return (
                <>
                  <div className="flex items-center gap-3 mb-4">
                    <div
                      className="text-4xl font-black"
                      style={pass === items.length ? { background: "linear-gradient(to right,#FF6B6B,#FF8E53)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" } : {}}
                    >
                      {pass}/{items.length}
                    </div>
                    <div className="text-sm text-gray-600 font-medium">
                      {pass === items.length ? "🟢 投資開始OK！" : pass >= 2 ? "🟡 もう少し…" : "🔴 データ収集中"}
                    </div>
                  </div>
                  {items.map((item, i) => (
                    <CheckItem key={i} {...item} />
                  ))}
                </>
              );
            })()}
          </div>

          {/* ── 展示データ有無 ────────────────────────── */}
          <div className="bg-white rounded-3xl p-5 shadow-sm mb-4">
            <h2 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4">展示データ有無別</h2>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-2xl p-3 text-center" style={{ backgroundColor: "#FFF0E8" }}>
                <p className="text-xs text-orange-400 font-bold mb-1">展示あり</p>
                <p className="text-2xl font-black text-orange-500">{stats.withExCount > 0 ? `${stats.withExRate}%` : "-"}</p>
                <p className="text-xs text-gray-400">{stats.withExHit}/{stats.withExCount}</p>
                <p className="text-xs text-orange-400 font-bold">回収率 {stats.withExCount > 0 ? `${stats.withExRoi}%` : "-"}</p>
              </div>
              <div className="bg-gray-50 rounded-2xl p-3 text-center">
                <p className="text-xs text-gray-400 font-bold mb-1">展示なし</p>
                <p className="text-2xl font-black text-gray-400">{stats.withoutExCount > 0 ? `${stats.withoutExRate}%` : "-"}</p>
                <p className="text-xs text-gray-400">{stats.withoutExHit}/{stats.withoutExCount}</p>
                <p className="text-xs text-gray-400">回収率 {stats.withoutExCount > 0 ? `${stats.withoutExRoi}%` : "-"}</p>
              </div>
            </div>
          </div>
        </>
      )}
    </main>
  );
}
