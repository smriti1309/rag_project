"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";
import { ChatSession, ChatMessage, DocumentItem, ChatCitation } from "@/types";
import {
  Plus,
  MessageSquare,
  Send,
  Sparkles,
  Bot,
  User,
  Trash2,
  Database,
  FileText,
  UploadCloud,
  CheckCircle2,
  Loader2,
  AlertCircle,
  Zap,
  Filter,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getAuthHeaders } from "@/lib/supabase/client";

export default function ChatPage() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [inputPrompt, setInputPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string>("all");
  const [expandedPassages, setExpandedPassages] = useState<Record<string, boolean>>({});
  const [expandedRetrievalDetails, setExpandedRetrievalDetails] = useState<Record<string, boolean>>({});

  const togglePassage = (key: string) => {
    setExpandedPassages((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const toggleRetrievalDetails = (msgId: string) => {
    setExpandedRetrievalDetails((prev) => ({
      ...prev,
      [msgId]: !prev[msgId],
    }));
  };
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const activeSession = sessions.find((s) => s.id === activeSessionId) || null;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [activeSession?.messages, loading]);

  // Fetch user documents for optional context filtering
  useEffect(() => {
    const fetchUserDocuments = async () => {
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
        console.error("Failed to fetch documents for chat selector:", err);
      }
    };

    fetchUserDocuments();
  }, []);

  // Fetch user conversations from backend
  const fetchConversations = useCallback(async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
      const authHeaders = await getAuthHeaders();
      const res = await fetch(`${apiUrl}/conversations`, {
        headers: authHeaders,
      });

      if (res.ok) {
        const data = await res.json();
        const mappedSessions: ChatSession[] = data.map((c: any) => ({
          id: c.id,
          title: c.title || "New Conversation",
          updatedAt: new Date(c.updated_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
          messages: [],
        }));

        setSessions(mappedSessions);

        if (mappedSessions.length > 0) {
          setActiveSessionId((prev) => {
            if (prev && mappedSessions.some((s) => s.id === prev)) {
              return prev;
            }
            return mappedSessions[0].id;
          });
        }
      }
    } catch (err) {
      console.error("Failed to fetch user conversations:", err);
    }
  }, []);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // Load messages for the active conversation
  const loadMessagesForSession = useCallback(async (sessionId: string) => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
      const authHeaders = await getAuthHeaders();
      const res = await fetch(`${apiUrl}/conversations/${sessionId}/messages`, {
        headers: authHeaders,
      });

      if (res.ok) {
        const data = await res.json();
        const mappedMessages: ChatMessage[] = data.map((m: any) => ({
          id: m.id,
          role: m.role as "user" | "assistant",
          content: m.content,
          timestamp: new Date(m.created_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
          citations: (m.citations || []).map((src: any) => ({
            documentId: src.document_id || src.documentId || "",
            chunkId: src.chunk_id !== undefined ? src.chunk_id : src.chunkId || 0,
            page: src.page,
            sourceFile: src.source_file || src.sourceFile,
            score: src.score,
            text: src.text || src.snippet,
          })),
          retrievedChunkCount: m.retrieved_chunk_count,
          retrievalTimeMs: m.retrieval_time_ms,
        }));

        setSessions((prev) =>
          prev.map((s) => (s.id === sessionId ? { ...s, messages: mappedMessages } : s))
        );
      }
    } catch (err) {
      console.error(`Failed to load messages for session ${sessionId}:`, err);
    }
  }, []);

  useEffect(() => {
    if (activeSessionId) {
      loadMessagesForSession(activeSessionId);
    }
  }, [activeSessionId, loadMessagesForSession]);

  // Create new conversation via backend API
  const handleNewChat = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
      const authHeaders = await getAuthHeaders();
      const res = await fetch(`${apiUrl}/conversations`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders,
        },
        body: JSON.stringify({ title: "New Conversation" }),
      });

      if (res.ok) {
        const data = await res.json();
        const newSession: ChatSession = {
          id: data.id,
          title: data.title || "New Conversation",
          updatedAt: "Just now",
          messages: [],
        };
        setSessions((prev) => [newSession, ...prev]);
        setActiveSessionId(data.id);
      }
    } catch (err) {
      console.error("Failed to create new conversation session:", err);
    }
  };

  // Delete conversation via backend API
  const handleDeleteSession = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
      const authHeaders = await getAuthHeaders();
      const res = await fetch(`${apiUrl}/conversations/${id}`, {
        method: "DELETE",
        headers: authHeaders,
      });

      if (res.ok || res.status === 404) {
        const updated = sessions.filter((s) => s.id !== id);
        setSessions(updated);
        if (activeSessionId === id) {
          setActiveSessionId(updated.length > 0 ? updated[0].id : null);
        }
      }
    } catch (err) {
      console.error("Failed to delete conversation:", err);
    }
  };

  const handleSendMessage = async () => {
    const query = inputPrompt.trim();
    if (!query || loading) return;

    setInputPrompt("");

    let currentSessionId = activeSessionId;

    // Auto-create a session if none is selected
    if (!currentSessionId) {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
        const authHeaders = await getAuthHeaders();
        const res = await fetch(`${apiUrl}/conversations`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...authHeaders,
          },
          body: JSON.stringify({
            title: query.length > 25 ? query.substring(0, 25) + "..." : query,
          }),
        });

        if (res.ok) {
          const data = await res.json();
          currentSessionId = data.id;
          const newSession: ChatSession = {
            id: currentSessionId!,
            title: data.title || query,
            updatedAt: "Just now",
            messages: [],
          };
          setSessions((prev) => [newSession, ...prev]);
          setActiveSessionId(currentSessionId);
        }
      } catch (err) {
        console.error("Failed to auto-create session:", err);
      }
    }

    const userMessage: ChatMessage = {
      id: `msg-temp-${Date.now()}`,
      role: "user",
      content: query,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    // Update state immediately with user message for instant feedback
    setSessions((prev) =>
      prev.map((s) => {
        if (s.id === currentSessionId) {
          const isFirstMessage = s.messages.length === 0;
          return {
            ...s,
            title: isFirstMessage
              ? query.length > 25
                ? query.substring(0, 25) + "..."
                : query
              : s.title,
            messages: [...s.messages, userMessage],
          };
        }
        return s;
      })
    );

    setLoading(true);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
      const authHeaders = await getAuthHeaders();

      const payload = {
        query: query,
        document_id: selectedDocId === "all" ? null : selectedDocId,
        conversation_id: currentSessionId,
        top_k: 5,
      };

      const res = await fetch(`${apiUrl}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders,
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error (${res.status})`);
      }

      const data = await res.json();

      // Refresh messages from backend to sync persisted message IDs and metadata
      if (data.conversation_id) {
        loadMessagesForSession(data.conversation_id);
        fetchConversations();
      }
    } catch (err: any) {
      console.error("Chat backend error:", err);
      const errorMessage: ChatMessage = {
        id: `msg-${Date.now()}-error`,
        role: "assistant",
        content: err?.message || "Failed to generate AI response. Please try again.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        isError: true,
      };

      setSessions((prev) =>
        prev.map((s) =>
          s.id === currentSessionId
            ? { ...s, messages: [...s.messages, errorMessage] }
            : s
        )
      );
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="h-[calc(100vh-6rem)] -mb-12 flex flex-col md:flex-row gap-6 overflow-hidden">
      {/* Left Sidebar - AI Chat History */}
      <div className="w-full md:w-72 bg-white dark:bg-slate-900 rounded-3xl border border-slate-200/80 dark:border-slate-800 shadow-sm flex flex-col justify-between shrink-0 overflow-hidden">
        {/* Top New Chat Button */}
        <div className="p-4 border-b border-slate-100 dark:border-slate-800">
          <button
            onClick={handleNewChat}
            className="w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs rounded-2xl shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            <span>New Chat Session</span>
          </button>
        </div>

        {/* Chat History List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          <span className="block px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
            Recent Conversations
          </span>

          {sessions.length === 0 ? (
            <div className="p-6 text-center text-xs text-slate-400 dark:text-slate-500 space-y-1">
              <p className="font-semibold">No recent conversations</p>
              <p className="text-[11px]">Start a new session above</p>
            </div>
          ) : (
            sessions.map((session) => {
              const isActive = session.id === activeSessionId;
              return (
                <div
                  key={session.id}
                  onClick={() => setActiveSessionId(session.id)}
                  className={cn(
                    "group p-3 rounded-2xl cursor-pointer transition-all flex items-center justify-between gap-2 text-xs",
                    isActive
                      ? "bg-indigo-50 dark:bg-indigo-950/60 text-indigo-900 dark:text-indigo-200 font-semibold shadow-xs"
                      : "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800/60"
                  )}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <MessageSquare
                      className={cn(
                        "w-4 h-4 shrink-0",
                        isActive ? "text-indigo-600 dark:text-indigo-400" : "text-slate-400"
                      )}
                    />
                    <span className="truncate">{session.title}</span>
                  </div>

                  <button
                    onClick={(e) => handleDeleteSession(session.id, e)}
                    title="Delete chat"
                    className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-rose-600 transition-opacity cursor-pointer"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })
          )}
        </div>

        {/* Sidebar Footer Context */}
        <div className="p-4 border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 text-xs text-slate-500 dark:text-slate-400 space-y-1">
          <div className="flex items-center gap-1.5 font-semibold text-slate-700 dark:text-slate-300">
            <Database className="w-3.5 h-3.5 text-emerald-500" />
            <span>Qdrant: knowledge_base_v2</span>
          </div>
          <p className="text-[11px] text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> Backend Connected
          </p>
        </div>
      </div>

      {/* Right Main Chat Area */}
      <div className="flex-1 bg-white dark:bg-slate-900 rounded-3xl border border-slate-200/80 dark:border-slate-800 shadow-sm flex flex-col justify-between overflow-hidden relative">
        {/* Chat Window Header */}
        <div className="p-4 px-6 border-b border-slate-100 dark:border-slate-800 flex flex-wrap items-center justify-between gap-3 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md z-10">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-cyan-500 text-white flex items-center justify-center shadow-xs">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                {activeSession?.title || "AI Knowledge Assistant"}
              </h3>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-cyan-500" /> Vector Context: Qdrant Index
              </p>
            </div>
          </div>

          {/* Context Scope Selector */}
          <div className="flex items-center gap-2">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={selectedDocId}
              onChange={(e) => setSelectedDocId(e.target.value)}
              className="px-3 py-1.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer text-slate-700 dark:text-slate-300 max-w-[200px] truncate"
            >
              <option value="all">All Documents ({documents.length})</option>
              {documents.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.name}
                </option>
              ))}
            </select>

            <span className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-900/50">
              <CheckCircle2 className="w-3.5 h-3.5" /> RAG Ready
            </span>
          </div>
        </div>

        {/* Scrollable Message Feed / Empty State */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {!activeSession || activeSession.messages.length === 0 ? (
            /* Empty Chat State */
            <div className="h-full flex flex-col items-center justify-center text-center space-y-6 max-w-md mx-auto py-12">
              <div className="w-16 h-16 rounded-3xl bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-100 dark:border-indigo-900/50 flex items-center justify-center text-indigo-600 dark:text-indigo-400 shadow-xs">
                <MessageSquare className="w-8 h-8" />
              </div>
              <div className="space-y-2">
                <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100">
                  No conversations yet
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                  Upload documents and start asking questions about your knowledge base.
                </p>
              </div>

              <Link
                href="/documents"
                className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-md hover:shadow-lg transition-all flex items-center gap-2"
              >
                <UploadCloud className="w-4 h-4" />
                <span>Upload Documents</span>
              </Link>
            </div>
          ) : (
            <>
              {activeSession.messages.map((msg) => (
                <div
                  key={msg.id}
                  className={cn(
                    "flex gap-4 max-w-3xl",
                    msg.role === "user" ? "ml-auto flex-row-reverse" : "mr-auto"
                  )}
                >
                  {/* Avatar */}
                  <div
                    className={cn(
                      "w-8 h-8 rounded-xl flex items-center justify-center shrink-0 text-white text-xs shadow-xs",
                      msg.role === "user"
                        ? "bg-indigo-600"
                        : msg.isError
                        ? "bg-rose-600"
                        : "bg-gradient-to-tr from-indigo-600 to-cyan-500"
                    )}
                  >
                    {msg.role === "user" ? (
                      <User className="w-4 h-4" />
                    ) : msg.isError ? (
                      <AlertCircle className="w-4 h-4" />
                    ) : (
                      <Bot className="w-4 h-4" />
                    )}
                  </div>

                  {/* Bubble Content */}
                  <div className="space-y-2 max-w-full">
                    <div
                      className={cn(
                        "p-4 rounded-3xl text-xs leading-relaxed shadow-xs whitespace-pre-wrap",
                        msg.role === "user"
                          ? "bg-indigo-600 text-white rounded-tr-none font-medium"
                          : msg.isError
                          ? "bg-rose-50 dark:bg-rose-950/40 text-rose-900 dark:text-rose-200 rounded-tl-none border border-rose-200 dark:border-rose-900/50"
                          : "bg-slate-100 dark:bg-slate-800/80 text-slate-900 dark:text-slate-100 rounded-tl-none border border-slate-200/60 dark:border-slate-700/60"
                      )}
                    >
                      {msg.content}
                    </div>

                    {/* Expandable Retrieval Details Container */}
                    {msg.role === "assistant" && !msg.isError && msg.citations && msg.citations.length > 0 && (
                      <div className="pt-2">
                        <div className="rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/80 dark:border-slate-700/80 overflow-hidden transition-all">
                          {/* Collapsed Medium-Sized Bar (~50-60px tall) */}
                          <div
                            onClick={() => toggleRetrievalDetails(msg.id)}
                            className="p-3.5 px-4 flex items-center justify-between gap-3 cursor-pointer hover:bg-slate-100/60 dark:hover:bg-slate-800/90 transition-colors select-none"
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              <div className="w-8 h-8 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-100 dark:border-indigo-900/50 flex items-center justify-center text-indigo-600 dark:text-indigo-400 shrink-0">
                                <Database className="w-4 h-4" />
                              </div>
                              <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 truncate">
                                {msg.citations.length} relevant sources
                              </span>
                            </div>

                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleRetrievalDetails(msg.id);
                              }}
                              className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300 transition-colors shrink-0 cursor-pointer"
                            >
                              <span>
                                {expandedRetrievalDetails[msg.id]
                                  ? "Hide retrieval details"
                                  : "View retrieval details"}
                              </span>
                              {expandedRetrievalDetails[msg.id] ? (
                                <ChevronUp className="w-4 h-4" />
                              ) : (
                                <ChevronDown className="w-4 h-4" />
                              )}
                            </button>
                          </div>

                          {/* Expanded Sources Content */}
                          {expandedRetrievalDetails[msg.id] && (
                            <div className="p-3 pt-0 space-y-2 border-t border-slate-200/60 dark:border-slate-700/60">
                              <div className="pt-2 space-y-2">
                                {msg.citations.map((cite, idx) => {
                                  const rank = idx + 1;
                                  const rankLabel =
                                    rank === 1
                                      ? "Most relevant"
                                      : rank === 2
                                      ? "Highly relevant"
                                      : "Relevant";
                                  const passageText = cite.text || cite.snippet;
                                  const key = `${msg.id}-${idx}`;
                                  const isPassageExpanded = !!expandedPassages[key];

                                  return (
                                    <div
                                      key={idx}
                                      className="p-2.5 rounded-xl bg-white dark:bg-slate-900/70 border border-slate-200/80 dark:border-slate-800 text-xs space-y-2 transition-all"
                                    >
                                      {/* Source header & rank badge */}
                                      <div className="flex flex-wrap items-center justify-between gap-2">
                                        <div className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-200 min-w-0">
                                          <FileText className="w-4 h-4 text-indigo-500 shrink-0" />
                                          <span className="truncate max-w-[180px] sm:max-w-[240px]">
                                            {cite.sourceFile || cite.documentId.substring(0, 8)}
                                          </span>
                                          {cite.page !== null && cite.page !== undefined && (
                                            <span className="text-[11px] text-slate-500 dark:text-slate-400 font-normal shrink-0">
                                              Page {cite.page}
                                            </span>
                                          )}
                                        </div>

                                        <span
                                          className={cn(
                                            "px-2.5 py-0.5 rounded-full text-[10px] font-semibold border shrink-0",
                                            rank === 1
                                              ? "bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800"
                                              : rank === 2
                                              ? "bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800"
                                              : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700"
                                          )}
                                        >
                                          #{rank} · {rankLabel}
                                        </span>
                                      </div>

                                      {/* Passage toggle button & expanded full text */}
                                      {passageText && (
                                        <div>
                                          {isPassageExpanded ? (
                                            <div className="space-y-2 pt-1">
                                              <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-950/80 border border-slate-200/60 dark:border-slate-800/80 text-[11px] text-slate-600 dark:text-slate-300 leading-relaxed font-normal whitespace-pre-wrap">
                                                "{passageText}"
                                              </div>
                                              <div className="flex justify-end">
                                                <button
                                                  type="button"
                                                  onClick={() => togglePassage(key)}
                                                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300 transition-colors cursor-pointer"
                                                >
                                                  <ChevronUp className="w-3.5 h-3.5" />
                                                  <span>Hide passage</span>
                                                </button>
                                              </div>
                                            </div>
                                          ) : (
                                            <div className="flex justify-end pt-0.5">
                                              <button
                                                type="button"
                                                onClick={() => togglePassage(key)}
                                                className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300 transition-colors cursor-pointer"
                                              >
                                                <ChevronDown className="w-3.5 h-3.5" />
                                                <span>View passage</span>
                                              </button>
                                            </div>
                                          )}
                                        </div>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    <span className="block text-[10px] text-slate-400 dark:text-slate-500 px-1">
                      {msg.timestamp}
                    </span>
                  </div>
                </div>
              ))}

              {/* Animated Loading State */}
              {loading && (
                <div className="flex gap-4 max-w-3xl mr-auto">
                  <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-indigo-600 to-cyan-500 text-white flex items-center justify-center shrink-0 shadow-xs">
                    <Bot className="w-4 h-4" />
                  </div>
                  <div className="p-4 rounded-3xl text-xs bg-slate-100 dark:bg-slate-800/80 text-slate-600 dark:text-slate-300 rounded-tl-none border border-slate-200/60 dark:border-slate-700/60 flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin text-indigo-600 dark:text-indigo-400" />
                    <span>Searching Qdrant vector index & generating grounded response...</span>
                  </div>
                </div>
              )}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Sticky Input Bar at Bottom */}
        <div className="p-4 border-t border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900">
          <div className="relative flex items-center bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700/80 rounded-2xl p-2 focus-within:ring-2 focus-within:ring-indigo-500 transition-all">
            <textarea
              rows={2}
              disabled={loading}
              value={inputPrompt}
              onChange={(e) => setInputPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                loading
                  ? "Generating response..."
                  : "Ask a question about your uploaded documents (Press Enter to send)..."
              }
              className="w-full bg-transparent text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none resize-none px-2"
            />
            <button
              onClick={handleSendMessage}
              disabled={loading || !inputPrompt.trim()}
              className={cn(
                "p-3 rounded-xl shrink-0 self-end mb-1 transition-all cursor-pointer",
                !inputPrompt.trim() || loading
                  ? "bg-slate-200 dark:bg-slate-800 text-slate-400 dark:text-slate-600 cursor-not-allowed"
                  : "bg-indigo-600 hover:bg-indigo-700 text-white shadow-md hover:shadow-lg"
              )}
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
          <div className="flex items-center justify-between text-[10px] text-slate-400 dark:text-slate-500 px-2 mt-2">
            <span>Powered by Gemini 3.6 Flash & Qdrant Cloud RAG</span>
            <span className="text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> RAG Engine Connected
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
