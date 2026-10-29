export interface DocumentUploadResponse {
  document_id: string;
  filename: string;
  display_name?: string | null;
  chunks_created: number;
  status: 'ready' | string;
}

export interface DocumentListItem {
  id: string;
  filename: string;
  display_name?: string | null;
  status: string;
  created_at: string;
}
