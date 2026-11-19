# Setup problems and fixes

`bash scripts/setup.sh` is safe to run again any time: it skips what is already done. It needs no password.

| What happens | Fix |
|---|---|
| `NOT READY: missing uv` / uv won't install | Check the internet; on a work computer a firewall may block it. Run setup again on home Wi-Fi. |
| ffmpeg download fails | Run setup again (it tries a second server). If it keeps failing on a Mac with Homebrew: `brew install ffmpeg` and run setup again (it uses an ffmpeg that is already there). |
| The speech model download stops | Run setup again: it picks up where it stopped. It is about 1.6 GB. |
| Windows: "bash is not recognized" | The Claude app's Code tab needs Git for Windows (git-scm.com). Install it with the normal choices, restart Claude. |
| `DOWNLOAD_FAILED` on a stream | The recording may be subscriber-only, deleted, or still processing. Try another stream, or ask the user to download that part themselves and use `--src <file>`. For a YouTube video that needs a login, ask the user if you may use their browser's login: then set `"cookies_from": "chrome"` (or `"safari"`, `"firefox"`, `"edge"`) in `~/.stream-clipper/config.json`. |
| `find.py` finds no chat on Kick | Kick sometimes blocks automated requests for a few minutes. Wait and run it again. |
| YouTube download errors | Update the downloader: `$PY -m pip install -U yt-dlp` (or `uv pip install -U yt-dlp --python $PY`). |
| Render stops part-way | Usually a full disk. Check free space, offer to move old clip folders to the Trash, render again. |
| Captions out of sync | Re-run `clip.py prep` on the clip (it re-listens). |

To uninstall: delete `~/.stream-clipper` (the tools) and, if the user wants, `~/Stream Clips` (their clips), then the
skill folder in `~/.claude/skills/gta6-clipper`. Ask first; use the Trash.

## Running in a Claude Code cloud session

- The cloud environment needs network access to Twitch's video servers (`*.ttvnw.net`, plus several
  `*.cloudfront.net` hosts) and Hugging Face's model servers. A wildcard can't be added with an approval card,
  so either add `*.ttvnw.net` under the environment's Allowed domains in Settings or set network access to
  unrestricted.
- Live mode reads Twitch chat over its web chat connection when a proxy is set, and `sc.py` points ffmpeg at the
  proxy. Without those changes it can't reach chat or video.
- An anonymous viewer gets Twitch ad breaks. Check each live moment's contact sheet and skip any that are just
  "Commercial break in progress".
