"use client";

import React, { useState, useRef } from "react";
import { UploadCloud, FileText, CheckCircle2, AlertCircle, Sparkles } from "lucide-react";
import { cn, formatBytes } from "@/lib/utils";
import { getAuthHeaders } from "@/lib/supabase/client";

interface UploadAreaProps {
  onUploadSuccess: (newDoc: any) => void;
}

export function UploadArea({ onUploadSuccess }: UploadAreaProps) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const allowedExtensions = [".pdf", ".txt", ".docx", ".png", ".jpg", ".jpeg", ".webp"];

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
      if (allowedExtensions.includes(ext)) {
        setSelectedFile(file);
      } else {
        alert("Only PDF, TXT, DOCX, PNG, JPG, JPEG, and WEBP files are supported.");
      }
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
    }
  };

  const [error, setError] = useState<string | null>(null);

  const handleRealUpload = async () => {
    if (!selectedFile) return;
    setUploading(true);
    setProgress(0);
    setStatusText("Initiating upload...");
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
      const authHeaders = await getAuthHeaders();

      const res = await fetch(`${apiUrl}/upload`, {
        method: "POST",
        headers: {
          ...authHeaders,
        },
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Upload failed with status ${res.status}`);
      }

      if (!res.body) {
        throw new Error("No response body received from server");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let completedData: any = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;

          try {
            const event = JSON.parse(trimmed);
            if (event.stage === "failed") {
              throw new Error(event.error || "Ingestion pipeline failed.");
            }

            if (typeof event.progress === "number") {
              setProgress(event.progress);
            }
            if (event.message) {
              setStatusText(event.message);
            }

            if (event.stage === "completed" && event.data) {
              completedData = event.data;
            }
          } catch (parseErr: any) {
            if (parseErr instanceof Error && parseErr.message !== line) {
              throw parseErr;
            }
          }
        }
      }

      if (completedData) {
        const newDoc = {
          id: completedData.document_id,
          name: completedData.original_filename,
          originalFilename: completedData.original_filename,
          size: completedData.size,
          uploadDate: new Date(completedData.uploaded_at).toISOString().replace("T", " ").substring(0, 19),
          chunkCount: completedData.chunk_count || 0,
          status: (completedData.status as any) || "indexed",
          fileType: completedData.file_type || "pdf",
        };

        onUploadSuccess(newDoc);
        setSelectedFile(null);
        setProgress(0);
        setStatusText("");
      } else {
        throw new Error("Ingestion stream ended without completing.");
      }
    } catch (err: any) {
      setError(err?.message || "Failed to upload document to backend.");
      setProgress(0);
      setStatusText("");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="p-6 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 shadow-sm space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <UploadCloud className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            Upload Document or Image
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Cloudflare R2 object storage with Supabase metadata & Qdrant vector indexing
          </p>
        </div>

        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-400 border border-indigo-100 dark:border-indigo-900/50">
          <Sparkles className="w-3.5 h-3.5" /> Max 50MB
        </span>
      </div>

      {/* Drag & Drop Zone */}
      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "p-8 rounded-xl border-2 border-dashed transition-all cursor-pointer flex flex-col items-center justify-center gap-3 text-center",
          dragActive
            ? "border-indigo-500 bg-indigo-50/50 dark:bg-indigo-950/30"
            : "border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 hover:bg-slate-100/50 dark:hover:bg-slate-800/40"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt,.docx,.png,.jpg,.jpeg,.webp"
          onChange={handleChange}
          className="hidden"
        />

        <div className="w-12 h-12 rounded-2xl bg-indigo-100 dark:bg-indigo-950/80 text-indigo-600 dark:text-indigo-400 flex items-center justify-center shadow-xs">
          <UploadCloud className="w-6 h-6" />
        </div>

        {selectedFile ? (
          <div className="space-y-1">
            <span className="block text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2 justify-center">
              <FileText className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
              {selectedFile.name}
            </span>
            <span className="block text-xs text-slate-500 dark:text-slate-400">
              {formatBytes(selectedFile.size)} • Click to change file
            </span>
          </div>
        ) : (
          <div className="space-y-1">
            <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Drag and drop your file here, or <span className="text-indigo-600 dark:text-indigo-400 underline">browse</span>
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Supports PDF, TXT, DOCX, PNG, JPG, JPEG, and WEBP formats
            </p>
          </div>
        )}
      </div>

      {/* Selected File & Simulated Upload Action */}
      {selectedFile && (
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/60">
          <div className="flex items-center gap-3 min-w-0">
            <FileText className="w-5 h-5 text-indigo-600 dark:text-indigo-400 shrink-0" />
            <div className="min-w-0">
              <span className="block text-xs font-bold text-slate-900 dark:text-slate-100 truncate">
                {selectedFile.name}
              </span>
              <span className="block text-[11px] text-slate-500 dark:text-slate-400">
                Ready for automated pipeline execution
              </span>
            </div>
          </div>

          <button
            onClick={handleRealUpload}
            disabled={uploading}
            className="w-full sm:w-auto py-2.5 px-5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs rounded-xl shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-60"
          >
            {uploading ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                <span>Indexing...</span>
              </>
            ) : (
              <>
                <UploadCloud className="w-4 h-4" />
                <span>Upload & Index Document</span>
              </>
            )}
          </button>
        </div>
      )}

      {/* Error Alert */}
      {error && (
        <div className="p-4 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/50 text-red-700 dark:text-red-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-red-500" />
          <span>{error}</span>
        </div>
      )}

      {/* Progress Bar */}
      {uploading && (
        <div className="space-y-2 p-4 rounded-xl bg-indigo-50/70 dark:bg-indigo-950/40 border border-indigo-100 dark:border-indigo-900/50">
          <div className="flex items-center justify-between text-xs font-semibold text-indigo-900 dark:text-indigo-200">
            <span>{statusText}</span>
            <span>{progress}%</span>
          </div>
          <div className="w-full bg-indigo-200 dark:bg-indigo-900/60 h-2 rounded-full overflow-hidden">
            <div
              className="bg-indigo-600 dark:bg-indigo-400 h-full transition-all duration-300 rounded-full"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
