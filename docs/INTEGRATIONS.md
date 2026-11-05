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

## AI Learning

Enable the panel to check these official sources every **5 minutes**:

| Publisher | Source |
| --- | --- |
| OpenAI | [News RSS](https://openai.com/news/rss.xml) |
| Anthropic / Claude | [Engineering index](https://www.anthropic.com/engineering) |
| n8n | [Blog RSS](https://blog.n8n.io/rss/) |
| Google AI | [AI blog RSS](https://blog.google/innovation-and-ai/technology/ai/rss/) |
| Google Developers | [Developer blog index](https://developers.googleblog.com/) |
| Google Research | [Research RSS](https://research.google/blog/rss/) |
| Hugging Face | [Blog feed](https://huggingface.co/blog/feed.xml) |
| Cloudflare | [AI blog RSS](https://blog.cloudflare.com/tag/ai/rss/) |
| NVIDIA | [Developer blog feed](https://developer.nvidia.com/blog/feed/) |

It selects recent AI articles with practical topics such as caching, inference, quantization, latency, agents, retrieval, and evaluation. Anthropic’s source is its official HTML engineering index; Google Developers uses the dated latest articles on its official home page because its RSS omits dates. Both are read directly, without an unofficial feed service. Anthropic engineering cards without a topic match appear under Build. Results are sorted by publication date and limited to the last 90 days; adding a source does not make its older articles appear newly published. Cost, Latency, and Build filters help narrow the feed.

Descriptions are publisher excerpts. Suggested **Try** actions are small experiments inferred from the topic; measure their effect on your own workload. Reference documentation remains available with a **Guide** label. The footer reports refresh state; its tooltip lists each source’s last check or error. Failed sources keep their previous cache, while successful sources update independently. Conditional requests reduce repeated downloads when supported by the publisher.

The search bar filters this resource collection locally. **Web** explicitly opens an AI-focused Google search in your browser. Search text is not sent to a model or stored in the feed cache. This feature needs no AI API key.

**To-do** adds an actionable experiment and a source link. Find that link under **Open learning source** in the task’s actions menu. **Notes** appends the takeaway, suggested experiment, date/source, and URL to your current text, including unsaved typing. Existing task edits are retained. Both buttons remain enabled after saving. A duplicate click reports “Already in” without creating another copy; after removing the resource from Notes or deleting its task, you can save it again.
