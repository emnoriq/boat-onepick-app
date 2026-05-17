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

      {/* ── サマリーヘッダー（暖色グラデーション） ────────────────── */}
      <div
        className="rounded-3xl p-6 mb-5 text-white shadow-lg"
        style={{ background: "linear-gradient(135deg, #FF6B6B 0%, #FF8E53 50%, #FFBE0B 100%)" }}
      >
        <p className="text-white/70 text-xs font-medium mb-1">{today}</p>
        <h1 className="text-3xl font-black mb-4 tracking-tight drop-shadow-sm">
          今日の投票リスト
        </h1>

        {hasBets ? (
          <div className="flex gap-3">
            {buyRaces.length > 0 && (
              <div className="bg-white/25 backdrop-blur-sm rounded-2xl px-4 py-2 text-center">
                <div className="text-2xl font-black">{buyRaces.length}</div>
                <div className="text-xs font-bold text-white/80">確定 BUY</div>
              </div>
            )}
            {candRaces.length > 0 && (
              <div className="bg-white/25 backdrop-blur-sm rounded-2xl px-4 py-2 text-center">
                <div className="text-2xl font-black">{candRaces.length}</div>
                <div className="text-xs font-bold text-white/80">検討</div>
              </div>
            )}
            {pending.length > 0 && (
              <div className="bg-white/15 rounded-2xl px-4 py-2 text-center">
                <div className="text-2xl font-black text-white/60">{pending.length}</div>
                <div className="text-xs text-white/50">展示待ち</div>
              </div>
            )}
          </div>
        ) : pending.length > 0 ? (
          <div className="bg-white/20 rounded-2xl px-4 py-3 inline-flex items-center gap-2">
            <span className="text-lg">⏳</span>
            <span className="text-sm font-bold">展示スキャン待ち {pending.length}件</span>
          </div>
        ) : (
          <div className="bg-white/20 rounded-2xl px-4 py-3 inline-flex items-center gap-2">
            <span className="text-lg">⛵</span>
            <span className="text-sm font-bold">朝6時以降にスキャン開始</span>
          </div>
        )}
      </div>

      {/* ── データなし ───────────────────────────────────────────── */}
      {!hasBets && pending.length === 0 && skipRaces.length === 0 && (
        <div className="text-center py-16">
          <p className="text-4xl mb-3">⛵</p>
          <p className="font-bold text-gray-500 mb-1">本日のデータがまだありません</p>
          <p className="text-sm text-gray-400">朝6時以降にスキャンが始まります</p>
        </div>
      )}

      {/* ── 🎯 投票確定（BUY） ──────────────────────────────────── */}
      {buyRaces.length > 0 && (
        <section className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-1 h-5 rounded-full" style={{ background: "linear-gradient(to bottom, #FF6B6B, #FF8E53)" }} />
            <h2 className="text-sm font-bold text-gray-700">
              投票確定
              <span className="ml-2 text-xs font-normal text-gray-400">BUY · {buyRaces.length}件</span>
            </h2>
          </div>
          {buyRaces.map((r, i) => <RaceCard key={r.id} race={r} rank={i + 1} />)}
        </section>
      )}

      {/* ── 📌 投票検討（CANDIDATE） ─────────────────────────────── */}
      {candRaces.length > 0 && (
        <section className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-1 h-5 rounded-full" style={{ background: "linear-gradient(to bottom, #FF8E53, #FFBE0B)" }} />
            <h2 className="text-sm font-bold text-gray-700">
              投票検討
              <span className="ml-2 text-xs font-normal text-gray-400">CANDIDATE · {candRaces.length}件</span>
            </h2>
          </div>
          {candRaces.map((r, i) => <RaceCard key={r.id} race={r} rank={buyRaces.length + i + 1} />)}
        </section>
      )}

      {/* ── ⏳ 展示待ち ───────────────────────────────────────────── */}
      {pending.length > 0 && (
        <section className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-1 h-5 rounded-full bg-gray-200" />
            <h2 className="text-sm font-semibold text-gray-400">
              展示待ち
              <span className="ml-2 text-xs font-normal">直前スキャン後に更新 · {pending.length}件</span>
            </h2>
          </div>
          {pending.map(r => <RaceCard key={r.id} race={r} />)}
        </section>
      )}

      {/* ── 見送り（折りたたみ） ────────────────────────────────── */}
      {skipRaces.length > 0 && (
        <details className="mb-6 group">
          <summary className="flex items-center gap-2 cursor-pointer text-xs text-gray-400 hover:text-gray-500 select-none list-none mb-3">
            <span className="group-open:rotate-90 transition-transform inline-block">▶</span>
            <span>見送り {skipRaces.length}件</span>
          </summary>
          <div className="opacity-50">
            {skipRaces.map(r => <RaceCard key={r.id} race={r} />)}
          </div>
        </details>
      )}

      {/* ── ボトムナビ ──────────────────────────────────────────── */}
      <div className="pt-4 mt-2 grid grid-cols-3 gap-3 text-center">
        {[
          { href: "/schedule", icon: "📋", label: "スケジュール" },
          { href: "/stats",    icon: "📊", label: "統計" },
          { href: "/debug",    icon: "🔍", label: "デバッグ" },
        ].map(nav => (
          <a
            key={nav.href}
            href={nav.href}
            className="flex flex-col items-center gap-1.5 py-3 rounded-2xl bg-white hover:shadow-md transition-all text-gray-400 hover:text-orange-500"
          >
            <span className="text-xl">{nav.icon}</span>
            <span className="text-xs font-medium">{nav.label}</span>
          </a>
        ))}
      </div>
    </main>
  );
}
