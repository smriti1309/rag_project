import React from "react";
import { DashboardCard } from "./DashboardCard";
import { mockDashboardStats } from "@/lib/mock-data";
import { FileText, Layers, Binary, Database } from "lucide-react";

export function StatsGrid() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
      <DashboardCard
        title="Documents Indexed"
        value="--"
        change="Demo Value"
        trend="neutral"
        icon={FileText}
        description="Parsed PDF and TXT documents in workspace"
        color="indigo"
      />

      <DashboardCard
        title="Total Chunks"
        value="--"
        change="Demo Value"
        trend="neutral"
        icon={Layers}
        description="Paragraph-aware chunks generated"
        color="cyan"
      />

      <DashboardCard
        title="Total Embeddings"
        value="--"
        change="Demo Value"
        trend="neutral"
        icon={Binary}
        description="gemini-embedding-2 vector embeddings"
        color="amber"
      />

      <DashboardCard
        title="Vector DB Status"
        value="Connected"
        change="Qdrant Active"
        trend="up"
        icon={Database}
        description="Collection: knowledge_base_v2 (Cosine metric)"
        color="emerald"
      />
    </div>
  );
}
