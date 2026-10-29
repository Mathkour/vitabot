export interface CpBotWidgetTheme {
  /** Launcher icon / header color, e.g. "#2563EB". Defaults to the tenant's color from the backend. */
  color?: string;
  position?: 'bottom-right' | 'bottom-left';
  /** Distance from the viewport edge in px (default 20). */
  offset?: number;
  zIndex?: number;
}

export interface CpBotWidgetOptions {
  /** Tenant slug agreed with cpbot, e.g. "creditplus". */
  tenant: string;
  /** Short-lived SSO JWT signed by your backend. */
  token?: string;
  /** Called on every chat open to mint a fresh SSO JWT (preferred over a static token). */
  tokenProvider?: () => string | Promise<string>;
  /** Same-origin URL returning the JWT as text or {"token": "..."}; fetched on every chat open. */
  tokenUrl?: string;
  theme?: CpBotWidgetTheme;
  lang?: 'en' | 'ar';
  /** Accessible title for the launcher (defaults to the bot name). */
  title?: string;
  /** Open the chat panel immediately. */
  open?: boolean;
  /** cpbot backend base URL (override only if told to). */
  apiUrl?: string;
  /** cpbot chat route URL (override only if told to). */
  chatUrl?: string;
}

export function init(options: CpBotWidgetOptions): void;
export function open(): void;
export function close(): void;
export function toggle(): void;
export function destroy(): void;
