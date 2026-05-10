import { getTodayPredictions, getScheduleData } from "@/lib/supabase";
import { buildRollPlan } from "@/lib/rollPlan";
import RaceCard from "@/components/RaceCard";

export const dynamic = "force-dynamic";

function todayJST(): string {
  return new Date().toLocaleDateString("ja-JP", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).replace(/\//g, "-");
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("ja-JP", {
    timeZone: "Asia/Tokyo",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export default async function HomePage() {
  const today = todayJST();
  const [races, { rows }] = await Promise.all([
    getTodayPredictions(today),
    getScheduleData(today),
  ]);
  const plan = buildRollPlan(rows);

  const buyRaces       = races.filter((r) => r.predictions?.decision === "buy");
  const candidateRaces = races.filter((r) => r.predictions?.decision === "candidate");

  // 転がし判定バナーの色
  const bannerStyle =
    plan.judgment === "go"
      ? "bg-green-50 border-green-400"
      : plan.judgment === "conditional"
      ? "bg-amber-50 border-amber-400"
      : "bg-gray-50 border-gray-300";
  const bannerIcon =
    plan.judgment === "go" ? "✅" : plan.judgment === "conditional" ? "⚠️" : "🚫";
  const bannerLabel =
    plan.judgment === "go" ? "挑戦可能" : plan.judgment === "conditional" ? "条件付き" : "見送り";

  return (
    <main className="max-w-lg mx-auto px-4 py-6">
      <h1 className="text-xl font-bold mb-1">今日の三連複1点候補</h1>
      <p className="text-xs text-gray-400 mb-4">{today}</p>

      {/* ── 今日の転がしセット ───────────────────────────── */}
      <a href="/roll-plan" className="block mb-5">
        <div className={`border-l-4 rounded-xl p-4 ${bannerStyle} hover:opacity-90 transition-opacity`}>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-lg">{bannerIcon}</span>
              <span className="font-bold text-sm">4回転がし判定：{bannerLabel}</span>
            </div>
            <span className="text-xs text-gray-400">詳細 →</span>
          </div>

          {plan.bestRoute ? (
            <div className="space-y-1">
              {/* 転がしチェーン（コンパクト表示） */}
              <div className="flex items-center gap-1 flex-wrap text-xs">
                <span className="font-bold text-gray-700">¥1,000</span>
                {plan.bestRoute.steps.map((step, i) => {
                  const isDone = step.status === "finished";
                  const isNext = step.status === "scheduled" &&
                    plan.bestRoute!.steps.slice(0, i).every((s) => s.status === "finished");
                  return (
                    <span key={step.race_id} className="flex items-center gap-1">
                      <span className="text-gray-300">→</span>
                      <span className={`px-1.5 py-0.5 rounded font-medium ${
                        step.prediction_hit === true
                          ? "bg-green-100 text-green-700"
                          : step.prediction_hit === false
                          ? "bg-red-100 text-red-500 line-through"
                          : isNext
                          ? "bg-blue-100 text-blue-700 font-bold"
                          : "bg-gray-100 text-gray-500"
                      }`}>
                        {step.stadium} {step.race_no}R {fmtTime(step.close_time)}
                        {step.prediction_hit === true && " ✅"}
                        {step.prediction_hit === false && " ❌"}
                        {isNext && " ◀ 次"}
                      </span>
                    </span>
                  );
                })}
              </div>
              {/* 選出レース数・信頼度 */}
              <div className="flex gap-3 text-xs text-gray-500 mt-1">
                <span className="text-red-600 font-bold">BUY×{plan.bestRoute.buyCount}</span>
                {plan.bestRoute.candidateCount > 0 && (
                  <span className="text-orange-600">CAND×{plan.bestRoute.candidateCount}</span>
                )}
                <span>avg conf {plan.bestRoute.avgConfidence}</span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-500">本日は4回転がしルートが見つかりません</p>
          )}
        </div>
      </a>

      {/* ── 個別レース一覧 ────────────────────────────────── */}
      {buyRaces.length === 0 && candidateRaces.length === 0 && (
        <div className="text-center py-10 text-gray-400">
          <p className="text-base font-semibold mb-2">本日の1点勝負レースはありません</p>
          <ul className="text-sm space-y-1 text-left inline-block">
            <li>・上位3艇が明確なレースが少ない</li>
            <li>・4番手との差が小さい</li>
            <li>・直前情報で不安要素あり</li>
          </ul>
        </div>
      )}

      {buyRaces.length > 0 && (
        <section className="mb-6">
          <h2 className="text-sm font-semibold text-red-600 uppercase tracking-wider mb-2">
            Sランク（買い）
          </h2>
          {buyRaces.map((r) => <RaceCard key={r.id} race={r} />)}
        </section>
      )}

      {candidateRaces.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-orange-500 uppercase tracking-wider mb-2">
            Aランク（候補）
          </h2>
          {candidateRaces.map((r) => <RaceCard key={r.id} race={r} />)}
        </section>
      )}

      <div className="mt-8 grid grid-cols-3 gap-2 text-center text-xs text-gray-500">
        <a href="/schedule"  className="border rounded-lg py-2 hover:bg-gray-50 hover:text-gray-700">📋 スケジュール</a>
        <a href="/roll-plan" className="border rounded-lg py-2 hover:bg-gray-50 hover:text-gray-700">🔄 転がし計画</a>
        <a href="/stats"     className="border rounded-lg py-2 hover:bg-gray-50 hover:text-gray-700">📊 長期統計</a>
        <a href="/ops"       className="border rounded-lg py-2 hover:bg-gray-50 hover:text-gray-700">🔧 運用チェック</a>
        <a href="/debug"     className="border rounded-lg py-2 hover:bg-gray-50 hover:text-gray-700">🐛 デバッグ</a>
      </div>
    </main>
  );
}
