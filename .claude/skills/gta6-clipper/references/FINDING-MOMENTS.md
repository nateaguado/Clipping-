# Finding the moments

## The signals, strongest first

1. **Viewer clips with views (Twitch, Kick).** Viewers clip what made them react. A clip with thousands of views is a
   moment strangers already want; your job is the best edit of it, posted fast. `find.py hot` lists them across the
   channel; `scan` uses them per stream. The clip's time marks the moment; the setup is usually 10 to 40 s before.
2. **Chat spikes.** Chat suddenly much faster than in the last 10 minutes, full of reactions (KEKW, LUL, LMAO, OMEGALUL,
   W, L, "clip it", +2, 💀😂😭). Chat reacts 5 to 20 s after the moment, so `scan` already moves each spike back 10 s.
   Weakness: when chat is hot for a whole segment (a big event), the best moment inside it may not stand out, which is
   why viewer clips come first.
3. **YouTube's most-replayed graph.** Where viewers rewound. Missing on streams only a few days old.
4. **YouTube live chat replay and Super Chats.** Many streamers switch replay off.
5. **What was said** (`listen`): the final judge. Read every candidate's transcript and chat lines.

## Kinds of moment (`scan --want`)

| Kind | Chat says | What it looks like |
|---|---|---|
| `popular` | (viewer clips with the most views) | Proven: people already clipped and watched it. |
| `funny` | KEKW, LUL, LMAO, ICANT, 💀😂😭 | A joke, a roast, a fail, a funny NPC, a bit. |
| `hype` (exciting) | POG, W, LETS GO, clutch, insane, 🔥🐐 | A clutch play, a win, a big pull, screaming. |
| `drama` | L, ratio, yikes, awkward, monkaS, 😬😳🍿 | An argument, an awkward silence, tension, getting called out. Careful: true and fair only. |
| `shock` (interesting) | WHAT, no way, wait, huh, 😮🤯 | A reveal, a twist, a surprising fact, something nobody expected. |

## Judging a moment: would a stranger watch to the end?

Keep it if you can say yes to most of these:
- **Instant read:** a stranger understands what is happening within 2 seconds (with a title and one context note).
- **A clear payoff:** a laugh, a shocked reaction, a fail, a win after struggle, a roast, a twist, a wild NPC, a
  glitch, a "streamer finds X" discovery, a real-life bit (like ordering Big Smoke's meal at a drive-thru).
- **The reaction is on screen:** the face (facecam or IRL) when it happens. A reaction you can only hear is weaker.
- **Short:** the setup plus payoff fit in 15 to 45 s. If the setup takes two minutes, it needs a context note
  instead, or it is a long-form compilation moment.
- **Works without the stream:** no inside joke a new viewer can't follow (a note can fix a small one).

Strong formats for gaming streams (by evidence, Nov 2026): first reactions to something new; "streamer finds / spots
X"; rage and difficulty; marathon milestones ("hour 30, 400 deaths"); RP bits; funny NPC or glitch moments; drama
moments (careful: true, fair, no accusations).

Skip (or flag to the user): moments with music playing or a Twitch `muted` warning, sponsor reads, gambling, anything
on the never-clip list in SKILL.md, and dead air.

## In and out points

- **In:** the last moment a stranger needs to understand the payoff. Usually the line that sets it up ("Can I get
  two number 9s..."), not the minute of build-up before it. Start mid-action rather than on silence.
- **Out:** 1 to 3 s after the peak reaction. End on the laugh or the line, not on the calm after it.
- **Join two parts** when the setup and payoff are apart: `"keep": [[3, 14], [52, 70]]`.
- **Drop** a ramble or a dead sentence in the middle with `drop` (word numbers).
- A clip can be longer than 45 s if every few seconds something new happens. Over 60 s only for TikTok Creator
  Rewards (it needs 1 minute+) and only if it holds.

## Two outputs from one big moment

- The short (15 to 45 s) for TikTok, Shorts, Reels.
- For a big shared event (a trailer, a launch, a famous moment several streamers reacted to): a multi-streamer
  compilation for YouTube long-form ("Streamers react to ..."), one chapter per streamer. A 2.8K-subscriber channel
  got 595K views with one in 2026. Make each reaction with `clip.py` (landscape is fine: set `layout` `game`), and
  join them with ffmpeg in a 16:9 version if the user wants that.
