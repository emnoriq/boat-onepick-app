import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "三連複1点 | ボートレース予想",
  description: "的中率重視・三連複1点特化のボートレース予想アプリ",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className="bg-slate-50 min-h-screen">
        <nav className="bg-white border-b border-gray-100 px-4 py-3 sticky top-0 z-10 shadow-sm">
          <div className="max-w-lg mx-auto flex items-center justify-between">
            <a href="/" className="flex items-center gap-2">
              <span className="text-lg">⛵</span>
              <span className="font-black text-slate-800 text-base tracking-tight">三連複1点</span>
            </a>
            <div className="flex items-center gap-1 text-xs">
              <a href="/schedule"  className="px-3 py-1.5 rounded-full text-gray-500 hover:bg-gray-100 hover:text-gray-800 transition-colors">スケジュール</a>
              <a href="/roll-plan" className="px-3 py-1.5 rounded-full text-gray-500 hover:bg-gray-100 hover:text-gray-800 transition-colors">転がし</a>
              <a href="/stats"     className="px-3 py-1.5 rounded-full text-gray-500 hover:bg-gray-100 hover:text-gray-800 transition-colors">統計</a>
            </div>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
