# Microsoft Sign-in (Entra ID, MFA)

Vagt can sign users in through Microsoft Entra ID, the same set-up as
Harbinger and Chronicle. Microsoft then handles authentication, so **MFA,
Conditional Access and a disabled Entra account apply to Vagt too**.

With `VAGT_SSO_ENABLED=1`, **the login page is Microsoft only**: no
username and password form, and a posted password is refused unchecked.
The one password login left is Django admin's own (`/admin/login/`), for
local administrator accounts (see *Admin pages* below).

It is **off by default**. Nothing changes until `VAGT_SSO_ENABLED=1`.

Code: `apps/accounts/`. The adapters decide who gets in, `views.py` makes
the login page Microsoft-only, `access.py` and `admin_site.py` keep SSO
sessions out of the admin pages, and the backends limit the admin login
to break-glass accounts under `VAGT_SSO_ONLY`.

---

## Who gets in

These checks run at every Microsoft login:

- Only accounts in **your tenant** get in. The tenant GUID is pinned, and
  `common`, `organizations` or a domain name stop Vagt at start-up.
- **Guest accounts** (`#EXT#` in the UPN) are refused, unless
  `VAGT_SSO_ALLOW_GUESTS=1`.
- The address must be in `VAGT_SSO_ALLOWED_DOMAINS` (default `fynbus.dk`).
- With `VAGT_SSO_REQUIRED_GROUPS` set, only **members of those Entra
  groups** get in. Vagt asks Microsoft Graph (`/me/checkMemberGroups`) at
  each login. If Graph can't answer, the login is refused (fail closed).
  Removing someone from the group locks them out at their next login.
- The Microsoft account is tied to a Vagt user by its **Entra object id**.
  On a user's first Microsoft login, that link is made once by e-mail
  address. **Set each user's work e-mail in Admin first.** After that,
  only the object id counts.
- A Microsoft account without a Vagt user is refused, unless
  `VAGT_SSO_AUTO_CREATE_USERS=1`. With it on, Vagt creates a plain user
  that is neither staff nor superuser. Every user can change controller
  statuses, so turn auto-creation on only together with the group check.

### Admin pages: local accounts only

A session started by **Microsoft sign-in never reaches the admin pages**,
even when its user is a superuser: Django admin (`/admin/`) and the
superuser-only pages in the app (*Dokumentation*). The *Admin* and
*Dokumentation* links are hidden for such a session, and `/admin/` shows
Django's "not authorised" page. Board, log, controllers and the profile
page work as before.

Administration is done with a **local account** signed in with a password
at **`/admin/login/`** (Django admin's own login page; Vagt's login page
takes no passwords while SSO is on). With `VAGT_SSO_ONLY=1` only the
accounts in `VAGT_SSO_BREAK_GLASS_USERS` may sign in there. Such a login has
no MFA, so give these accounts long random passwords kept in the password
vault, and keep the list short. The same accounts are the way in when
Microsoft sign-in is down: sign in at `/admin/login/`, then open the board
at `/`.

Admin → Users has an **SSO** column (✓ Linked / — / Break-glass) and a
*Microsoft sign-in* filter.

API personal access tokens are not affected. They authenticate on their
own, without MFA, so issue them sparingly and with an expiry.

---

## Entra set-up (once)

1. **App registration** "Vagt SSO", single tenant.
   - Redirect URI (platform *Web*):
     `https://<your Vagt host>/allauth/microsoft/login/callback/`
     (with the trailing slash).
   - API permissions: Microsoft Graph, delegated `User.Read` (the default).
   - Create a **client secret** and note when it expires.
2. **Enterprise application** of the same name → *Properties*:
   *Assignment required* = **Yes**. Under *Users and groups*, assign the
   group of people who may use Vagt, and no single users.
3. Note the **tenant id**, the **client id** and the group's **object id**.

---

## Settings

Put these in an env file on the host and load it into the container with
`env_file:` in the compose service (the `docker-compose.yml` in this repo
has none; add it there, or use the production stack's env file). The
client secret never goes into the compose file or into a repository.

| Variable | Value |
|----------|-------|
| `VAGT_SSO_ENABLED` | `1` |
| `VAGT_SSO_TENANT_ID` | Tenant GUID |
| `VAGT_SSO_CLIENT_ID` | The app registration's client id |
| `VAGT_SSO_CLIENT_SECRET` | Its client secret |
| `VAGT_SSO_REQUIRED_GROUPS` | Group object id(s), comma-separated (max 20) |
| `VAGT_SSO_ONLY` | `1`: only break-glass accounts may use a password (at `/admin/login/`) |
| `VAGT_SSO_BREAK_GLASS_USERS` | Usernames that may still use a password, e.g. `admin` |
| `VAGT_SSO_AUTO_CREATE_USERS` | `0` (default) |
| `VAGT_SSO_ALLOWED_DOMAINS` | Default `fynbus.dk` |
| `VAGT_SSO_ALLOW_GUESTS` | `0` (default) |
| `VAGT_SESSION_MAX_HOURS` | Default `336` (two weeks). `12` makes a lock-out in Entra take effect by the next day. |

The container needs outbound HTTPS to `login.microsoftonline.com` and
`graph.microsoft.com`.

`manage.py check` warns when `VAGT_SSO_ONLY` has no break-glass account
(`accounts.W001`), and when SSO is on without a required group
(`accounts.W002`).

---

## Rollout

1. Create a local administrator account for break-glass use (long random
   password, in the vault) and set every user's work e-mail in Admin.
   Make sure everyone who uses Vagt is in the Entra group.
2. Set `VAGT_SSO_ENABLED=1`, the group, `VAGT_SSO_ONLY=1` and
   `VAGT_SSO_BREAK_GLASS_USERS`, then recreate the container. The login
   page now shows only **Log ind med Microsoft**. Each user is linked by
   e-mail on their first Microsoft login (Admin → Users: ✓ Linked).
   Passwords work only for the break-glass accounts, at `/admin/login/`.
   The profile page no longer offers a password change.

The upgrade itself keeps everyone signed in: a migration moves existing
sessions to Vagt's password backend.

To roll back, turn SSO off with
`VAGT_SSO_ENABLED=0`. Then recreate the container. Users keep their
passwords and their Microsoft links.
