import { getTodayPredictions } from "@/lib/supabase";
import RaceCard from "@/components/RaceCard";

export const dynamic = "force-dynamic";

function todayJST(): string {
  return new Date().toLocaleDateString("ja-JP", {
    timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit",
  }).replace(/\//g, "-");
}

export default async function HomePage() {
  const today = todayJST();
  const races = await getTodayPredictions(today);

  const hasEx = (r: typeof races[number]) =>
    r.predictions?.reason != null &&
    !r.predictions.reason.includes("[展示未取得]") &&
    !r.predictions.reason.includes("朝スキャン暫定");

  const sorted = races
    .filter(r => r.predictions != null)
    .sort((a, b) => (b.predictions?.confidence ?? 0) - (a.predictions?.confidence ?? 0));

  const buyRaces  = sorted.filter(r => r.predictions?.decision === "buy"       && hasEx(r));
  const candRaces = sorted.filter(r => r.predictions?.decision === "candidate" && hasEx(r));
  const skipRaces = sorted.filter(r => r.predictions?.decision === "skip"      && hasEx(r));
  const pending   = sorted.filter(r => !hasEx(r));
  const hasBets   = buyRaces.length > 0 || candRaces.length > 0;

  return (
    <main className="max-w-lg mx-auto px-4 py-5">

      {/* ── サマリーヘッダー ───────────────────────────────────────── */}
      <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl p-5 mb-5 text-white shadow-lg">
        <p className="text-slate-400 text-xs mb-1">{today}</p>
        <h1 className="text-2xl font-black mb-3 tracking-tight">今日の投票リスト</h1>
        <div className="flex gap-2 flex-wrap">
          {buyRaces.length > 0 ? (
            <div className="bg-emerald-500/20 text-emerald-300 text-sm font-bold px-3 py-1.5 rounded-xl">
              🎯 BUY {buyRaces.length}件
            </div>
          ) : (
            <div className="bg-white/10 text-slate-400 text-sm px-3 py-1.5 rounded-xl">
              BUY なし
            </div>
          )}
          {candRaces.length > 0 && (
            <div className="bg-amber-400/20 text-amber-300 text-sm font-bold px-3 py-1.5 rounded-xl">
              📌 検討 {candRaces.length}件
            </div>
          )}
          {pending.length > 0 && (
            <div className="bg-white/10 text-slate-300 text-sm px-3 py-1.5 rounded-xl">
              ⏳ 展示待ち {pending.length}件
            </div>
          )}
        </div>
      </div>

      {/* ── データなし ───────────────────────────────────────────── */}
      {!hasBets && pending.length === 0 && skipRaces.length === 0 && (
        <div className="text-center py-16">
          <p className="text-4xl mb-3">⛵</p>
          <p className="font-bold text-gray-600 mb-1">本日のデータがまだありません</p>
          <p className="text-sm text-gray-400">朝6時以降にスキャンが始まります</p>
        </div>
      )}

      {/* ── 🎯 投票確定（BUY） ──────────────────────────────────── */}
      {buyRaces.length > 0 && (
        <section className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-1 h-4 rounded-full bg-emerald-500" />
            <h2 className="text-sm font-bold text-gray-800">
              投票確定
              <span className="ml-1.5 text-xs font-normal text-gray-400">BUY · {buyRaces.length}件</span>
            </h2>
          </div>
          {buyRaces.map((r, i) => <RaceCard key={r.id} race={r} rank={i + 1} />)}
        </section>
      )}

      {/* ── 📌 投票検討（CANDIDATE） ─────────────────────────────── */}
      {candRaces.length > 0 && (
        <section className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-1 h-4 rounded-full bg-amber-400" />
            <h2 className="text-sm font-bold text-gray-800">
              投票検討
              <span className="ml-1.5 text-xs font-normal text-gray-400">CANDIDATE · {candRaces.length}件</span>
            </h2>
          </div>
          {candRaces.map((r, i) => <RaceCard key={r.id} race={r} rank={buyRaces.length + i + 1} />)}
        </section>
      )}

      {/* ── ⏳ 展示待ち ───────────────────────────────────────────── */}
      {pending.length > 0 && (
        <section className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-1 h-4 rounded-full bg-slate-300" />
            <h2 className="text-sm font-semibold text-gray-500">
              展示待ち
              <span className="ml-1.5 text-xs font-normal text-gray-400">直前スキャン後に更新 · {pending.length}件</span>
            </h2>
          </div>
          {pending.map(r => <RaceCard key={r.id} race={r} />)}
        </section>
      )}

      {/* ── 見送り（折りたたみ） ────────────────────────────────── */}
      {skipRaces.length > 0 && (
        <details className="mb-6 group">
          <summary className="flex items-center gap-2 cursor-pointer text-xs text-gray-400 hover:text-gray-600 select-none list-none mb-3">
            <span className="group-open:rotate-90 transition-transform inline-block">▶</span>
            <span>見送り {skipRaces.length}件を表示</span>
          </summary>
          <div className="opacity-50 hover:opacity-70 transition-opacity">
            {skipRaces.map(r => <RaceCard key={r.id} race={r} />)}
          </div>
        </details>
      )}

      {/* ── ボトムナビ ──────────────────────────────────────────── */}
      <div className="border-t border-gray-100 pt-5 mt-2 grid grid-cols-3 gap-2 text-center">
        {[
          { href: "/schedule", icon: "📋", label: "スケジュール" },
          { href: "/stats",    icon: "📊", label: "統計" },
          { href: "/debug",    icon: "🔍", label: "デバッグ" },
        ].map(nav => (
          <a
            key={nav.href}
            href={nav.href}
            className="flex flex-col items-center gap-1 py-2 rounded-xl hover:bg-white hover:shadow-sm transition-all text-gray-400 hover:text-gray-700"
          >
            <span className="text-lg">{nav.icon}</span>
            <span className="text-xs">{nav.label}</span>
          </a>
        ))}
      </div>
    </main>
  );
}
