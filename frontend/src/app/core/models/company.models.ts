export interface Company {
  id: string;
  name: string;
  /** Odoo SSO matches the Odoo host's subdomain to this (e.g. hawa-wa-adam). */
  slug: string;
  /** Other subdomains that also sign into this company (e.g. almisk for misk). */
  sso_aliases: string[];
  created_at: string;
  user_count: number;
  ask_odoo_enabled: boolean;
  odoo_configured: boolean;
}

export interface CompanyRequest {
  name: string;
}

/** A company's Ask Odoo setup. The password is write-only: never returned. */
export interface CompanyOdooSettings {
  enabled: boolean;
  configured: boolean;
  url: string;
  db: string;
  username: string;
  has_password: boolean;
  client_key: string | null;
}

export interface CompanyOdooRequest {
  enabled: boolean;
  url: string;
  db: string;
  username: string;
  /** Empty = keep the saved password. */
  password: string | null;
}

export interface OdooTestResult {
  ok: boolean;
  error: string | null;
}
