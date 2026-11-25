# trend-scout

A local, read-only trend engine for Claude Code: think "my own Apify", running on a Mac with no platform fees. It finds what's taking off in a niche and why, with the numbers attached:

- **Reddit**: the week's top posts per niche, ranked by velocity `(comments×2 + score) / hours^1.5`, plus comment *intent* (the share of comments asking how/where/which or tagging a friend).
- **YouTube**: recent videos whose views beat their channel's size (views ÷ subscribers ≥ 3), with views per hour.
- **Instagram**: top and recent posts per hashtag, and creator-account outliers (official Graph API).
- **TikTok**: the public Creative Center trending lists (no login).
- **Hooks**: the first ~3 seconds of speech in a video. YouTube uses captions; anything else uses Whisper on device (mlx-whisper).
- **Memory**: SQLite remembers everything it has shown, so a brief never repeats a post.

Everything is read-only: nothing posts, follows, likes or messages. It uses no burner accounts, stealth browsers or proxies; where a platform says no, the tool says so.

## Run
```bash
uv sync
uv run playwright install chromium   # only for TikTok
uv run pytest
claude mcp add trend-scout -- uv --directory "$PWD" run trend-scout
```
Niches (subreddits, YouTube search phrases, Instagram hashtags) live in `niches.toml`.

## Keys (macOS Keychain, service `enterprise-os`; never in files)
Store each one with:
```bash
security add-generic-password -U -s enterprise-os -a NAME -w
```
It asks for the value, so it never lands in your shell history.

| NAME | Where to get it |
|---|---|
| `YOUTUBE_API_KEY` | console.cloud.google.com → new project → APIs & Services → Library → "YouTube Data API v3" → Enable → Credentials → Create credentials → API key (restrict it to YouTube Data API v3). Free: 10,000 units a day; one search costs 100. |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | reddit.com/prefs/apps → "create another app" → type **script**, redirect `http://localhost:8080` → the id under the app name and the secret. Reddit refuses keyless reads. |
| `IG_ACCESS_TOKEN`, `IG_USER_ID` | See Instagram setup below. |

## Instagram setup (about 20 minutes, once)
1. In the Instagram app: make the account Professional (Creator or Business) and link it to a Facebook Page.
2. developers.facebook.com → My Apps → Create app → "Other" → **Business**. Add the **Instagram Graph API** product. Dev mode is fine, since it's only your own account.
3. Graph API Explorer: pick the app, get a User token with `instagram_basic`, `pages_show_list`, `pages_read_engagement`, `business_management`. Exchange it for a long-lived token (Access Token Debugger → "Extend Access Token", about 60 days) and save it as `IG_ACCESS_TOKEN`.
4. In the Explorer: `GET me/accounts?fields=instagram_business_account` gives the Instagram id; save it as `IG_USER_ID`.
5. Refresh the token before it expires. Tool results warn 7 days ahead.

Limits: 30 different hashtags per rolling 7 days (tracked locally; a 31st tag is refused before it's sent). Creator lookups only see business and creator accounts.

## Known limits
- TikTok's Creative Center serves a blank page to headless browsers, so `tiktok_trending` usually reports "blocked". We don't work around that. Read it by hand in a normal browser instead.
- No TikTok keyword search with engagement numbers: TikTok only offers that through its academic Research API.
