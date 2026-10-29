export type DocumentIndexFileType = 'pdf' | 'pptx' | 'txt';

export interface DocumentIndexSearchResult {
  page_id: string;
  file_name: string;
  file_type: DocumentIndexFileType;
  page_number: number;
  snippet: string;
}

export interface DocumentIndexPage {
  page_id: string;
  file_name: string;
  file_type: DocumentIndexFileType;
  page_number: number;
  text_content: string;
  created_at: string;
}

export interface AskIndexSource {
  file_name: string;
  file_type: DocumentIndexFileType;
  page_number: number;
}

export interface AskIndexResponse {
  answer: string;
  sources: AskIndexSource[];
  offer_support: boolean;
}
