import { TenantBranding } from './tenant.models';

export interface SuperadminTenant extends TenantBranding {
  id: string;
  created_at: string;
}

export interface CreateTenantRequest {
  company_name: string;
  email: string;
  password: string;
}

export interface CreateTenantResponse {
  tenant_id: string;
  status: string;
}
