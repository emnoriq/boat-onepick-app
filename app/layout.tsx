import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "三連複1点 | ボートレース予想",
  description: "的中率重視・三連複1点特化のボートレース予想アプリ",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className="bg-gray-50 min-h-screen">
        <nav className="bg-white border-b px-4 py-3">
          <div className="max-w-6xl mx-auto flex items-center justify-between">
            <a href="/" className="font-bold text-base">三連複1点</a>
            <div className="flex items-center gap-4 text-sm">
              <a href="/ops"   className="text-gray-500 hover:text-gray-800">運用</a>
              <a href="/stats" className="text-gray-500 hover:text-gray-800">統計</a>
              <a href="/debug" className="text-gray-400 hover:text-gray-600">debug</a>
            </div>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
