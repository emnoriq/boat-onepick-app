import { getTodayPredictions } from "@/lib/supabase";
import HomeList from "./HomeList";

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
        <p className="text-white/60 text-xs font-medium mb-1 tracking-widest uppercase">{today}</p>
        <h1 className="text-2xl font-black mb-4 tracking-tight">
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

      {/* ── レースリスト（判定順 / 時間順 切り替え） ──────────────── */}
      <HomeList
        buyRaces={buyRaces}
        candRaces={candRaces}
        pending={pending}
        skipRaces={skipRaces}
      />

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
