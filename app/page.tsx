import { getTodayPredictions } from "@/lib/supabase";
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

export default async function HomePage() {
  const today = todayJST();
  const races = await getTodayPredictions(today);

  const buyRaces      = races.filter((r) => r.predictions?.decision === "buy");
  const candidateRaces = races.filter((r) => r.predictions?.decision === "candidate");

  return (
    <main className="max-w-lg mx-auto px-4 py-6">
      <h1 className="text-xl font-bold mb-1">今日の三連複1点候補</h1>
      <p className="text-xs text-gray-400 mb-4">{today}</p>

      {buyRaces.length === 0 && candidateRaces.length === 0 && (
        <div className="text-center py-16 text-gray-400">
          <p className="text-lg font-semibold mb-2">本日の1点勝負レースはありません</p>
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
