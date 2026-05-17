import { getOpsData } from "@/lib/supabase";

export const dynamic = "force-dynamic";

function todayJST(): string {
  return new Date().toLocaleDateString("ja-JP", {
    timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit",
  }).replace(/\//g, "-");
}

function Row({ label, value, sub, ok, warn }: {
  label: string; value: string | number; sub?: string; ok?: boolean; warn?: boolean;
}) {
  return (
    <div className="flex justify-between items-center py-2 border-b border-orange-50 last:border-0">
      <span className="text-sm text-gray-600">{label}</span>
      <span className={`font-bold tabular-nums text-sm ${
        ok   ? "text-rose-500" :
        warn ? "text-amber-500" :
               "text-gray-700"
      }`}>
        {value}
        {sub && <span className="text-xs font-normal text-gray-400 ml-1">{sub}</span>}
      </span>
    </div>
  );
}

function ProgressBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.round(value / max * 100) : 0;
  return (
    <div className="h-2 rounded-full overflow-hidden mb-3" style={{ backgroundColor: "#FFF0E8" }}>
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${pct}%`, background: "linear-gradient(to right, #FF6B6B, #FF8E53)" }}
      />
    </div>
  );
}

export default async function OpsPage() {
  const today = todayJST();
  const ops = await getOpsData(today);
  const roiNum = parseFloat(ops.roi);

  return (
    <main className="max-w-lg mx-auto px-4 py-5">

      {/* ── ヘッダー ───────────────────────────────── */}
      <div
        className="rounded-3xl p-5 mb-5 text-white shadow-lg"
        style={{ background: "linear-gradient(135deg, #FF6B6B 0%, #FF8E53 60%, #FFBE0B 100%)" }}
      >
        <p className="text-white/60 text-xs mb-1">今日の処理状況</p>
        <h1 className="text-2xl font-black mb-2">運用チェック</h1>
        <p className="text-white/70 text-sm">{today}</p>
        {ops.lastUpdatedAt && (
          <p className="text-white/50 text-xs mt-1">DB更新: {ops.lastUpdatedAt}</p>
        )}
      </div>

      {/* ── 処理進捗 ────────────────────────────────── */}
      <div className="bg-white rounded-3xl p-5 shadow-sm mb-4">
        <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-4">処理進捗</h2>

        <div className="mb-2 flex justify-between text-sm">
          <span className="text-gray-600">予想完了</span>
          <span className="font-bold text-gray-800">{ops.predictionsTotal} / {ops.racesTotal}</span>
        </div>
        <ProgressBar value={ops.predictionsTotal} max={ops.racesTotal} />

        <div className="mb-2 flex justify-between text-sm">
          <span className="text-gray-600">結果確定</span>
          <span className="font-bold text-gray-800">{ops.finishedCount} / {ops.racesTotal}</span>
        </div>
        <ProgressBar value={ops.finishedCount} max={ops.racesTotal} />

        <div className="space-y-0">
          <Row label="全レース数"    value={`${ops.racesTotal}件`} />
          <Row label="展示取得済み"  value={`${ops.exhibitionCount} / ${ops.predictionsTotal}件`}
            warn={ops.exhibitionCount < ops.predictionsTotal && ops.predictionsTotal > 0} />
          <Row label="予想未作成"    value={`${ops.unevaluatedCount}件`}
            warn={ops.unevaluatedCount > 0} />
        </div>
      </div>

      {/* ── 判定サマリー ────────────────────────────── */}
      <div className="bg-white rounded-3xl p-5 shadow-sm mb-4">
        <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-4">判定内訳</h2>
        <div className="grid grid-cols-2 gap-2 mb-3">
          {[
            { label: "BUY",      count: ops.buyCount,       bg: "bg-rose-50",   text: "text-rose-500",   sub: "投票確定" },
            { label: "CANDIDATE",count: ops.candidateCount, bg: "bg-orange-50", text: "text-orange-400", sub: "投票検討" },
            { label: "WATCH",    count: ops.watchCount,     bg: "bg-amber-50",  text: "text-amber-500",  sub: "検証候補" },
            { label: "SKIP",     count: ops.skipCount,      bg: "bg-gray-50",   text: "text-gray-400",   sub: "見送り" },
          ].map(c => (
            <div key={c.label} className={`${c.bg} rounded-2xl p-3 text-center`}>
              <div className={`text-2xl font-black ${c.text}`}>{c.count}</div>
              <div className="text-xs font-bold text-gray-500">{c.label}</div>
              <div className="text-xs text-gray-400">{c.sub}</div>
            </div>
          ))}
        </div>
        <Row label="最大 confidence" value={`${ops.maxConf.toFixed(1)}点`} />
        <Row label="平均 confidence" value={`${ops.avgConf}点`} />
      </div>

      {/* ── 的中状況 ────────────────────────────────── */}
      <div className="bg-white rounded-3xl p-5 shadow-sm mb-4">
        <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-4">本日の的中状況</h2>
        {ops.verifiedTotal === 0 ? (
          <p className="text-sm text-gray-400 text-center py-4">まだ結果確定レースがありません</p>
        ) : (
          <>
            <Row label="検証対象"  value={`${ops.verifiedTotal}件`} />
            <Row label="的中数"    value={`${ops.hitCount}件`} />
            <Row label="的中率"    value={`${ops.hitRate}%`} ok={parseFloat(ops.hitRate) >= 35} />
            <Row label="投資額"    value={`¥${ops.investTotal.toLocaleString()}`} sub="1点100円" />
            <Row label="払戻合計"  value={`¥${ops.payoutTotal.toLocaleString()}`} />
            <Row label="回収率"    value={`${ops.roi}%`}
              ok={roiNum >= 100}
              warn={roiNum < 100 && ops.verifiedTotal > 0} />
          </>
        )}
      </div>
    </main>
  );
}
