"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";

const TABS = [
  { href: "/",         icon: "🏠", label: "ホーム" },
  { href: "/schedule", icon: "📋", label: "スケジュール" },
  { href: "/stats",    icon: "📊", label: "統計" },
  { href: "/ops",      icon: "⚙️", label: "運用" },
];

export default function BottomNav() {
  const pathname = usePathname();

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 bg-white/90 backdrop-blur-md border-t border-orange-100 safe-area-inset-bottom">
      <div className="max-w-lg mx-auto flex">
        {TABS.map(tab => {
          const active = tab.href === "/"
            ? pathname === "/"
            : pathname.startsWith(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`flex-1 flex flex-col items-center gap-0.5 py-2.5 transition-all ${
                active ? "opacity-100" : "opacity-40 hover:opacity-70"
              }`}
            >
              <span className="text-xl leading-none">{tab.icon}</span>
              <span
                className={`text-xs font-bold ${active ? "text-orange-500" : "text-gray-500"}`}
              >
                {tab.label}
              </span>
              {active && (
                <span
                  className="absolute bottom-0 w-8 h-0.5 rounded-full"
                  style={{ background: "linear-gradient(to right, #FF6B6B, #FF8E53)" }}
                />
              )}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
