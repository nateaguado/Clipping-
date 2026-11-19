# Posting

## The title hook (on the clip)

Use `HOOKS.md`: the most extreme TRUE version of what happens, a person first, one question planted and never
answered, 6 to 12 words, ending in "..." or one emoji. A plain label ("Kai plays GTA 6") gets no views; a lie gets
"clickbait" comments. Launch week: never spoil the story in the hook.

## The post caption

- First line: a searchable sentence with the streamer's name and the game or topic. People search "kai cenat gta"
  and the caption keeps earning views for weeks. Not "lol crazy clip".
- Optional second line: a question that invites comments ("Was the 45 a real order? 😭").
- 3 to 5 hashtags: the streamer (#kaicenat), the game (#gta6 #gtavi or #gtasanandreas), the type (#streamerclips,
  #twitchclips or #kickclips), and one broad tag (#gaming). Check the campaign's required tags.
- A different caption on each platform and each upload, so identical reposts aren't flagged.
- Credit the streamer if the campaign asks (it usually does) and it is good manners anyway.

## Posting through Blotato (only after `BLOTATO-SETUP.md` is done)

1. `blotato_list_accounts` for the account ids (saved in `channels/me.md`).
2. Upload: `blotato_create_presigned_upload_url` with the file name, then
   `curl -X PUT "<presignedUrl>" --data-binary "@<finished.mp4>"`, and use the `publicUrl` it gave.
3. Show the summary for every post (page, platform, clip, caption, time) and **wait for a clear yes**.
4. `blotato_create_post` once per platform, each with its own caption:
   - Instagram: `platform: "instagram"`, `mediaType: "reel"`, `shareToFeed: true`.
   - TikTok: `platform: "tiktok"`, `privacyLevel: "PUBLIC_TO_EVERYONE"`, `disabledComments: false`,
     `disabledDuet: false`, `disabledStitch: false`, `isAiGenerated: false`, `isBrandedContent` and `isYourBrand`
     `false` (a paid campaign clip may need `isBrandedContent: true`: follow the campaign's rules). Ask once if they
     want different switches; save in `me.md`.
   - YouTube: `platform: "youtube"`, a `title` (under 100 characters, with "GTA 6" and the streamer),
     `privacyStatus: "public"`, `shouldNotifySubscribers: true`.
   - Leave out `scheduledTime` to post now, or set it (ISO time, their time zone, asked once) to schedule.
   Blotato's tool descriptions list each platform's required fields: read them, don't guess.
5. `blotato_get_post_status` until it's live, give them each post's link, and remind them to submit it to the
   campaign (`WHOP.md`).

Clips posted this way can't use the apps' in-app songs. If a campaign requires a song, they post that clip by hand
from the app (you still write the caption).

## Rhythm

- Fresh moments: post as soon as the clip is ready. During launch weeks and big streams, aim for within 1 to 3 hours
  of the moment (vendors and experienced clippers agree speed wins; there is no independent study).
- Otherwise: 1 to 3 clips a day, every day, same page on TikTok, Shorts and Reels. US evenings (6 to 10 pm Eastern)
  help early momentum.
- Campaign clips: submit each link the moment it is live; stop posting to a campaign when its budget is almost spent.

## The log (`~/Stream Clips/channels/<channel>.md`)

```markdown
| Date | Streamer | Moment | Hook | Platforms | Views 24 h | Views 7 d | Notes |
|---|---|---|---|---|---|---|---|
| 2026-11-15 | Kai Cenat | Big Smoke order at drive-thru (VOD 2922436506 26:30:05) | Kai ordered Big Smoke's meal at a real drive-thru | TT, YT, IG | | | |
```

Every few days ask the user for the views and fill them in. Then say what worked (which streamer, moment type, hook
pattern, length) and pick the next moments with that in mind.
