export type DocumentStatus = "indexed" | "processing" | "failed";

export interface DocumentItem {
  id: string;
  name: string;
  originalFilename: string;
  size: number;
  uploadDate: string;
  chunkCount: number;
  status: DocumentStatus;
  pageCount?: number;
}

export interface DashboardStats {
  documentsIndexed: number;
  totalChunks: number;
  totalEmbeddings: number;
  vectorDbStatus: "Connected" | "Disconnected";
  lastUploadedTime: string | null;
}

export interface SystemHealth {
  backendStatus: string;
  vectorDbStatus: string;
  embeddingModel: string;
  lastUploadedTime: string | null;
}

export interface ChatCitation {
  documentId: string;
  chunkId: number;
  page?: number | null;
  sourceFile?: string | null;
  score?: number;
  snippet?: string;
  text?: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  citations?: ChatCitation[];
  retrievedChunkCount?: number;
  retrievalTimeMs?: number;
  isError?: boolean;
}

export interface ChatSession {
  id: string;
  title: string;
  updatedAt: string;
  messages: ChatMessage[];
}

export interface SystemSettings {
  embeddingModel: string;
  embeddingDimension: number;
  embeddingBatchSize: number;
  vectorDbUrl: string;
  vectorDbCollection: string;
  vectorBatchSize: number;
  vectorMetric: string;
  llmProvider: string;
  llmModel: string;
  chunkStrategy: string;
  chunkMaxWords: number;
  chunkOverlap: number;
}

export interface UserProfile {
  name: string;
  email: string;
  role: string;
  avatar: string;
}
