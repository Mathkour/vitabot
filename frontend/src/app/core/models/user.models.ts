export interface CompanyUser {
  id: string;
  email: string;
  role: string;
  username?: string;
  company_id?: string | null;
  company_name?: string | null;
}

export interface UsersListParams {
  search?: string;
  page?: number;
  page_size?: number;
  company_id?: string;
}

export interface CreateUserRequest {
  email: string;
  username: string;
  password: string;
  role: string;
  company_id?: string | null;
}

export interface UpdateUserRequest {
  role?: string;
  company_id?: string | null;
}

export interface UsersListResponse {
  users: CompanyUser[];
  total: number;
  total_pages: number;
}

export interface ImportColumnMapping {
  email: number | string | null;
  username: number | string | null;
  role: number | string | null;
}

export interface ImportPreviewResponse {
  headers: string[];
  mapping: ImportColumnMapping;
  preview: string[][];
  total_rows: number;
}

export interface ImportConfirmRequest {
  mapping: ImportColumnMapping;
  rows: string[][];
}

export interface ImportConfirmResponse {
  imported: number;
  skipped: number;
}
