import { getOpsData } from "@/lib/supabase";

export const dynamic = "force-dynamic";

function todayJST(): string {
  return new Date().toLocaleDateString("ja-JP", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).replace(/\//g, "-");
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border p-4 mb-4">
      <h2 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-3">
        {title}
      </h2>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function Row({
  label,
  value,
  sub,
  highlight,
  warn,
}: {
  label: string;
  value: string | number;
  sub?: string;
  highlight?: boolean;
  warn?: boolean;
}) {
  return (
    <div className="flex justify-between items-baseline">
      <span className="text-sm text-gray-600">{label}</span>
      <span
        className={`font-bold tabular-nums ${
          highlight
            ? "text-blue-600 text-lg"
            : warn
            ? "text-orange-500"
            : "text-gray-800"
        }`}
      >
        {value}
        {sub && (
          <span className="text-xs font-normal text-gray-400 ml-1">{sub}</span>
        )}
      </span>
    </div>
  );
}

function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="w-full bg-gray-100 rounded-full h-1.5 mt-0.5">
      <div
        className={`h-1.5 rounded-full ${color}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export default async function OpsPage() {
  const today = todayJST();
  const ops = await getOpsData(today);

  const allConf  = ops.maxConf;
  const roiNum   = parseFloat(ops.roi);
  const roiColor = roiNum >= 100 ? "text-green-600" : roiNum >= 70 ? "text-orange-500" : "text-red-500";

  return (
    <main className="max-w-lg mx-auto px-4 py-6">
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-xl font-bold">運用チェック</h1>
        <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">
          {today}
        </span>
      </div>
      {ops.lastUpdatedAt && (
        <p className="text-xs text-gray-400 mb-4">
          DB 最終更新: {ops.lastUpdatedAt}
        </p>
      )}

      {/* ── 今日の処理状況 ─────────────────────────── */}
      <Section title="今日の処理状況">
        <Row label="今日の全レース数"   value={`${ops.racesTotal} 件`} />
        <Row label="詳細取得済み"       value={`${ops.entriesTotal / 6 | 0} / ${ops.racesTotal} レース`}
          sub="(entries ÷ 6艇)"
          warn={ops.entriesTotal === 0 && ops.racesTotal > 0}
        />
        <Row label="展示取得済み"       value={`${ops.exhibitionCount} / ${ops.predictionsTotal} 件`}
          warn={ops.exhibitionCount < ops.predictionsTotal && ops.predictionsTotal > 0}
        />
        <Row label="予想未作成"         value={`${ops.unevaluatedCount} 件`}
          warn={ops.unevaluatedCount > 0}
        />
        <Row label="results 登録数"     value={`${ops.resultsTotal} 件`} />
        <div className="border-t pt-2 mt-2 space-y-2">
          <Row
            label="直前処理済み (predictions)"
            value={`${ops.predictionsTotal} / ${ops.racesTotal}`}
          />
          <Bar value={ops.predictionsTotal} max={ops.racesTotal} color="bg-green-400" />
          <Row
            label="結果確定済み"
            value={`${ops.finishedCount} / ${ops.racesTotal}`}
          />
          <Bar value={ops.finishedCount} max={ops.racesTotal} color="bg-blue-400" />
        </div>
      </Section>

      {/* ── 判定状況 ────────────────────────────────── */}
      <Section title="判定状況">
        <div className="flex gap-2 mb-2">
          <span className="flex-1 bg-red-50 border border-red-200 rounded-lg p-2 text-center">
            <div className="text-xs text-red-500 font-semibold">BUY</div>
            <div className="text-2xl font-black text-red-600">{ops.buyCount}</div>
            <div className="text-xs text-red-400">投票候補</div>
          </span>
          <span className="flex-1 bg-orange-50 border border-orange-200 rounded-lg p-2 text-center">
            <div className="text-xs text-orange-500 font-semibold">CANDIDATE</div>
            <div className="text-2xl font-black text-orange-500">{ops.candidateCount}</div>
            <div className="text-xs text-orange-400">投票候補</div>
          </span>
          <span className="flex-1 bg-blue-50 border border-blue-200 rounded-lg p-2 text-center">
            <div className="text-xs text-blue-500 font-semibold">WATCH</div>
            <div className="text-2xl font-black text-blue-500">{ops.watchCount}</div>
            <div className="text-xs text-blue-400">検証候補</div>
          </span>
          <span className="flex-1 bg-gray-50 border border-gray-200 rounded-lg p-2 text-center">
            <div className="text-xs text-gray-400 font-semibold">SKIP</div>
            <div className="text-2xl font-black text-gray-400">{ops.skipCount}</div>
            <div className="text-xs text-gray-300">非対象</div>
          </span>
        </div>
        <Row label="最大 confidence" value={`${allConf.toFixed(1)} 点`} />
        <Row label="平均 confidence" value={`${ops.avgConf} 点`} />
      </Section>

      {/* ── 的中状況 ────────────────────────────────── */}
      <Section title="的中状況（結果確定分）">
        {ops.verifiedTotal === 0 ? (
          <p className="text-sm text-gray-400 text-center py-2">
            まだ結果確定レースがありません
          </p>
        ) : (
          <>
            <Row label="検証対象レース数" value={`${ops.verifiedTotal} 件`} />
            <Row label="的中数"           value={`${ops.hitCount} 件`} />
            <Row
              label="的中率"
              value={`${ops.hitRate} %`}
              highlight
            />
            <div className="border-t pt-2 mt-2 space-y-2">
              <Row label="投資額合計"   value={`¥${ops.investTotal.toLocaleString()}`}
                sub="(1点100円)" />
              <Row label="払戻金合計"   value={`¥${ops.payoutTotal.toLocaleString()}`} />
              <Row
                label="仮回収率"
                value={`${ops.roi} %`}
                highlight={roiNum >= 100}
                warn={roiNum < 100 && ops.verifiedTotal > 0}
              />
            </div>
          </>
        )}
      </Section>

      {/* ── リンク ──────────────────────────────────── */}
      <div className="flex gap-3 mt-2 text-center text-xs">
        <a href="/schedule"  className="flex-1 text-gray-400 underline hover:text-gray-600">
          スケジュール
        </a>
        <a href="/roll-plan" className="flex-1 text-gray-400 underline hover:text-gray-600">
          転がし計画
        </a>
        <a href="/debug" className="flex-1 text-gray-400 underline hover:text-gray-600">
          デバッグ一覧
        </a>
        <a href="/stats" className="flex-1 text-gray-400 underline hover:text-gray-600">
          長期統計
        </a>
      </div>
    </main>
  );
}
