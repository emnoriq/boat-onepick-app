import type { Metadata } from "next";
import { Noto_Sans_JP, Inter } from "next/font/google";
import "./globals.css";
import BottomNav from "@/components/BottomNav";

const noto = Noto_Sans_JP({
  subsets: ["latin"],
  weight: ["400", "500", "700", "900"],
  variable: "--font-noto",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "三連複1点 | ボートレース予想",
  description: "的中率重視・三連複1点特化のボートレース予想アプリ",
  appleWebApp: {
    capable: true,
    title: "三連複1点",
    statusBarStyle: "black-translucent",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body style={{ backgroundColor: "#FFF5F0" }} className={`${noto.variable} ${inter.variable} font-sans min-h-screen pb-20`}>
        {/* ── トップバー（ロゴのみ） ───────────────── */}
        <header className="bg-white/80 backdrop-blur-sm border-b border-orange-100 px-4 py-3 sticky top-0 z-10">
          <div className="max-w-lg mx-auto flex items-center justify-between">
            <a href="/" className="flex items-center gap-2">
              <span className="text-lg">⛵</span>
              <span
                className="font-black text-base tracking-tight"
                style={{ background: "linear-gradient(to right, #FF6B6B, #FF8E53)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}
              >
                三連複1点
              </span>
            </a>
            <a href="/debug" className="text-xs text-gray-300 hover:text-gray-400 transition-colors">debug</a>
          </div>
        </header>

        {/* ── コンテンツ ───────────────────────────── */}
        {children}

        {/* ── ボトムタブナビ ───────────────────────── */}
        <BottomNav />
      </body>
    </html>
  );
}
