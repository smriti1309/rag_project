"use client";

import React from "react";
import { SettingsCard } from "@/components/features/settings/SettingsCard";
import { mockSystemSettings } from "@/lib/mock-data";
import { Cpu, Database, Sparkles, Layers, Sliders, ShieldCheck } from "lucide-react";

export default function SettingsPage() {
  const qdrantUrl = process.env.NEXT_PUBLIC_QDRANT_URL || "Not configured";
  const qdrantCollection = process.env.NEXT_PUBLIC_QDRANT_COLLECTION_NAME || "knowledge_base_v2";
  const embeddingModel = process.env.NEXT_PUBLIC_EMBEDDING_MODEL || "gemini-embedding-2";
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "Not configured";

  return (
    <div className="space-y-8 pb-12">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2.5">
            Engine Configuration
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Active architectural parameters derived from application Settings
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-3 py-1.5 rounded-xl bg-amber-50 dark:bg-amber-950/60 border border-amber-200 dark:border-amber-900/50 text-xs font-semibold text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5" /> Read-Only Mode
          </span>
        </div>
      </div>

      {/* Configuration Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Embedding Model Card */}
        <SettingsCard
          title="Embedding Model"
          subtitle="Gemini Embedding 2 vector encoding configuration"
          icon={Cpu}
          items={[
            { label: "Model Name", value: embeddingModel, badge: "Google GenAI" },
            { label: "Vector Dimension", value: "768 Float32" },
            { label: "Batch Size", value: "32 items/batch" },
            { label: "Device Backend", value: "Google GenAI API" },
          ]}
        />

        {/* Vector Database Card */}
        <SettingsCard
          title="Vector Database"
          subtitle="Qdrant collection and indexing settings"
          icon={Database}
          items={[
            { label: "Vector DB Engine", value: "Qdrant Vector DB", badge: "Cloud" },
            { label: "Connection URL", value: qdrantUrl },
            { label: "Collection Name", value: qdrantCollection },
            { label: "Batch Upsert Size", value: "500 points" },
            { label: "Distance Metric", value: "Cosine" },
          ]}
        />

        {/* Auth & LLM Provider Card */}
        <SettingsCard
          title="Authentication & Services"
          subtitle="Supabase Auth and LLM Provider setup"
          icon={Sparkles}
          items={[
            { label: "Auth Provider", value: "Supabase Auth", badge: "Active" },
            { label: "Supabase URL", value: supabaseUrl },
            { label: "LLM Provider", value: "Gemini 3.6 Flash" },
            { label: "Model Identifier", value: "gemini-3.6-flash" },
          ]}
        />

        {/* Chunk Strategy Card */}
        <SettingsCard
          title="Chunking Strategy"
          subtitle="Paragraph-aware document splitting parameters"
          icon={Layers}
          items={[
            { label: "Strategy", value: "Paragraph-Aware Chunking", badge: "Paragraph-Aware" },
            { label: "Max Chunk Size", value: "500 words" },
            { label: "Overlap Size", value: "30 words" },
            { label: "Parser Markers", value: "===== PAGE N ===== Tracked" },
          ]}
        />
      </div>
    </div>
  );
}
