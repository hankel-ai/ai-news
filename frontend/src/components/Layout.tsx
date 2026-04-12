import { ReactNode } from "react";

interface Props {
  activeTab: string;
  onTabChange: (tab: "headlines" | "settings") => void;
  children: ReactNode;
}

export default function Layout({ activeTab, onTabChange, children }: Props) {
  const tabs = [
    { key: "headlines" as const, label: "Headlines" },
    { key: "settings" as const, label: "Settings" },
  ];

  return (
    <div className="max-w-4xl mx-auto px-4 py-6">
      <header className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-hankel-accent">AI News</h1>
        <nav className="flex gap-1 bg-hankel-surface rounded-lg p-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => onTabChange(t.key)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                activeTab === t.key
                  ? "bg-hankel-accent text-hankel-bg"
                  : "text-hankel-muted hover:text-hankel-text"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <main>{children}</main>
    </div>
  );
}
