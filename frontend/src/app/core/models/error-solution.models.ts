export interface ErrorSolutionItem {
  id: string;
  error_text: string;
  solution_text: string;
  error_text_ar?: string | null;
  solution_text_ar?: string | null;
  category_id?: string | null;
}

export interface ErrorSolutionImportResponse {
  status: string;
  created: number;
  skipped: number;
}
