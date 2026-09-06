import React from "react";
import { SystemHealth } from "@/types";
import { Server, Database, Cpu, Clock, CheckCircle, AlertTriangle, Activity } from "lucide-react";

interface SystemHealthPanelProps {
  health: SystemHealth | null;
  loading?: boolean;
}

export function SystemHealthPanel({ health, loading }: SystemHealthPanelProps) {
  const isHealthy = health?.vectorDbStatus?.includes("Connected");
  const backendStatus = loading ? "Checking..." : health?.backendStatus || "Healthy";
  const vectorDbStatus = loading ? "Checking..." : health?.vectorDbStatus || "Disconnected";
  const embeddingModel = loading ? "Loading..." : health?.embeddingModel || "gemini-embedding-2 (768D)";
  const lastUploadedTime = loading
    ? "Loading..."
    : health?.lastUploadedTime || "No documents uploaded";

  return (
    <div className="p-6 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 shadow-sm">
      <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-slate-800">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-900/50 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
            <Activity className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
              System Health & Pipeline
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Real-time service indicators
            </p>
          </div>
        </div>

        {isHealthy ? (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-900/50">
            <CheckCircle className="w-3.5 h-3.5" /> All Services Operational
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-400 border border-amber-200 dark:border-amber-900/50">
            <AlertTriangle className="w-3.5 h-3.5" /> Service Degraded
          </span>
        )}
      </div>

      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Backend Status */}
        <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200/60 dark:border-slate-800 flex items-center gap-3">
          <div className="p-2 rounded-lg bg-indigo-100 dark:bg-indigo-900/50 text-indigo-600 dark:text-indigo-400 shrink-0">
            <Server className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <span className="block text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
              Backend Status
            </span>
            <span className="block text-xs font-bold text-slate-900 dark:text-slate-100 truncate">
              {backendStatus}
            </span>
          </div>
        </div>

        {/* Vector DB Status */}
        <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200/60 dark:border-slate-800 flex items-center gap-3">
          <div className="p-2 rounded-lg bg-emerald-100 dark:bg-emerald-900/50 text-emerald-600 dark:text-emerald-400 shrink-0">
            <Database className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <span className="block text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
              Vector Database
            </span>
            <span className="block text-xs font-bold text-slate-900 dark:text-slate-100 truncate">
              {vectorDbStatus}
            </span>
          </div>
        </div>

        {/* Embedding Model */}
        <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200/60 dark:border-slate-800 flex items-center gap-3">
          <div className="p-2 rounded-lg bg-cyan-100 dark:bg-cyan-900/50 text-cyan-600 dark:text-cyan-400 shrink-0">
            <Cpu className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <span className="block text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
              Embedding Model
            </span>
            <span className="block text-xs font-bold text-slate-900 dark:text-slate-100 truncate">
              {embeddingModel}
            </span>
          </div>
        </div>

        {/* Last Uploaded Time */}
        <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200/60 dark:border-slate-800 flex items-center gap-3">
          <div className="p-2 rounded-lg bg-amber-100 dark:bg-amber-900/50 text-amber-600 dark:text-amber-400 shrink-0">
            <Clock className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <span className="block text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
              Last Uploaded Time
            </span>
            <span className="block text-xs font-bold text-slate-900 dark:text-slate-100 truncate">
              {lastUploadedTime}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
