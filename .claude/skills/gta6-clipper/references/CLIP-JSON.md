# clip.json: every setting of one clip

`clip.py new` writes it; you edit it, then run `clip.py still` and `clip.py render`. Times can be seconds in the
finished clip (`3.5`) or a word from `clip.py prep`'s numbered transcript (`"w12"` = when word 12 starts, `"w12e"` = when it ends).

```json
{
  "layout": "auto",
  "cam": [0, 266, 398, 222],
  "cam_share": 0.42,
  "game_zoom": 1.0,
  "game_x": 0.5,
  "keep": [[2.0, 31.5]],
  "drop": ["40-44"],
  "tighten": null,
  "captions": "comic",
  "colors": {"w12": "yellow"},
  "tags": [{"at": "w23", "text": "CRASH"}],
  "emoji": [{"at": "w10", "e": "😭"}],
  "punch": [{"at": "w40", "zoom": 1.3, "shake": true, "sound": "boom"}],
  "caption_y": null,
  "spell": {"w31": "Chat,"},
  "censor": true,
  "hook": {"text": "Kai finally beats GTA 5 😭", "style": "outline", "until": "end"},
  "notes": [{"text": "He bet his whole stream on this", "at": 1.5}],
  "credit": "Kai Cenat on Twitch"
}
```

## Picture

| Key | What it does |
|---|---|
| `layout` | `auto` uses what `prep` found. `stack` = facecam on top, gameplay under it (gaming). `full` = a 9:16 window that follows the face (IRL, just chatting, reactions, podcasts). `game` = the whole picture across the middle on a blurred copy (no facecam, or the facecam is hidden). |
| `cam` | The facecam box in the source, `[x, y, w, h]` in pixels. `prep` finds it and draws it in green on `camcheck.jpg` with a grid labelled every 100 px. If the box is off, read the right numbers from the grid and set them here. Leave a little room around the face; the box is cropped to fill the top panel. |
| `cam_share` | How tall the facecam panel is, as a share of the clip (0.42 = 806 px). 0.35 to 0.5. |
| `game_zoom` | Zoom into the gameplay panel (1.0 = full height of the game picture). 1.2 to 1.5 brings small action closer. |
| `game_x` | Where the gameplay panel looks, 0 (left) to 1 (right). 0.5 is the middle. Move it so the action (the car, the character, the boss) is in view, and the facecam is not shown twice. |
| `game_y` | `game` layout only: where the picture sits (centre, in px from the top). Default 960. |
| `zoom` | `full` layout only: closer than the full height (1.0 to 1.6). Stays sharp up to about 1.4 on 1080p. |

## Cut

| Key | What it does |
|---|---|
| `keep` | (Story clips made with `new --parts` start with one range per part.) In seconds of the downloaded moment (`source.mp4`), not the finished clip. The in and out points, `[[start, end], ...]` in seconds of the downloaded moment. Several ranges join into one clip: the setup, then the payoff. Default: the whole moment. |
| `drop` | Word numbers to remove (`"40-44"`, `"12"`): a dead sentence, a ramble before the payoff. |
| `tighten` | Shortens silences longer than this many seconds (0.8 is tight). Off by default because stream moments are often loud without words (a scream, a crash, a jumpscare). |

## Text

| Key | What it does |
|---|---|
| `captions` | The caption look: `comic` (default, the MrBeast-style comic look), `punch` (one big word), `speedy` (2-3 italic words), `porter` (podcast look, whole phrase coloured), `hormozi`, `classic`, `bold`, `clean`, a look saved from a reference clip (`references/STYLES.md`), or `none`. |
| `caption_style` | Fine-tune the look: `{"size": 130, "colors": ["#FF3B3B"], "words": 1, "font": "anton/anton-v27-latin-regular.ttf", "skew": 0.15, "shadow": "glow"}`. `clip.py fonts` shows every font. |
| `colors` | Which words get the key colour, instead of the automatic pick (shouted words, numbers, names): `{"w12": "yellow", "w30-31": "green"}`. |
| `tags` | `*SOUND*` captions for action without words: `[{"at": "w23", "text": "CRASH", "for": 1.0}]`. |
| `emoji` | Emoji that pop in beside the caption: `[{"at": "w10", "e": "😭", "for": 1.2}]`. |
| `caption_y` | Height of the captions (centre, px). Default: on the seam in `stack`, 1250 in `full`, 1330 in `game`. Keep them between 300 and 1450 so the app's buttons never cover them. |
| `spell` | Fix what the speech reader misheard: names, slang, game words (`{"w12": "Kai", "w30": "NPC"}`). An empty string hides the word. Streams are noisy: always read the transcript for misheard names. |
| `censor` | `true` (default) shows strong swears as `f*ck` in the captions. The audio is not bleeped. |
| `hook` | The title at the top: `text`, `until` (`"end"` or a time), `style` (`plate` = black capitals on a white box, the story-page look, put it under the captions with `"y": 1400`; `outline` = white bold italic with one emoji at the end, the big clip-page look; `white` box with black words; `black` box), `size` (default 56), `y`. It moves off the face automatically. Emoji only show in `outline`. |
| `notes` | Context lines that pop in: `[{"text": "...", "at": "w20", "until": 6}]`. `style` `black` (default) or `white`, `y`. Only when a stranger would be lost without it, and only if it raises the stakes (who the other person is, what's at risk). Never filler labels like "Hour 103" (`HOOKS.md`). |
| `add_words` | Lines the speech reader missed (a quiet phone call, someone off camera): `[{"text": "what was the occasion?", "at": 47.0, "until": 47.9, "color": "yellow"}]`, times in seconds of `source.mp4`. Their words are numbered from w100000 (w100103 = 2nd line, 4th word). |
| `stickers` | Picture cards cut from the footage that pop in: `[{"at": "w43", "for": 1.8, "src": 2.6, "box": [x, y, w, h], "w": 440, "x": 260, "y": 250, "tilt": -6}]`. `src` is a second in `source.mp4` (or an image file), `box` the part of that frame in source pixels, `x`/`y` the centre on the finished picture. |
| `blur` | Hide burned-in text or a logo from the original: `[{"from": 0, "until": 3.7, "box": [x, y, w, h]}]` in finished-picture pixels. |
| `credit` | A small pill naming the streamer (`"Kai Cenat on Twitch"`). Many clipping programs require a credit; it is good manners anyway. |
| `streamer` | Saved from `clip.py new --streamer`; used in titles and posting notes. |

## Effects

| Key | What it does |
|---|---|
| `punch` | Quick zoom-ins: `[{"at": "w40", "zoom": 1.3, "for": 0.9, "shake": true, "flash": false, "sound": "boom"}]`. In `stack` only the facecam zooms. |
| `auto_punch` | `true` (default): the loudest moments get a punch-in by themselves, the very loudest with a shake and a boom. |
| `sounds` | Sound effects: `[{"at": "w5", "sound": "whoosh", "volume": 0.4}]`. Built in: `boom`, `whoosh`, `pop`, `ding`, `riser`; or a file name from `~/Stream Clips/sounds/`. |
| `auto_sounds` | `true` (default): a soft pop under each `*SOUND*` tag. |
| `effects` | `false` turns off all automatic punches and sounds. |

## Finished file

`clip.py render` writes `~/Stream Clips/finished/<clip name>.mp4` (1080x1920, 30 fps, sound at -14 LUFS, the loudness the apps play at).
