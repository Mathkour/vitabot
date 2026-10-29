export interface Company {
  id: string;
  name: string;
  created_at: string;
  user_count: number;
}

export interface CompanyRequest {
  name: string;
}
