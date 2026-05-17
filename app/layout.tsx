import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "三連複1点 | ボートレース予想",
  description: "的中率重視・三連複1点特化のボートレース予想アプリ",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body style={{ backgroundColor: "#FFF5F0" }} className="min-h-screen">
        <nav className="bg-white/80 backdrop-blur-sm border-b border-orange-100 px-4 py-3 sticky top-0 z-10">
          <div className="max-w-lg mx-auto flex items-center justify-between">
            <a href="/" className="flex items-center gap-2">
              <span className="text-lg">⛵</span>
              <span className="font-black text-base tracking-tight bg-gradient-to-r from-rose-500 to-orange-400 bg-clip-text text-transparent">
                三連複1点
              </span>
            </a>
            <div className="flex items-center gap-1 text-xs">
              <a href="/schedule" className="px-3 py-1.5 rounded-full text-gray-500 hover:bg-orange-50 hover:text-orange-500 transition-colors">スケジュール</a>
              <a href="/stats"    className="px-3 py-1.5 rounded-full text-gray-500 hover:bg-orange-50 hover:text-orange-500 transition-colors">統計</a>
            </div>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
