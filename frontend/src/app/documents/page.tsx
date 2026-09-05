"use client";

import React, { useState, useEffect } from "react";
import { UploadArea } from "@/components/features/documents/UploadArea";
import { DocumentCard } from "@/components/features/documents/DocumentCard";
import { DocumentItem } from "@/types";
import { Search, Filter, Database, FileX2, Sparkles, X, CheckCircle2, Layers } from "lucide-react";
import { formatBytes } from "@/lib/utils";
import { getAuthHeaders } from "@/lib/supabase/client";

export default function KnowledgeBasePage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedDoc, setSelectedDoc] = useState<DocumentItem | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchDocuments = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
      const authHeaders = await getAuthHeaders();
      const res = await fetch(`${apiUrl}/documents`, {
        headers: authHeaders,
      });
      if (res.ok) {
        const data = await res.json();
        const mappedDocs: DocumentItem[] = data.map((d: any) => ({
          id: d.document_id,
          name: d.original_filename,
          originalFilename: d.original_filename,
          size: d.size,
          uploadDate: new Date(d.uploaded_at).toISOString().replace("T", " ").substring(0, 19),
          chunkCount: d.chunk_count || 0,
          status: (d.status as any) || "indexed",
        }));
        setDocuments(mappedDocs);
      }
    } catch (err) {
      console.error("Failed to fetch documents:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleUploadSuccess = (newDoc: DocumentItem) => {
    setDocuments((prev) => [newDoc, ...prev.filter((d) => d.id !== newDoc.id)]);
  };

  const handleDelete = async (id: string) => {
    if (confirm("Are you sure you want to delete this document?")) {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
        const authHeaders = await getAuthHeaders();
        const res = await fetch(`${apiUrl}/documents/${id}`, {
          method: "DELETE",
          headers: authHeaders,
        });
        if (res.ok) {
          setDocuments((prev) => prev.filter((doc) => doc.id !== id));
        } else {
          const errData = await res.json().catch(() => ({}));
          alert(errData.detail || "Failed to delete document.");
        }
      } catch (err: any) {
        alert("Error deleting document: " + (err?.message || "Server error"));
      }
    }
  };

  const filteredDocs = documents.filter((doc) => {
    const matchesSearch = doc.name.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === "all" || doc.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="space-y-8 pb-12">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2.5">
            Knowledge Base
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Manage parsed documents, chunk JSONs, and Qdrant vector embeddings
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <span className="px-3 py-1.5 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-100 dark:border-indigo-900/50 text-xs font-semibold text-indigo-600 dark:text-indigo-400 flex items-center gap-1.5">
            <Database className="w-3.5 h-3.5" /> {documents.length} Documents Indexed
          </span>
        </div>
      </div>

      {/* Top Upload Area Component */}
      <UploadArea onUploadSuccess={handleUploadSuccess} />

      {/* Search & Filter Toolbar */}
      <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="relative w-full sm:w-80">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search documents by title..."
            className="w-full pl-9 pr-3 py-2 bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700/80 rounded-xl text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
          <Filter className="w-4 h-4 text-slate-400" />
          <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Status:</span>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700/80 rounded-xl text-xs font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all cursor-pointer"
          >
            <option value="all">All Documents ({documents.length})</option>
            <option value="indexed">Indexed</option>
            <option value="processing">Processing</option>
            <option value="failed">Failed</option>
          </select>
        </div>
      </div>

      {/* Documents Grid / Empty State */}
      {filteredDocs.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredDocs.map((doc) => (
            <DocumentCard
              key={doc.id}
              document={doc}
              onDelete={handleDelete}
              onView={(d) => setSelectedDoc(d)}
            />
          ))}
        </div>
      ) : (
        /* Empty State Component */
        <div className="p-12 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 shadow-sm text-center flex flex-col items-center justify-center space-y-4">
          <div className="w-16 h-16 rounded-2xl bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-100 dark:border-indigo-900/50 flex items-center justify-center text-indigo-500 dark:text-indigo-400">
            <FileX2 className="w-8 h-8" />
          </div>

          <div className="space-y-1 max-w-sm">
            <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">
              No documents uploaded
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              Drag & drop a PDF to begin building your knowledge base.
            </p>
          </div>
        </div>
      )}

      {/* Document Metadata Modal */}
      {selectedDoc && (
        <div className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="w-full max-w-2xl bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-2xl p-6 space-y-6 max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-slate-800">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-100 dark:border-indigo-900/50 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
                  <Layers className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
                    {selectedDoc.name}
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Parsed Document Metadata & Qdrant Vector Status
                  </p>
                </div>
              </div>

              <button
                onClick={() => setSelectedDoc(null)}
                className="p-2 rounded-xl text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="overflow-y-auto space-y-4 pr-1">
              <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200/60 dark:border-slate-700/60 space-y-3">
                <div className="flex items-center justify-between text-xs font-semibold text-slate-700 dark:text-slate-300">
                  <span>Document ID:</span>
                  <span className="font-mono text-indigo-600 dark:text-indigo-400">{selectedDoc.id}</span>
                </div>
                <div className="flex items-center justify-between text-xs font-semibold text-slate-700 dark:text-slate-300">
                  <span>File Size:</span>
                  <span>{formatBytes(selectedDoc.size)}</span>
                </div>
                <div className="flex items-center justify-between text-xs font-semibold text-slate-700 dark:text-slate-300">
                  <span>Uploaded Timestamp:</span>
                  <span>{selectedDoc.uploadDate}</span>
                </div>
                <div className="flex items-center justify-between text-xs font-semibold text-slate-700 dark:text-slate-300">
                  <span>Generated Chunks:</span>
                  <span>{selectedDoc.chunkCount} chunks</span>
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-xs">
              <span className="text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4" /> Indexed in Qdrant Vector DB
              </span>
              <button
                onClick={() => setSelectedDoc(null)}
                className="px-4 py-2 bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 font-semibold rounded-xl hover:opacity-90 transition-opacity cursor-pointer"
              >
                Close Metadata
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
