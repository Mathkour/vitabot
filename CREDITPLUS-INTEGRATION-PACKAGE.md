# Credit Plus — cpbot Chat Widget Integration

## Overview

This is an embeddable chat widget with single sign-on (SSO). It adds a floating chat icon to your site; when a user clicks it, a chat window opens and the user is signed in automatically — no separate cpbot login. On your side there are two things to do:

1. **Add a script tag** to your pages (Step 1).
2. **Sign a short-lived JWT** for the logged-in user (Step 2).

---

## Step 1: Install the widget

Install the attached package:

```bash
npm install ./cpbot-widget-1.0.0.tgz
```

Copy the script into your static files so your site can serve it:

```bash
mkdir -p wwwroot/lib/cpbot
cp node_modules/cpbot-widget/dist/cpbot-widget.js wwwroot/lib/cpbot/
```

Add this to your layout (`_Layout.cshtml`), for signed-in users only:

```html
@if (User.Identity?.IsAuthenticated == true)
{
    <script src="~/lib/cpbot/cpbot-widget.js"
            data-tenant="<TENANT>"
            data-api-url="<API_URL>"
            data-chat-url="<CHAT_URL>"
            data-token-url="/cpbot/token"></script>
}
```

Or, equivalently, in JavaScript:

```html
<script src="~/lib/cpbot/cpbot-widget.js"></script>
<script>
  CpBotWidget.init({
    tenant: '<TENANT>',
    apiUrl: '<API_URL>',
    chatUrl: '<CHAT_URL>',
    tokenUrl: '/cpbot/token',
    theme: { color: '#2563EB', position: 'bottom-right' },  // optional
    lang: 'en'                                               // optional: 'en' | 'ar'
  });
</script>
```

Values to use for the placeholders:

| Placeholder | Value |
|---|---|
| `<TENANT>` | `creditplus` |
| `<API_URL>` | `https://cpbot-staging.onrender.com` |
| `<CHAT_URL>` | `https://cpbot-frontend.onrender.com/widget-chat` |

`data-token-url` points to the endpoint from Step 2. The widget calls it each time the chat is opened, so it always sends a fresh token. Do not hard-code a static token — it expires in minutes.

---

## Step 2: Generate the SSO token (ASP.NET)

Add the `/cpbot/token` endpoint (requires the `System.IdentityModel.Tokens.Jwt` package). Keep it `[Authorize]`d so only logged-in users get a token.

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
        issuer:  "credit-plus",
        audience: "cpbot-widget",          // must be exactly this
        claims:  claims,
        notBefore: now,
        expires: now.AddMinutes(5),
        signingCredentials: creds);

    return Results.Text(new JwtSecurityTokenHandler().WriteToken(jwt));
});
```

Store the secret in your secret store (e.g. `dotnet user-secrets set "CpBot:SsoSecret" "<secret>"` in development), never in source code.

### Required claims

| Claim | Type | Example | Required? |
|---|---|---|---|
| `sub` | string | `"a1b2c3-user-id"` | **Required** — your stable user id |
| `email` | string | `"ali@example.com"` | **Required** — used to match or create the chat user |
| `aud` | string | `"cpbot-widget"` | **Required** — must be exactly this value |
| `exp` | number (Unix seconds) | `1790423056` | **Required** — expired tokens are rejected |
| `name` | string | `"Ali Ahmad"` | Optional (recommended) — display name; defaults to the part of the e-mail before `@` |
| `iat` | number (Unix seconds) | `1790422756` | Optional (recommended) — `exp − iat` may not exceed 60 minutes |
| `iss` | string | `"credit-plus"` | Optional — informational only |

- **Algorithm:** HS256 only. Any other algorithm is rejected.
- **Expiry:** use **5 minutes** (`exp = now + 5 min`), as in the tested setup. The token only needs to survive the trip from your server to the chat window.
- Chat users are always created as regular members; nothing in the token can grant admin rights.

---

## The shared secret

The signing secret will be shared separately over **[means TBD]**. Do not commit it to source control or share it over email/Slack.

---

## Allowed domains

`https://credit-plus.me` and `https://www.credit-plus.me` are the **only** origins the widget accepts embedding from and the backend accepts widget requests from (HTTPS only). If you need another subdomain added, tell us **before going live**.

---

## What was tested

The full flow was tested end-to-end against our real staging environment (staging backend and staging chat frontend, not just locally): widget icon load with the tenant's branding, SSO verification, a live chat message with a real bot reply, and rejection of a tampered/invalid token. The test tokens were signed by our own test script, so the C# snippet above has not yet been run on your side — please verify it once in your dev environment.

---

## Support contact

For integration issues, contact: [your contact info]
