import { TenantBranding } from './tenant.models';

export type UserRole = 'admin' | 'company_admin' | 'member' | 'superadmin';

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthResponse {
  role: UserRole;
  username?: string;
  phone?: string;
  country_code?: string;
  tenant_id: string;
  company_id?: string | null;
  tenant?: TenantBranding | null;
}

export interface UpdateUsernameRequest {
  username: string;
}

export interface UpdateUsernameResponse {
  username: string;
}

export interface JwtPayload {
  tenant_id?: string;
  company_id?: string | null;
  sub?: string;
  email?: string;
  role?: string;
  exp?: number;
  [key: string]: unknown;
}

export interface CurrentUser {
  email: string | null;
  username: string | null;
  phone: string | null;
  countryCode: string | null;
  role: UserRole | null;
  tenantId: string | null;
  companyId: string | null;
}

export interface UpdatePhoneRequest {
  phone: string;
  country_code: string;
}

export interface UpdatePhoneResponse {
  phone: string;
  country_code: string;
}
