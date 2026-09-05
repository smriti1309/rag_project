import {
  DashboardStats,
  DocumentItem,
  ChatSession,
  SystemHealth,
  SystemSettings,
  UserProfile,
} from "@/types";

export const mockUser: UserProfile = {
  name: "Alex Rivera",
  email: "demo@knowledge.ai",
  role: "AI Systems Engineer",
  avatar: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80",
};

export const mockDashboardStats: DashboardStats = {
  documentsIndexed: 8,
  totalChunks: 1245,
  totalEmbeddings: 1245,
  vectorDbStatus: "Connected",
  lastIndexedTime: "2026-07-30 16:25:33",
};

export const mockSystemHealth: SystemHealth = {
  backendStatus: "Healthy (FastAPI v1.0.0)",
  vectorDbStatus: "Connected (Qdrant v1.7.0)",
  embeddingModel: "gemini-embedding-2 (768-dim)",
  lastIndexedTime: "2026-07-30 16:25:33",
};

export const mockDocuments: DocumentItem[] = [];

export const mockChatSessions: ChatSession[] = [];

export const mockSystemSettings: SystemSettings = {
  embeddingModel: "gemini-embedding-2",
  embeddingDimension: 768,
  embeddingBatchSize: 32,
  vectorDbUrl: "http://localhost:6333",
  vectorDbCollection: "knowledge_base_v2",
  vectorBatchSize: 500,
  vectorMetric: "Cosine",
  llmProvider: "Gemini 3.6 Flash",
  llmModel: "gemini-3.6-flash",
  chunkStrategy: "Paragraph-Aware Chunking",
  chunkMaxWords: 500,
  chunkOverlap: 30,
};
