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
        <nav className="bg-white border-b px-4 py-3 flex items-center justify-between max-w-lg mx-auto">
          <a href="/" className="font-bold text-base">三連複1点</a>
          <a href="/stats" className="text-sm text-gray-500 hover:text-gray-700">検証</a>
        </nav>
        {children}
      </body>
    </html>
  );
}
