# Editing styles that go viral on clip pages

Measured in Nov 2026 from the most-viewed streamer clip Shorts (frames studied one by one), not from caption-app
blogs. What the 1M to 15M view clips have in common:

- **Few words, big.** One or two words on screen at a time, huge, in a heavy font. Never a subtitle line.
- **A thick black outline**, plus a hard shadow or a dark glow, so the words read on any game or room.
- **Key words in colour.** Yellow or green on the important or shouted words, white on the rest.
- **`*SOUND*` tags.** When something happens without words, the caption says it: `*FALLS*`, `*AURA*`, `*LANDS*`,
  `*CRASH*`, `*DOOR SLAMS*`.
- **The caption sits on the seam** between the facecam and the gameplay (stack layout), or low-middle on IRL.
- **A short, true title** at the top; the biggest pages write it in white bold italic with one emoji at the end.
- **The picture moves on big moments:** a quick punch-in on the face when the streamer screams, a shake on an
  impact, sometimes a deep boom under it.

## The caption looks (`"captions"` in clip.json)

| Look | What it is | Seen on | Use it for |
|---|---|---|---|
| `comic` (default) | The MrBeast-style comic caption: 1 to 2 slanted words, thick outline, hard shadow, key words yellow and green. | Jynxzi clips (15M views), MrBeast | Almost anything; the safest choice. Gaming, funny moments. |
| `punch` | ONE big condensed word at a time, white with a dark glow, loud words yellow. | Kai Cenat Live (10M), Live Speedy (782K) | Fast talkers, IRL, hype moments. Feels the most "streamer clip". |
| `speedy` | 2 to 3 heavy italic condensed words, key words yellow and green. | SpeedUniverse (9.1M) | IRL and travel streams, reactions, longer sentences. |
| `porter` | Tall condensed slanted capitals (Bebas-style), 2 to 3 words, no outline, soft shadow; the WHOLE phrase turns yellow, green or red when it holds a key word (set with `colors`: green for names and good things, red for bad or shocking, yellow for emphasis). | Michael Porter Jr. podcast clips | IRL, podcasts, drama, storytime. Very clean. |
| `hormozi` | Montserrat Black capitals, 3 words, the word being said turns yellow, thick outline + hard shadow. | Alex Hormozi | Reactions, talking, advice. |
| `classic` | Montserrat Black, 3 words, the word being said turns yellow. | The Hormozi look | Talking, advice, podcasts, drama explainers. |
| `bold` | Luckiest Guy, 2 words, green word being said. | | Kids' games, Minecraft, Roblox. |
| `story` | Inter Bold lowercase, 3 words, white with a soft shadow, no outline. Colour another person's lines or the punchline yellow with `colors`. Pair with the `plate` hook. | Big IG story edits (e.g. the "I met Shaq" reel) | Story clips joined from several moments, IRL, family, deliveries, podcasts. |
| `clean` | TikTok Sans, sentence case, soft shadow, 5 words, no animation. | | Serious or sad moments, news. |

Pick one look per channel and keep it: a page that looks the same every time gets recognised in the feed.

## Make each clip feel edited (all in clip.json)

- **Key words** are picked automatically: shouted words, numbers and names. Override with
  `"colors": {"w12": "yellow", "w30": "green", "w40-42": "red"}` (colours: yellow, green, red, blue, orange, pink,
  purple, white, or `#RRGGBB`). Two or three coloured words per sentence is plenty.
- **Sound tags:** `"tags": [{"at": "w23", "text": "CRASH"}]` shows `*CRASH*` in the caption spot for about a second
  (`"for": 1.5` to hold longer). Add one wherever the clip has a big action without words: a fall, a crash, a scream,
  a slam, a goal, *AURA* for a cool walk-in. 1 to 4 per clip.
- **Emoji:** `"emoji": [{"at": "w10", "e": "😭"}]` pops an emoji beside the caption. Use 1 to 3, on the laugh or the
  shock. 😭 💀 😂 🔥 😳 🤯 😱 are the ones clip pages use most.
- **Punch-ins:** on by default. The loudest moments (screams, crashes) get a quick zoom on the face, the very loudest
  with a shake and a deep boom. Add your own: `"punch": [{"at": "w40", "zoom": 1.3, "for": 1, "shake": true,
  "flash": false, "sound": "boom"}]`. Turn the automatic ones off with `"auto_punch": false`, or all effects with
  `"effects": false`.
- **Sounds:** built in (made from scratch, free to use): `boom`, `whoosh`, `pop`, `ding`, `riser`.
  `"sounds": [{"at": "w5", "sound": "whoosh", "volume": 0.4}]`. A user's own sound effects go in
  `~/Stream Clips/sounds/` (use the file name without the ending, like `"sound": "vine-boom"`). Less is more: a
  sound on every cut gets annoying.
- **Picture cards:** `"stickers": [{"at": "w43", "src": 2.6, "box": [640, 0, 660, 660], "w": 440, "x": 260, "y": 250, "tilt": -6}]`
  pops a white-bordered photo cut from the footage (`src` = second in `source.mp4`, `box` = the part to cut) on the word
  that names it: the person being talked about, the car, the prize. Keep it off faces.
- **Hide the original's text:** `"blur": [{"from": 0, "until": 3.7, "box": [0, 790, 1080, 290]}]` (box in the
  finished 1080x1920 picture) over burned-in subtitles or a logo.
- **Title style:** `"hook": {"text": "...", "style": "plate", "size": 40, "y": 1400, "until": 5.5}` is the story-page
  plate (black capitals on a white box under the captions). Write it with `references/HOOKS.md`.

  For gaming clips: `"hook": {"text": "Kai wasn't ready for this 😭", "style": "outline"}` is the big-page look (white
  bold italic, emoji at the end). `white` (white box) suits talking clips.

## Copy a creator's own reference look

When the user pastes a clip whose look they love (any TikTok, Short, Reel, or a file):

1. `$PY scripts/clip.py ref "<look name>" --src "<link or file>"`. This writes, in `~/Stream Clips/styles/<look name>/`:
   `sheet.jpg` (a frame every half second of the first 20 s, timestamped), `frames/` (each frame larger) and
   `fonts.jpg` (every font, numbered, with the same sample words).
2. Open `sheet.jpg` and a few frames where the caption shows. Note: words per caption, upper or sentence case, the
   font (closest one in `fonts.jpg`; if the user owns the real font file, put it in `~/Stream Clips/fonts/`), fill
   colour, key-word colours, outline thickness, shadow (`hard`, `glow`, `soft` or none), slant, where it sits, and
   any tags, emoji, zooms, title style.
3. Write `~/Stream Clips/styles/<look name>.json`:

```json
{"base": "comic", "from": "https://www.tiktok.com/@clips/video/...", "font": "barlow-condensed/barlow-condensed-v13-latin-900italic.ttf",
 "size": 120, "case": "upper", "fill": "#FFFFFF", "colors": ["#FFE500"], "stroke": 9, "shadow": "hard", "skew": 0,
 "words": 2, "mode": "keywords", "anim": "pop", "notes": "yellow key words, caption on the seam"}
```

   `mode`: `keywords` (key words coloured), `current` (the word being said coloured), `none`.
   `anim`: `pop` or `null`. `skew`: slant, 0 to 0.25.
4. Use it with `"captions": "<look name>"`, render one still, put it next to a reference frame, and fix what is off.
   Tell the user it is a close match with free fonts, not an exact copy, unless they gave you the font file.

Copy the editing look only. Never reuse the other clip page's logo, watermark, name or footage.
