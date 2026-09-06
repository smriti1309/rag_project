"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { StatsGrid } from "@/components/features/dashboard/StatsGrid";
import { SystemHealthPanel } from "@/components/features/dashboard/SystemHealthPanel";
import { useAuth } from "@/components/providers/AuthProvider";
import { DashboardStats, DocumentItem, SystemHealth } from "@/types";
import {
  UploadCloud,
  MessageSquare,
  BookOpen,
  ArrowUpRight,
  FileText,
  Sparkles,
  CheckCircle2,
} from "lucide-react";
import { formatBytes } from "@/lib/utils";
import { getAuthHeaders } from "@/lib/supabase/client";

export default function DashboardPage() {
  const { user } = useAuth();
  const [recentDocs, setRecentDocs] = useState<DocumentItem[]>([]);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loadingStats, setLoadingStats] = useState<boolean>(true);

  useEffect(() => {
    const fetchDashboardData = async () => {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
      const authHeaders = await getAuthHeaders();

      // 1. Fetch Documents for Recent Documents section
      try {
        const res = await fetch(`${apiUrl}/documents`, {
          headers: authHeaders,
        });
        if (res.ok) {
          const data = await res.json();
          const mapped: DocumentItem[] = data.map((d: any) => ({
            id: d.document_id,
            name: d.original_filename,
            originalFilename: d.original_filename,
            size: d.size,
            uploadDate: new Date(d.uploaded_at).toISOString().replace("T", " ").substring(0, 19),
            chunkCount: d.chunk_count || 0,
            status: (d.status as any) || "indexed",
          }));
          setRecentDocs(mapped.slice(0, 4));
        }
      } catch (err) {
        console.error("Failed to fetch recent documents:", err);
      }

      // 2. Fetch Dashboard Statistics and Health
      try {
        setLoadingStats(true);
        const statsRes = await fetch(`${apiUrl}/dashboard/stats`, {
          headers: authHeaders,
        });
        if (statsRes.ok) {
          const sData = await statsRes.json();
          setStats({
            documentsIndexed: sData.documents_indexed,
            totalChunks: sData.total_chunks,
            totalEmbeddings: sData.total_embeddings,
            vectorDbStatus: sData.qdrant_status as "Connected" | "Disconnected",
            lastUploadedTime: sData.last_uploaded_time,
          });
          setHealth({
            backendStatus: sData.backend_status,
            vectorDbStatus: `${sData.qdrant_status} (${sData.qdrant_collection})`,
            embeddingModel: sData.embedding_model,
            lastUploadedTime: sData.last_uploaded_time,
          });
        }
      } catch (err) {
        console.error("Failed to fetch dashboard stats:", err);
      } finally {
        setLoadingStats(false);
      }
    };

    fetchDashboardData();
  }, []);

  return (
    <div className="space-y-8 pb-12">
      {/* Welcome Banner */}
      <div className="p-8 rounded-3xl bg-gradient-to-r from-indigo-600 via-indigo-700 to-cyan-600 text-white shadow-xl relative overflow-hidden">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff0f_1px,transparent_1px),linear-gradient(to_bottom,#ffffff0f_1px,transparent_1px)] bg-[size:24px_24px]"></div>

        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="max-w-xl space-y-2">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 backdrop-blur-md text-xs font-semibold text-cyan-200 border border-white/20">
              <Sparkles className="w-3.5 h-3.5" /> Enterprise Knowledge Core
            </div>
            <h2 className="text-3xl font-extrabold tracking-tight">
              Welcome back, {user?.name || "AI Engineer"} 👋
            </h2>
            <p className="text-sm text-indigo-100/90 leading-relaxed">
              Your RAG pipeline is fully operational. Processed documents are vectorized into Qdrant using paragraph-aware chunking and 768D Gemini Embedding 2 embeddings.
            </p>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <Link
              href="/documents"
              className="px-4 py-2.5 rounded-xl bg-white text-indigo-700 hover:bg-indigo-50 font-semibold text-xs transition-all shadow-md flex items-center gap-2"
            >
              <UploadCloud className="w-4 h-4" />
              <span>Upload Document</span>
            </Link>
            <Link
              href="/chat"
              className="px-4 py-2.5 rounded-xl bg-white/15 hover:bg-white/25 backdrop-blur-md text-white font-semibold text-xs border border-white/20 transition-all flex items-center gap-2"
            >
              <MessageSquare className="w-4 h-4" />
              <span>Ask AI Chat</span>
            </Link>
          </div>
        </div>
      </div>

      {/* Quick Statistics Grid */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
            Engine Statistics
          </h3>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            Updated in real-time
          </span>
        </div>
        <StatsGrid stats={stats} loading={loadingStats} />
      </section>

      {/* System Health Panel */}
      <section className="space-y-3">
        <SystemHealthPanel health={health} loading={loadingStats} />
      </section>

      {/* Recent Knowledge Base Activity & AI Chat */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 p-6 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 shadow-sm space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
            <div className="flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
              <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
                Recent Knowledge Base Documents
              </h3>
            </div>
            <Link
              href="/documents"
              className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline flex items-center gap-1"
            >
              View All <ArrowUpRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {recentDocs.length > 0 ? (
            <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {recentDocs.map((doc) => (
                <div
                  key={doc.id}
                  className="py-3.5 flex items-center justify-between gap-4 first:pt-0 last:pb-0 hover:bg-slate-50/50 dark:hover:bg-slate-800/30 px-2 rounded-xl transition-colors"
                >
                  <div className="flex items-center gap-3.5 min-w-0">
                    <div className="w-10 h-10 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-100 dark:border-indigo-900/50 flex items-center justify-center text-indigo-600 dark:text-indigo-400 shrink-0">
                      <FileText className="w-5 h-5" />
                    </div>
                    <div className="min-w-0">
                      <span className="block text-sm font-bold text-slate-900 dark:text-slate-100 truncate">
                        {doc.name}
                      </span>
                      <span className="block text-xs text-slate-500 dark:text-slate-400">
                        {formatBytes(doc.size)} • {doc.chunkCount} chunks • {doc.uploadDate}
                      </span>
                    </div>
                  </div>

                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-900/50 shrink-0">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Indexed
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-8 text-center flex flex-col items-center justify-center space-y-4 my-2">
              <div className="w-12 h-12 rounded-2xl bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-100 dark:border-indigo-900/50 flex items-center justify-center text-indigo-500 dark:text-indigo-400">
                <FileText className="w-6 h-6" />
              </div>
              <div className="space-y-1">
                <h4 className="text-base font-bold text-slate-900 dark:text-slate-100">
                  No documents uploaded yet
                </h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 max-w-sm">
                  Upload your first PDF to build your knowledge base.
                </p>
              </div>
              <Link
                href="/documents"
                className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-md transition-all flex items-center gap-2"
              >
                <UploadCloud className="w-4 h-4" />
                <span>Upload Document</span>
              </Link>
            </div>
          )}
        </div>

        {/* AI Chat Card */}
        <div className="p-6 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 shadow-sm flex flex-col justify-between space-y-6">
          <div className="space-y-3">
            <div className="w-10 h-10 rounded-xl bg-cyan-50 dark:bg-cyan-950/60 border border-cyan-100 dark:border-cyan-900/50 flex items-center justify-center text-cyan-600 dark:text-cyan-400">
              <MessageSquare className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
              AI Chat
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              Launch an interactive chat session to query your indexed Qdrant document vectors.
            </p>
          </div>

          {recentDocs.length > 0 ? (
            <Link
              href="/chat"
              className="w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs rounded-xl shadow-md transition-all flex items-center justify-center gap-2"
            >
              <span>Open AI Chat Window</span>
              <ArrowUpRight className="w-4 h-4" />
            </Link>
          ) : (
            <button
              disabled
              className="w-full py-3 px-4 bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500 font-semibold text-xs rounded-xl cursor-not-allowed flex items-center justify-center gap-2"
            >
              <span>Upload documents to enable AI chat.</span>
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
