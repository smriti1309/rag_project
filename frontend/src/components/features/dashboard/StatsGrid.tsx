import React from "react";
import { DashboardCard } from "./DashboardCard";
import { DashboardStats } from "@/types";
import { FileText, Layers, Binary, Database } from "lucide-react";

interface StatsGridProps {
  stats: DashboardStats | null;
  loading?: boolean;
}

export function StatsGrid({ stats, loading }: StatsGridProps) {
  const docsVal = loading ? "..." : stats ? stats.documentsIndexed.toLocaleString() : "0";
  const chunksVal = loading ? "..." : stats ? stats.totalChunks.toLocaleString() : "0";
  const embeddingsVal = loading ? "..." : stats ? stats.totalEmbeddings.toLocaleString() : "0";
  const qdrantVal = loading ? "..." : stats?.vectorDbStatus || "Disconnected";
  const qdrantActive = stats?.vectorDbStatus === "Connected";

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
      <DashboardCard
        title="Documents Indexed"
        value={docsVal}
        change="Live Count"
        trend="neutral"
        icon={FileText}
        description="Successfully indexed documents"
        color="indigo"
      />

      <DashboardCard
        title="Total Chunks"
        value={chunksVal}
        change="Live Count"
        trend="neutral"
        icon={Layers}
        description="Paragraph-aware text chunks"
        color="cyan"
      />

      <DashboardCard
        title="Total Embeddings"
        value={embeddingsVal}
        change="Qdrant Vectors"
        trend="neutral"
        icon={Binary}
        description="768D vector points stored"
        color="amber"
      />

      <DashboardCard
        title="Vector DB Status"
        value={qdrantVal}
        change={qdrantActive ? "Qdrant Active" : "Qdrant Offline"}
        trend={qdrantActive ? "up" : "down"}
        icon={Database}
        description="Collection: knowledge_base_v2"
        color={qdrantActive ? "emerald" : "rose"}
      />
    </div>
  );
}
