# Connect your own services

All credentials belong in your home directory, never this repository. Enable each panel through Nightshift Home settings after setup. Third-party APIs and authorization policies can change; an integration can fail independently of the local desktop.

## Cloudflare

1. Copy the example to the app’s configuration directory:

   ```sh
   mkdir -p ~/.config/nightshift-home
   cp examples/sites.json ~/.config/nightshift-home/sites.json
   chmod 600 ~/.config/nightshift-home/sites.json
   ```

2. Edit `account_id` to your Cloudflare account ID and `hosts` to one–four lowercase bare hostnames that belong to that account. The example domains and zero ID are placeholders. Do not enter URLs, wildcards, or ports. Zone IDs are not required by this account-host query.
3. Restart Nightshift, enable **Cloudflare site insights**, and use its connection button. Complete consent in your browser. This uses a separate PKCE/loopback OAuth client for Cloudflare’s official MCP endpoint; existing Codex/MCP credentials are not imported.
4. If a link expires, start a new connection rather than reusing it. The connection window lets you reopen, retry, and cancel. API access still depends on the selected account, its permissions, and Cloudflare’s available analytics datasets.

The widget polls every **5 minutes** for a rolling **24-hour** window. Trends use **15-minute buckets**. These are HTTP request counts, including automated traffic, not unique human visitors. The primary host is displayed separately from its `www` host, which appears in details. Compare the same account, host, period, and filters in Cloudflare before comparing totals. Adaptive sampling and reporting delay can affect values. An update failure preserves the cache and displays its age; it does not fabricate current totals.

The small health indicator is a separate HTTPS request from your computer every **2 minutes**. It is not a global uptime monitor. No checks are made against bundled personal domains.

Token file: `~/.config/nightshift-home/cloudflare-oauth.json`, mode 0600. Requested scopes: `offline_access user:read account:read analytics.read`. Upstream reference: [Cloudflare MCP servers](https://developers.cloudflare.com/agents/model-context-protocol/cloudflare/servers-for-cloudflare/).

## Google / Gmail

Install/use GNOME Online Accounts, open Settings → Online Accounts, add your own Google account, and enable Mail if offered by your distribution/account. Complete the browser handoff back to GNOME. Then enable the Gmail panel in Home settings. If no account is saved, Nightshift cannot use a browser login as a substitute.

Gmail access is read-only inbox headers through GOA and IMAP. Message bodies are not fetched and messages are not marked read. Headers stay in memory. Checks occur approximately once a minute while enabled. Google/organization policy and GOA version may prevent Mail access.

The Gmail shortcut opens Gmail in your browser. The native inbox detail view is also available with `nightshift-home --detail gmail` when the Gmail widget is enabled.

## Google Photos

This integration rotates **photos you explicitly select**, not your entire library or a continuously synchronized feed. Use `nightshift-home --photos` to open setup.

Create your own Google Cloud desktop OAuth client with the Google Photos Picker API enabled. Follow Google’s [Picker configuration guide](https://developers.google.com/photos/picker/guides/get-started-picker), including consent/test-user setup where required. Import the downloaded desktop client JSON in Nightshift, sign in, and choose photos in Google’s picker. Nightshift requests `photospicker.mediaitems.readonly` and caches selected image files locally for rotation every 30 seconds.

The OAuth client file is stored at `~/.config/nightshift-home/google-photos-client.json`; selected images are stored under `~/.local/share/nightshift-home/photos/`. No Google OAuth client is bundled. Selecting new photos requires another explicit picker session.

## GitHub

Install the GitHub CLI, run `gh auth login`, set your own username in Home settings, and enable GitHub activity. The calendar uses GitHub’s contribution API and updates every 30 minutes. Streaks use UTC dates; an unfinished day with zero activity preserves yesterday’s streak.

Nightshift does not copy your GitHub CLI token into its own configuration. GitHub availability, token permissions, and private-contribution visibility determine the returned data.

## Codex and Handy

Install these applications independently. Codex sessions are read from the local state database in read-only mode. Enabling session titles makes their names visible in the detail view; they remain hidden by default. The schema is not a public compatibility guarantee, so future application updates may require adapter changes. Resume uses the installed `codex` executable in a terminal and does not supply approval-bypass flags.

Handy uses its installed desktop entry/executable. Nightshift does not install speech models, change voice-typing shortcuts, or control physical keyboard RGB lighting.

## YouTube Music

Open YouTube Music in a browser that exposes MPRIS media controls. Start playback, then use the widget’s player chooser if automatic selection is ambiguous. Previous/next and seek are enabled only when the selected player reports those capabilities. The saved last track is a local convenience, not a streaming API or a replacement for the browser.

## AI pulse

Enable the panel to fetch public Hugging Face blog posts and recent AI repositories from GitHub every **15 minutes**. The Tools tab is a recent-repository query sorted by stars, not GitHub’s official Trending page. Learn is a curated list rather than a live feed. Rate limits/offline errors show the saved data and its timestamp.
