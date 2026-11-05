# Security and local data

Nightshift is a local desktop application. It has no telemetry endpoint, hosted backend, or shared credentials. It contacts selected service APIs only for enabled integrations or user-initiated setup; the browser opens user-selected links. System monitoring reads local `/proc`/filesystem counters.

Treat these directories as private:

- `~/.config/nightshift-home/`: settings, notes/tasks, layout profiles, OAuth data, focus/music state, theme undo snapshots.
- `~/.cache/nightshift-home/`: integration response caches.
- `~/.local/share/nightshift-home/photos/`: explicitly selected photo downloads.
- `~/.local/state/nightshift-desktop/`: installation journal, which can contain backups of pre-existing files/settings.

Credential and personal-store writers use restrictive file permissions. Local permissions do not protect against another process running as your own user. OAuth browser handoffs use loopback callbacks and PKCE. The Cloudflare client restricts endpoints to its expected service and requests read-oriented scopes. No browser cookies are imported.

The repository includes only code, theme assets, placeholder configuration, and synthetic screenshots. `.gitignore` is a guardrail, not a substitute for reviewing a commit. Do not copy a live app/config directory into a pull request.

For a vulnerability, use GitHub’s private vulnerability reporting on this repository if available. If unavailable, open an issue requesting a private contact without posting credentials, private user data, or exploit details. Supported releases are currently the latest `main` snapshot; this is an early public release, not a hardened credential manager.
