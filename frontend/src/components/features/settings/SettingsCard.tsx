import React from "react";
import { LucideIcon } from "lucide-react";

interface SettingItem {
  label: string;
  value: string | number;
  badge?: string;
}

interface SettingsCardProps {
  title: string;
  subtitle: string;
  icon: LucideIcon;
  items: SettingItem[];
}

export function SettingsCard({ title, subtitle, icon: Icon, items }: SettingsCardProps) {
  return (
    <div className="p-6 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 shadow-sm space-y-4">
      <div className="flex items-center gap-3 pb-3 border-b border-slate-100 dark:border-slate-800">
        <div className="w-10 h-10 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-100 dark:border-indigo-900/50 flex items-center justify-center text-indigo-600 dark:text-indigo-400 shrink-0">
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">{title}</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>
        </div>
      </div>

      <div className="space-y-3">
        {items.map((item, idx) => (
          <div
            key={idx}
            className="flex items-center justify-between p-3 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200/50 dark:border-slate-800 text-xs"
          >
            <span className="font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider text-[11px]">
              {item.label}
            </span>
            <div className="flex items-center gap-2">
              <span className="font-bold text-slate-900 dark:text-slate-100 font-mono">
                {item.value}
              </span>
              {item.badge && (
                <span className="px-2 py-0.5 rounded-md bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300 font-semibold text-[10px]">
                  {item.badge}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
