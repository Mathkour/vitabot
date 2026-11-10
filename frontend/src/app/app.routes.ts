import { Routes } from '@angular/router';
import { adminGuard } from './core/guards/admin.guard';
import { authGuard } from './core/guards/auth.guard';
import { companyAdminGuard } from './core/guards/company-admin.guard';
import { guestGuard } from './core/guards/guest.guard';
import { housingBankTenantGuard } from './core/guards/housing-bank-tenant.guard';
import { memberGuard } from './core/guards/member.guard';
import { odooAccessGuard } from './core/guards/odoo-access.guard';
import { sharedPageGuard } from './core/guards/shared-page.guard';
import { superadminGuard } from './core/guards/superadmin.guard';
import { uploadLockGuard } from './core/guards/upload-lock.guard';
import { vitaCareTenantGuard } from './core/guards/vita-care-tenant.guard';

export const routes: Routes = [
  {
    path: 'auth',
    canActivate: [guestGuard],
    loadComponent: () =>
      import('./features/auth/auth-page/auth-page').then((m) => m.AuthPage),
  },
  {
    // Public: reached with a token already issued server-to-server by
    // POST /auth/odoo-sso, before the browser has any session of its own —
    // guestGuard would wrongly bounce an already-logged-in browser away
    // before the new token gets applied, so this route carries no guard.
    path: 'sso-login',
    loadComponent: () =>
      import('./features/auth/sso-login/sso-login').then((m) => m.SsoLoginPage),
  },
  {
    // Embedded-widget chat: public, no guard — it authenticates itself from
    // the partner JWT in the URL fragment (see WidgetChat).
    path: 'widget-chat',
    loadComponent: () =>
      import('./features/widget-chat/widget-chat').then((m) => m.WidgetChat),
  },
  {
    path: 'access-denied',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/access-denied/access-denied').then((m) => m.AccessDenied),
  },
  // Must come before the path:'' layout routes below. Those routes match
  // the bare root as a prefix with zero segments remaining, and since none
  // of their children has an empty path, no child ever activates — the
  // layout shell (sidebar) still renders with a permanently empty
  // <router-outlet>, and because the only guards live on the children, no
  // guard ever runs either (sidebar visible, blank content, no network
  // calls at all, no redirect — exact root-path bug). This exact-match
  // redirect intercepts the bare root first so that case never reaches
  // them; any non-empty path falls through to the layout routes as before.
  { path: '', pathMatch: 'full', redirectTo: 'auth' },
  // Admin-only pages, flattened to top-level paths (no /admin/* prefix).
  // The layout shell is still shared via this path:'' parent (it costs no
  // URL segment), but each child carries its own explicit canActivate so
  // the access rule is visible and set per-route rather than inherited.
  {
    path: '',
    loadComponent: () =>
      import('./layout/admin-layout/admin-layout').then((m) => m.AdminLayout),
    children: [
      {
        path: 'knowledge-base',
        canActivate: [adminGuard],
        canDeactivate: [uploadLockGuard],
        loadComponent: () =>
          import('./features/admin/knowledge-base/knowledge-base').then(
            (m) => m.KnowledgeBase,
          ),
      },
      { path: 'categories', redirectTo: 'knowledge-base', pathMatch: 'full' },
      { path: 'documents', redirectTo: 'knowledge-base', pathMatch: 'full' },
      { path: 'media', redirectTo: 'knowledge-base', pathMatch: 'full' },
      {
        // companyAdminGuard, not adminGuard: a company_admin also needs
        // this page (to manage their own company's users) — every other
        // admin route in this file stays on plain adminGuard.
        path: 'users',
        canActivate: [companyAdminGuard],
        loadComponent: () =>
          import('./features/admin/users/users').then((m) => m.Users),
      },
      {
        // Tenant-admin only (companyAdminGuard would wrongly admit a
        // company_admin here — they manage users, not the companies
        // themselves). Gated to Vita Care on the backend
        // (require_vita_care_admin); the sidebar link is hidden for every
        // other tenant, same pattern as vita-insights/document-index.
        path: 'companies',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./features/admin/companies/companies').then((m) => m.Companies),
      },
      {
        path: 'conversations',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./features/admin/conversations/conversations').then((m) => m.Conversations),
      },
      {
        path: 'conversations/:userId',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./features/admin/conversations/conversation-detail/conversation-detail').then(
            (m) => m.ConversationDetail,
          ),
      },
      {
        path: 'admin-assistant',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./features/admin/admin-assistant/admin-assistant').then(
            (m) => m.AdminAssistant,
          ),
      },
      {
        // Admin's FAQ *management* page — distinct component from the
        // member-facing FAQ *viewer* at /faq below, so it can't share that
        // path once flattened.
        path: 'faq-management',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./features/admin/faq/faq').then((m) => m.Faq),
      },
      {
        // Per-tenant insights for this tenant's own admin — distinct from
        // /superadmin/ai-monitoring, which is superadmin-only and aggregates
        // across every tenant (see routers/tenant_analytics.py vs.
        // routers/ai_monitoring.py on the backend).
        path: 'analytics',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./features/admin/analytics/analytics').then((m) => m.Analytics),
      },
      {
        // Questions the bot couldn't answer, for the tenant admin to answer
        // (each answer becomes knowledge the bot uses from then on).
        path: 'unanswered-questions',
        canActivate: [adminGuard],
        loadComponent: () =>
          import('./features/admin/unanswered-questions/unanswered-questions').then(
            (m) => m.UnansweredQuestions,
          ),
      },
      {
        // companyAdminGuard: a company_admin answers only their own
        // company's tickets (enforced on the backend too). Distinct path
        // from /support-tickets below (the member-facing "my tickets" view).
        path: 'support-tickets-admin',
        canActivate: [companyAdminGuard],
        loadComponent: () =>
          import('./features/admin/support-tickets/support-tickets').then(
            (m) => m.AdminSupportTickets,
          ),
      },
      // Settings temporarily hidden — do not delete. Matching sidebar nav
      // item is also commented out in sidebar.ts. Direct navigation to
      // /settings now falls through to the wildcard route below.
      // {
      //   path: 'settings',
      //   canActivate: [adminGuard],
      //   loadComponent: () =>
      //     import('./features/admin/settings/settings').then((m) => m.Settings),
      // },
    ],
  },
  {
    path: 'admin',
    pathMatch: 'full',
    redirectTo: 'knowledge-base',
  },
  {
    path: 'superadmin',
    canActivate: [superadminGuard],
    loadComponent: () =>
      import('./layout/client-layout/client-layout').then((m) => m.ClientLayout),
    children: [
      {
        path: '',
        loadComponent: () =>
          import('./features/superadmin/superadmin-page/superadmin-page').then(
            (m) => m.SuperadminPage,
          ),
      },
      {
        path: 'odoo-chat',
        loadComponent: () =>
          import('./features/superadmin/odoo-chat/odoo-chat').then(
            (m) => m.OdooChat,
          ),
      },
      {
        path: 'ai-monitoring',
        loadComponent: () =>
          import('./features/superadmin/ai-monitoring/ai-monitoring').then(
            (m) => m.AiMonitoring,
          ),
      },
    ],
  },
  // Member-only and cross-role-shared pages, flattened to top-level paths
  // (no /chat/* prefix). Same path:'' layout-sharing trick as the admin
  // group above, with per-route guards. The shell here is RoleLayout, not a
  // fixed layout component — before flattening, an admin reached these
  // pages via /admin/* (AdminLayout, sidebar) and a member via /chat/*
  // (ClientLayout, topbar only); with no prefix left to key off, RoleLayout
  // picks the shell from the visiting user's actual role instead.
  {
    path: '',
    loadComponent: () =>
      import('./layout/role-layout/role-layout').then((m) => m.RoleLayout),
    children: [
      {
        // Shared with the old /admin/chat — same ChatPage component reached
        // by both admins and members, so it gets sharedPageGuard rather
        // than adminGuard or memberGuard (see that guard's doc comment).
        path: 'chat',
        canActivate: [sharedPageGuard],
        loadComponent: () =>
          import('./features/chat/chat-page/chat-page').then((m) => m.ChatPage),
      },
      {
        // Shared with the old /admin/profile.
        path: 'profile',
        canActivate: [sharedPageGuard],
        loadComponent: () =>
          import('./features/profile/profile-page/profile-page').then((m) => m.ProfilePage),
      },
      {
        // Shared with the old /admin/vita-insights ("Ask Odoo"). Only for
        // users the backend allows: company users with their own company's
        // Odoo connection, or Vita Care's own staff — see odooAccessGuard.
        path: 'vita-insights',
        canActivate: [sharedPageGuard, vitaCareTenantGuard, odooAccessGuard],
        loadComponent: () =>
          import('./features/admin/vita-insights/vita-insights').then(
            (m) => m.VitaInsights,
          ),
      },
      {
        // Shared with the old /admin/document-index.
        path: 'document-index',
        canActivate: [sharedPageGuard, housingBankTenantGuard],
        loadComponent: () =>
          import('./features/admin/document-index/document-index').then(
            (m) => m.DocumentIndex,
          ),
      },
      {
        // AI-generated answers built only from the Document Index's own
        // files (never invented) — same tenant gating as document-index.
        path: 'ask-ai',
        canActivate: [sharedPageGuard, housingBankTenantGuard],
        loadComponent: () =>
          import('./features/admin/ask-ai/ask-ai').then((m) => m.AskAi),
      },
      {
        // Member-only FAQ *viewer* — distinct component from the admin FAQ
        // *management* page at /faq-management above.
        path: 'faq',
        canActivate: [memberGuard],
        loadComponent: () =>
          import('./features/faq/faq-page/faq-page').then((m) => m.FaqPage),
      },
      {
        // Member-only video library — Vita Care tenant only (backend-enforced
        // too, via require_vita_care_tenant on GET /videos).
        path: 'videos',
        canActivate: [memberGuard, vitaCareTenantGuard],
        loadComponent: () =>
          import('./features/videos/videos-page/videos-page').then((m) => m.VideosPage),
      },
      {
        // Not in the sidebar/topbar nav — reached only from the bot's
        // "contact support" offer (no-info answers) or a notification link
        // once a ticket is answered. See chat-page.ts's openSupportTicket().
        path: 'support-tickets',
        canActivate: [memberGuard],
        loadComponent: () =>
          import('./features/support-tickets/support-tickets-page/support-tickets-page').then(
            (m) => m.SupportTicketsPage,
          ),
      },
    ],
  },
  { path: '**', redirectTo: 'auth' },
];
