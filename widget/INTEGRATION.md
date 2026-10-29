# cpbot chat widget — integration guide for Credit Plus

This adds a floating cpbot chat icon to your ASP.NET Core site. Users who are
already logged in through ASP.NET Identity are signed into the chat
automatically (SSO) — they never see a cpbot login.

**How it works**

1. Your server signs a short-lived JWT (5 minutes) for the logged-in user, using a secret shared with us.
2. The widget passes that JWT to the cpbot chat window, which verifies it with the cpbot backend.
3. cpbot matches the user by email (creating them on first use) and starts a chat session.

The secret never leaves your server. The browser only ever sees the short-lived JWT.

## What we give you

| Item | Example |
|---|---|
| Tenant slug | `creditplus` |
| Shared JWT secret (HS256, 32+ characters) | sent to you over a secure channel — **never commit it to source control** |
| `cpbot-widget-1.0.0.tgz` | this package |

Store the secret in your normal secret store (user-secrets, environment variable,
Azure Key Vault, `appsettings` outside source control). In the code below it is
read from configuration key `CpBot:SsoSecret`.

## 1. Install the widget

```bash
npm install ./cpbot-widget-1.0.0.tgz
```

The script to serve is `node_modules/cpbot-widget/dist/cpbot-widget.js`. For a
typical ASP.NET Core site, copy it into `wwwroot`:

```bash
mkdir -p wwwroot/lib/cpbot
cp node_modules/cpbot-widget/dist/cpbot-widget.js wwwroot/lib/cpbot/
```

(If you use a JS bundler, `import { init } from 'cpbot-widget'` works too — an
ESM build and TypeScript types are included.)

## 2. Add the script to your layout

Put this in `_Layout.cshtml`, only for signed-in users. The widget asks your
server for a fresh token each time the chat is opened, so it never uses an
expired one:

```html
@if (User.Identity?.IsAuthenticated == true)
{
    <script src="~/lib/cpbot/cpbot-widget.js"
            data-tenant="creditplus"
            data-token-url="/cpbot/token"
            data-position="bottom-right"></script>
}
```

Equivalent JavaScript call:

```html
<script src="~/lib/cpbot/cpbot-widget.js"></script>
<script>
  CpBotWidget.init({
    tenant: 'creditplus',
    tokenUrl: '/cpbot/token',            // or: tokenProvider: async () => (await fetch('/cpbot/token')).text()
    theme: { color: '#2563EB', position: 'bottom-right', offset: 20 },
    lang: 'en'                           // 'ar' for Arabic
  });
</script>
```

Options: `tenant` (required), one of `token` / `tokenUrl` / `tokenProvider`
(required), `theme.color` (defaults to your tenant color), `theme.position`
(`bottom-right` | `bottom-left`), `theme.offset`, `theme.zIndex`, `lang`,
`open` (start opened), `title`. Script-tag equivalents are `data-tenant`,
`data-token`, `data-token-url`, `data-color`, `data-position`, `data-offset`,
`data-lang`, `data-title`, `data-open`.

Do not hard-code a static `data-token` for real use: it expires in minutes.
`data-token-url` / `tokenProvider` is the supported approach.

## 3. Sign the JWT in ASP.NET (C#)

Add the token endpoint (minimal API shown; a controller action works the same).
Install `System.IdentityModel.Tokens.Jwt` if it is not already referenced.

```csharp
using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using Microsoft.AspNetCore.Authorization;
using Microsoft.IdentityModel.Tokens;

// Program.cs
app.MapGet("/cpbot/token", [Authorize] (ClaimsPrincipal user, IConfiguration config) =>
{
    var secret = config["CpBot:SsoSecret"]
        ?? throw new InvalidOperationException("CpBot:SsoSecret is not configured");

    // Use YOUR Identity user's stable id, e-mail and display name.
    var userId = user.FindFirstValue(ClaimTypes.NameIdentifier)!;
    var email  = user.FindFirstValue(ClaimTypes.Email)
                 ?? throw new InvalidOperationException("User has no e-mail");
    var name   = user.FindFirstValue(ClaimTypes.Name) ?? email;

    var now = DateTime.UtcNow;
    var claims = new[]
    {
        new Claim("sub",   userId),
        new Claim("email", email),
        new Claim("name",  name),
        new Claim("iat", EpochTime.GetIntDate(now).ToString(), ClaimValueTypes.Integer64),
    };

    var key   = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(secret));
    var creds = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);

    var jwt = new JwtSecurityToken(
        issuer:  "credit-plus",            // informational
        audience: "cpbot-widget",          // REQUIRED, must be exactly this
        claims:  claims,
        notBefore: now,
        expires: now.AddMinutes(5),        // keep short; max accepted is 60 min
        signingCredentials: creds);

    return Results.Text(new JwtSecurityTokenHandler().WriteToken(jwt));
});
```

Add the secret to configuration (not to source control), e.g.
`dotnet user-secrets set "CpBot:SsoSecret" "<secret from cpbot>"` in development.

### Claims format

| Claim | Required | Meaning |
|---|---|---|
| `sub` | yes | Your stable user id |
| `email` | yes | User's e-mail — cpbot matches/creates the chat user by this |
| `name` | recommended | Display name (falls back to the part of the e-mail before `@`) |
| `aud` | yes | Must be exactly `cpbot-widget` |
| `exp` | yes | Expiry. Expired tokens are rejected |
| `iat` | recommended | Issue time. `exp - iat` may not exceed 60 minutes |
| `iss` | no | Informational |

Algorithm is **HS256**; any other algorithm (including `none`) is rejected. The
secret is used as its UTF-8 bytes on both sides.

Chat users are always created as regular chat members; a claim can never grant
admin rights in cpbot.

## 4. Other things to check on your side

- **Only issue tokens to logged-in users** — keep the endpoint `[Authorize]`d and, if you use antiforgery/CSRF policies, note it is a GET that returns a token only to the same origin.
- **Content-Security-Policy** (if you set one): allow the widget script from your own origin, `frame-src` for the cpbot chat origin, and `connect-src` for the cpbot API origin (we will give you both).
- **HTTPS everywhere.**
- **Secret rotation:** tell us and we can switch secrets with a short overlap; in the meantime do not put the secret in client-side code, logs or repos.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Icon appears but chat shows "Something went wrong" | JWT rejected: wrong secret, wrong `aud`, expired (check server clock), missing `email`/`sub` |
| No icon | Script not loaded (404 on `/lib/cpbot/cpbot-widget.js`), or user not authenticated |
| Chat window blank | Your CSP blocks the `frame-src` for the chat origin |
| `/cpbot/token` returns 401/302 | Endpoint requires an authenticated session — call it from a logged-in page |

Browser console messages are prefixed `[cpbot-widget]`.
