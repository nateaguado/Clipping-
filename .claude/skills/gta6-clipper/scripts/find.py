"""The moment finder: where the clip-worthy moments are in a stream VOD or a long video.

  find.py hot <channel link or name>          the channel's most-viewed viewer clips (last day / week), with the
                                               VOD and time of each: the fastest way to find what is already blowing up
  find.py vods <channel link>                 the channel's recent past streams (VODs)
  find.py scan <VOD or video link> [--from 2:00:00 --to 6:00:00] [--step 15]
                                               reads the signals across the whole stream and ranks candidate moments
  find.py listen <scan folder> [--top 12]     downloads only the sound around the top candidates and writes what was
                                               said, so Claude can judge each moment (candidates.md)

Signals, strongest first: viewer-made clips (Twitch, Kick), chat spikes with reaction words (KEKW, LMAO, W, L, "clip
it", skulls), YouTube's "Most replayed" graph, YouTube live chat replay. Chat reacts 5 to 20 s after the moment, so
every chat peak is moved back before it becomes a window.
Work goes in ~/Stream Clips/streams/<name>/.
"""
import argparse, collections, concurrent.futures as cf, datetime as dt, json, math, os, re, subprocess, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sc

TW_CID = 'kimne78kx3ncx6brgo4mv6wki5h1ko'  # Twitch's public web client id (no login)
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'
HYPE = re.compile(r"\b(kekw|lul|lol+|lmao+|lmfao+|omegalul|icant|pog+|poggers|pogchamp|w+|l+|wtf|nah+h*|bro+|clip+( it| that)?|\+2|o+mg+|holy|yo+|dead+|wat|what+|ratio|goat+|crazy|insane|bruh+|💀|😂|🤣|😭)\b|(💀|😂|🤣|😭|🔥|‼|❗)", re.I)
LAG = 10         # chat reacts about this long after the moment
PRE, POST = 35, 15  # window around a moment: room for the setup before, the reaction after


# ---------------------------------------------------------------- web helpers

# What kind of moment the chat is reacting to. Each message counts for the first mood it matches.
MOODS = {
    'funny': re.compile(r"\b(kekw|lul|lol+|lmao+|lmfao+|omegalul|icant|i cant|dead+|bruh+|pause|ayo+|crying|hahah\w*|xd+)\b|(💀|😂|🤣|😭)", re.I),
    'hype': re.compile(r"\b(pog+|poggers|pogchamp|lets+ go+|let's go+|w+|goat+|clutch|insane|crazy|holy|sheesh|cinema|aura|gg+|ez+|banger)\b|(🔥|🐐|‼|❗|🚀)", re.I),
    'drama': re.compile(r"\b(drama|beef|ratio|l+|yikes|cringe|awkward|monkas|madge|mad|tilted|exposed|cancel+ed|he lying|lying|cap|chat is this real|fight|banned|ban)\b|(😬|😳|🍿|D:)", re.I),
    'shock': re.compile(r"\b(what+|wat|wtf|no way|nah+h*|omg|o+mg+|wait+|huh+|real|wow+|bro what|how)\b|(😮|😱|🤯|❓|\?{2,})", re.I),
}
MOOD_WORDS = dict(funny='funny', hype='exciting / hype', drama='drama / tension', shock='shocking / interesting')


def mood_of(texts):
    """-> {mood: share of messages} for a list of chat lines."""
    n = max(1, len(texts))
    out = {k: 0 for k in MOODS}
    for x in texts:
        for k, rx in MOODS.items():
            if rx.search(x):
                out[k] += 1
                break
    return {k: round(v / n, 2) for k, v in out.items()}


def top_mood(m):
    if not m:
        return None
    k = max(m, key=m.get)
    return k if m[k] >= .12 else None


def get_json(url, headers=None, data=None, tries=4):
    h = {'User-Agent': UA, 'Accept': 'application/json'}
    h.update(headers or {})
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=h)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 403 and 'kick.com' in url:  # Kick's Cloudflare wall: look like a real browser
                try:
                    from curl_cffi import requests as cr
                    return cr.get(url, impersonate='chrome', timeout=30).json()
                except Exception:
                    pass
            if e.code in (404, 410):
                return None
        except Exception:
            pass
        time.sleep(1 + i)
    return None


def gql(query):
    d = get_json('https://gql.twitch.tv/gql', {'Client-Id': TW_CID, 'Content-Type': 'application/json'}, json.dumps({'query': query}).encode())
    return (d or {}).get('data') or {}


def hms(s):
    s = max(0, int(s))
    return f'{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}'


def secs(x):
    if x is None:
        return None
    s = 0.0
    for v in str(x).split(':'):
        s = s * 60 + float(v)
    return s


def iso(t):
    """'2026-11-15T09:42:58Z', '2026-11-15 09:42:58' (Kick, UTC) or with an offset -> aware datetime."""
    x = dt.datetime.fromisoformat(str(t).strip().replace('Z', '+00:00').replace(' ', 'T'))
    return x if x.tzinfo else x.replace(tzinfo=dt.timezone.utc)


# ---------------------------------------------------------------- what is this link?

def parse(link):
    """-> (platform, kind, id). kind is 'vod', 'channel' or 'video'."""
    s = link.strip()
    m = re.search(r'twitch\.tv/videos/(\d+)', s)
    if m:
        return 'twitch', 'vod', m.group(1)
    m = re.search(r'twitch\.tv/([A-Za-z0-9_]+)', s)
    if m and m.group(1).lower() not in ('videos', 'directory'):
        return 'twitch', 'channel', m.group(1).lower()
    m = re.search(r'kick\.com/([A-Za-z0-9_-]+)/videos/([0-9a-f-]{36})', s)
    if m:
        return 'kick', 'vod', m.group(2)
    m = re.search(r'kick\.com/([A-Za-z0-9_-]+)', s)
    if m:
        return 'kick', 'channel', m.group(1).lower()
    if re.search(r'youtube\.com|youtu\.be', s):
        if re.search(r'/@|/channel/|/c/', s) and 'watch' not in s:
            return 'youtube', 'channel', s
        return 'youtube', 'video', s
    if re.fullmatch(r'[A-Za-z0-9_-]{3,25}', s):
        return which_platform(s.lower()), 'channel', s.lower()
    if os.path.isfile(s):
        return 'file', 'video', os.path.abspath(s)
    raise SystemExit(f'not a Twitch, Kick or YouTube link: {link}')


def which_platform(name):
    """A bare name: whichever of Twitch and Kick has the most recent stream under it."""
    best = ('twitch', '')
    try:
        v = tw_vods(name, 1)[2]
        if v:
            best = ('twitch', v[0]['start'])
    except SystemExit:
        pass
    try:
        k = kick_vods(name)
        if k and str(iso(k[0]['start'])) > str(iso(best[1])) if best[1] else k:
            best = ('kick', k[0]['start'])
    except Exception:
        pass
    sc.log(f'{name}: using {best[0].title()} (most recent streams there).')
    return best[0]


# ---------------------------------------------------------------- Twitch

def tw_vods(login, n=10):
    d = gql('query{user(login:"%s"){displayName stream{id title viewersCount} videos(first:%d,type:ARCHIVE,sort:TIME){edges{node{id title lengthSeconds createdAt status}}}}}' % (login, n))
    u = d.get('user')
    if not u:
        raise SystemExit(f'no Twitch channel called {login}')
    vods = [dict(id=e['node']['id'], title=e['node']['title'], seconds=e['node']['lengthSeconds'], start=e['node']['createdAt'],
                 live=e['node']['status'] == 'RECORDING', url=f"https://www.twitch.tv/videos/{e['node']['id']}") for e in u['videos']['edges']]
    return u['displayName'], u.get('stream'), vods


def tw_vod(vid):
    d = gql('query{video(id:"%s"){id title lengthSeconds createdAt status owner{login displayName}}}' % vid)
    v = d.get('video')
    if not v:
        raise SystemExit('That Twitch VOD is not available (deleted, subscriber-only, or a typo).')
    return dict(platform='twitch', id=v['id'], title=v['title'], seconds=v['lengthSeconds'], start=v['createdAt'],
                live=v['status'] == 'RECORDING', channel=v['owner']['login'], streamer=v['owner']['displayName'],
                url=f"https://www.twitch.tv/videos/{v['id']}")


def tw_clips(login):
    """Viewer-made clips of a channel with views and their place in the VOD. Twitch blocks paging, so the first page of
    each period and sort order is combined (a few hundred clips: all the big ones)."""
    q = 'query{user(login:"%s"){clips(first:100,criteria:{period:%s,sort:%s}){edges{node{slug title viewCount createdAt durationSeconds videoOffsetSeconds video{id} curator{login}}}}}}'
    out = {}
    jobs = [(p, s) for p in ('LAST_DAY', 'LAST_WEEK', 'LAST_MONTH', 'ALL_TIME') for s in ('VIEWS_DESC', 'TRENDING')]
    with cf.ThreadPoolExecutor(4) as ex:
        for res in ex.map(lambda ps: gql(q % (login, ps[0], ps[1])), jobs):
            for e in (((res.get('user') or {}).get('clips') or {}).get('edges') or []):
                n = e['node']
                out[n['slug']] = dict(title=n['title'], views=n['viewCount'], at=n['createdAt'], seconds=n['durationSeconds'],
                                      offset=n['videoOffsetSeconds'], vod=(n.get('video') or {}).get('id'),
                                      url=f"https://clips.twitch.tv/{n['slug']}", by=(n.get('curator') or {}).get('login'))
    return list(out.values())


def tw_chat_page(vid, off):
    q = 'query{video(id:"%s"){comments(contentOffsetSeconds:%d){edges{node{contentOffsetSeconds commenter{login} message{fragments{text}}}}}}}' % (vid, off)
    v = gql(q).get('video') or {}
    return [dict(t=e['node']['contentOffsetSeconds'], u=(e['node'].get('commenter') or {}).get('login'),
                 x=''.join(f['text'] for f in e['node']['message']['fragments'])) for e in ((v.get('comments') or {}).get('edges') or [])]


# ---------------------------------------------------------------- Kick

def kick_channel(slug):
    c = get_json(f'https://kick.com/api/v2/channels/{slug}')
    if not c:
        raise SystemExit(f'no Kick channel called {slug} (or Kick blocked the request; try again in a minute)')
    return c


def kick_vods(slug):
    v = get_json(f'https://kick.com/api/v2/channels/{slug}/videos') or []
    out = []
    for x in v:
        out.append(dict(id=(x.get('video') or {}).get('uuid'), title=x.get('session_title'), seconds=int((x.get('duration') or 0) / 1000),
                        start=x.get('start_time'), live=bool(x.get('is_live')), source=x.get('source'), livestream_id=x.get('id'),
                        url=f"https://kick.com/{slug}/videos/{(x.get('video') or {}).get('uuid')}"))
    return out


def kick_vod(uuid):
    v = get_json(f'https://kick.com/api/v1/video/{uuid}')
    if not v:
        raise SystemExit('That Kick VOD is not available.')
    ls = v.get('livestream') or {}
    ch = ls.get('channel') or {}
    slug = ch.get('slug') or (ch.get('user') or {}).get('username', '').lower()
    return dict(platform='kick', id=uuid, title=ls.get('session_title'), seconds=int((ls.get('duration') or 0) / 1000),
                start=ls.get('start_time'), live=bool(ls.get('is_live')), source=v.get('source'), livestream_id=ls.get('id'),
                channel=slug, channel_id=ch.get('id'), streamer=(ch.get('user') or {}).get('username') or slug,
                url=f'https://kick.com/{slug}/videos/{uuid}')


def kick_clips(slug, livestream_id=None, vod_start=None, pages=6):
    out, cur = [], None
    for time_ in ('day', 'week', 'month'):
        cur = None
        for _ in range(pages):
            u = f'https://kick.com/api/v2/channels/{slug}/clips?sort=view&time={time_}' + (f'&cursor={cur}' if cur else '')
            d = get_json(u) or {}
            for c in d.get('clips') or []:
                out.append(c)
            cur = d.get('nextCursor')
            if not cur:
                break
    seen, res = set(), []
    for c in out:
        if c['id'] in seen:
            continue
        seen.add(c['id'])
        if livestream_id and str(c.get('livestream_id')) != str(livestream_id):
            continue
        res.append(c)
    clips = []
    want = sorted(res, key=lambda c: -(c.get('views') or c.get('view_count') or 0))[:60]
    with cf.ThreadPoolExecutor(6) as ex:
        details = list(ex.map(lambda c: get_json(f"https://kick.com/api/v2/clips/{c['id']}") or {}, want))
    for c, dd in zip(want, details):
        clip_ = dd.get('clip') or dd
        st = clip_.get('started_at')
        off = None
        if st and vod_start:
            off = (iso(st) - iso(vod_start)).total_seconds()
        clips.append(dict(title=c.get('title'), views=c.get('views') or c.get('view_count') or 0, seconds=c.get('duration'),
                          offset=off, started=st, vod=c.get('livestream_id'), at=c.get('created_at'), url=f"https://kick.com/{slug}/clips/{c['id']}"))
    return clips


def kick_chat_page(chan_id, vod_start, off):
    t = (iso(vod_start) + dt.timedelta(seconds=off)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    d = get_json(f'https://kick.com/api/v2/channels/{chan_id}/messages?start_time={t}') or {}
    ms = (d.get('data') or {}).get('messages') or []
    t0 = iso(vod_start)
    return [dict(t=(iso(m['created_at']) - t0).total_seconds(), u=(m.get('sender') or {}).get('username'),
                 x=re.sub(r'\[emote:\d+:([^\]]+)\]', r'\1', m.get('content') or '')) for m in ms]


# ---------------------------------------------------------------- YouTube

def yt_info(url):
    r = subprocess.run([sc.VPY(), '-m', 'yt_dlp', '-q', '--no-warnings', '--skip-download', '--dump-json', '--no-playlist', *sc.cookie_args(), url],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit('That YouTube video could not be read (private, members-only, or still live).')
    return json.loads(r.stdout)


def yt_chat(url, folder):
    """YouTube live chat replay (when the streamer left it on), as [{t, u, x, paid}]."""
    tmpl = os.path.join(folder, '_ytchat')
    subprocess.run([sc.VPY(), '-m', 'yt_dlp', '-q', '--no-warnings', '--skip-download', '--write-subs', '--sub-langs', 'live_chat',
                    '-o', tmpl, *sc.cookie_args(), url], capture_output=True)
    f = next((os.path.join(folder, x) for x in os.listdir(folder) if x.startswith('_ytchat') and x.endswith('.json')), None)
    msgs = []
    if not f:
        return msgs
    with open(f, encoding='utf-8') as fh:
        for line in fh:
            try:
                a = json.loads(line)['replayChatItemAction']
                t = int(a['videoOffsetTimeMsec']) / 1000
                for act in a.get('actions', []):
                    it = (act.get('addChatItemAction') or {}).get('item') or {}
                    r_ = it.get('liveChatTextMessageRenderer') or it.get('liveChatPaidMessageRenderer')
                    if not r_:
                        continue
                    txt = ''.join(run_.get('text') or (run_.get('emoji') or {}).get('shortcuts', [''])[0] for run_ in (r_.get('message') or {}).get('runs', []))
                    msgs.append(dict(t=t, u=(r_.get('authorName') or {}).get('simpleText'), x=txt, paid='liveChatPaidMessageRenderer' in it))
            except Exception:
                continue
    os.remove(f)
    return msgs


# ---------------------------------------------------------------- scoring

def sample_of(off, page, span):
    texts = [m['x'] for m in page]
    hype = sum(1 for x in texts if HYPE.search(x) or (len(set(x.lower().split())) == 1 and 0 < len(x) < 15)) / len(texts)
    paid = sum(1 for m in page if m.get('paid'))
    return dict(t=off, rate=len(page) / span, hype=hype, paid=paid, texts=texts, mood=mood_of(texts))


def chat_curve(samples, step):
    """How unusual the chat is at each point: its speed against the last 10 minutes, boosted when the messages are
    reactions (KEKW, LMAO, W, skulls, 'clip it') and by Super Chats. -> [(time, score)]"""
    out = []
    win = max(4, 600 // step)
    for k, x in enumerate(samples):
        base = [y['rate'] for y in samples[max(0, k - win):k] if y['rate'] > 0]
        if len(base) < max(4, 120 // step) or x['rate'] <= 0:  # needs 2 minutes of normal chat to compare with
            out.append((x['t'], 0.0)); continue
        mu = sum(base) / len(base)
        sd = math.sqrt(sum((v - mu) ** 2 for v in base) / len(base)) or max(.2, mu * .3)
        z = (x['rate'] - mu) / sd
        out.append((x['t'], max(0.0, z) * (1 + 1.5 * x['hype']) + .5 * x.get('paid', 0)))
    return out


def peaks(curve, k, gap_bins):
    order = sorted(range(len(curve)), key=lambda b: -curve[b])
    out = []
    for b in order:
        if curve[b] <= 0:
            break
        if all(abs(b - o) > gap_bins for o in out):
            out.append(b)
        if len(out) >= k:
            break
    return out


# ---------------------------------------------------------------- commands

def cmd_hot(a):
    plat, kind, ident = parse(a.channel)
    rows = []
    if plat == 'twitch':
        name = ident
        disp, live, vods = tw_vods(name, 20)
        vmap = {v['id']: v for v in vods}
        for c in tw_clips(name):
            v = vmap.get(c['vod'])
            rows.append(dict(c, vod_url=v['url'] if v else None, vod_title=v['title'] if v else None))
        sc.log(f'{disp} on Twitch' + (f" is LIVE now: {live['title']} ({live.get('viewersCount')} watching)" if live else ''))
    elif plat == 'kick':
        vods = kick_vods(ident)
        vmap = {str(v['livestream_id']): v for v in vods}
        for c in kick_clips(ident):
            v = vmap.get(str(c['vod']))
            if v and c.get('started') and v.get('start'):
                c['offset'] = (iso(c['started']) - iso(v['start'])).total_seconds()
            rows.append(dict(c, vod_url=v['url'] if v else None, vod_title=v['title'] if v else None))
        sc.log(f'{ident} on Kick')
    else:
        raise SystemExit('hot works with Twitch and Kick channels. For YouTube, use scan on the stream link.')
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=float(a.days))
    rows = [r for r in rows if r.get('at') and iso(r['at']) >= since]
    rows.sort(key=lambda r: -r['views'])
    if not rows:
        print(f'No viewer clips in the last {a.days} day(s). Try --days 7, or scan a VOD.')
        return
    print(f'Most-viewed viewer clips, last {a.days} day(s):')
    for r in rows[:a.top]:
        where = f"VOD {r['vod_url']} at {hms(r['offset'])}" if r.get('offset') is not None and r.get('vod_url') else 'VOD not saved (clip only)'
        print(f"{r['views']:>8,} views | {r['title'][:60]!r} | {where} | {r['url']}")
    print('\nA viewer clip that is already getting views is a moment people want. Make your own edit of it: '
          'clip.py new <name> --src <VOD link> --from <time - 30 s> --to <time + 30 s>')


def cmd_vods(a):
    plat, kind, ident = parse(a.channel)
    if plat == 'twitch':
        disp, live, vods = tw_vods(ident, 15)
        if live:
            print(f"LIVE NOW: {live['title']} ({live.get('viewersCount')} watching). The live VOD below grows as they stream.")
    elif plat == 'kick':
        vods = kick_vods(ident)
    else:
        raise SystemExit('vods works with Twitch and Kick channels. For YouTube, open the channel\'s Live tab and copy a stream link.')
    for v in vods:
        print(f"{'LIVE ' if v['live'] else ''}{v['start'][:16]} | {hms(v['seconds'])} | {v['title']!r} | {v['url']}")


def cmd_scan(a):
    plat, kind, ident = parse(a.link)
    if kind == 'channel':
        if plat == 'twitch':
            ident = tw_vods(ident, 1)[2][0]['id']
        elif plat == 'kick':
            ident = kick_vods(ident)[0]['id']
        else:
            raise SystemExit('Give a link to one stream or video, not the channel.')
        kind = 'vod'
        sc.log('Using the latest stream.')
    if plat == 'twitch':
        info = tw_vod(ident)
    elif plat == 'kick':
        info = kick_vod(ident)
    elif plat == 'youtube':
        y = yt_info(ident)
        info = dict(platform='youtube', id=y['id'], title=y.get('title'), seconds=int(y.get('duration') or 0), start=y.get('release_timestamp'),
                    live=bool(y.get('is_live')), channel=y.get('channel_id'), streamer=y.get('channel') or y.get('uploader'), url=y['webpage_url'],
                    heatmap=y.get('heatmap'), has_chat='live_chat' in (y.get('subtitles') or {}), views=y.get('view_count'))
    else:
        raise SystemExit('scan needs a Twitch, Kick or YouTube link. For a file on this computer, use listen with --file.')
    total = info['seconds']
    t_from = secs(a.start) or 0
    t_to = min(total, secs(a.end) or total)
    name = re.sub(r'[^A-Za-z0-9 _-]+', '', f"{info.get('streamer') or info.get('channel')} {info['title'] or ''}")[:60].strip() or info['id']
    folder = os.path.join(sc.conf()['work'], 'streams', f"{name} {info['id'][:8]}")
    os.makedirs(folder, exist_ok=True)
    sc.log(f"{info.get('streamer')}: {info['title']!r}, {hms(total)} long{' (still LIVE: scanning what is there so far)' if info.get('live') else ''}.")
    sc.log(f'Scanning {hms(t_from)} to {hms(t_to)}.')
    t0 = time.time()

    # 1. viewer clips
    clips = []
    if plat == 'twitch':
        clips = [c for c in tw_clips(info['channel']) if c['vod'] == info['id'] and c.get('offset') is not None]
    elif plat == 'kick':
        clips = [c for c in kick_clips(info['channel'], info['livestream_id'], info['start']) if c.get('offset') is not None]
    clips = [c for c in clips if t_from - 30 <= c['offset'] <= t_to]
    sc.log(f'  viewer clips of this stream: {len(clips)}' + (f" (top: {max(c['views'] for c in clips):,} views)" if clips else ''))

    # 2. chat, sampled: one page of messages at each step gives the chat speed and mood at that point
    samples = []
    step = int(a.step)
    offs = list(range(int(t_from), int(t_to), step))
    if plat in ('twitch', 'kick'):
        if plat == 'kick' and info.get('channel_id') is None:
            info['channel_id'] = kick_channel(info['channel'])['id']
        fetch = (lambda o: tw_chat_page(info['id'], o)) if plat == 'twitch' else (lambda o: kick_chat_page(info['channel_id'], info['start'], o))
        sc.log(f'  reading chat at {len(offs)} points (every {step} s), {sc.human_time(len(offs) / (10 if plat == "twitch" else 6))}...')
        with cf.ThreadPoolExecutor(8 if plat == 'twitch' else 5) as ex:
            for off, page in zip(offs, ex.map(fetch, offs)):
                page = [m for m in page if m['t'] >= off - 1]
                if len(page) >= 2:
                    span = max(.5, page[-1]['t'] - page[0]['t'])
                    samples.append(sample_of(off, page, span))
                else:
                    samples.append(dict(t=off, rate=0.0, hype=0.0, texts=[]))
    elif plat == 'youtube' and info.get('has_chat'):
        sc.log('  reading the live chat replay (the whole thing; a few minutes for a long stream)...')
        msgs = [m for m in yt_chat(info['url'], folder) if t_from <= m['t'] <= t_to]
        for off in offs:
            page = [m for m in msgs if off <= m['t'] < off + step]
            samples.append(sample_of(off, page, step) if page else dict(t=off, rate=0.0, hype=0.0, texts=[]))
    sc.log(f"  chat points read: {sum(1 for x in samples if x['rate'] > 0)} of {len(offs)}")

    # 3. score
    curve = chat_curve(samples, step)
    cands = []
    for c in clips:  # a viewer clip marks the moment itself (it ends where the clipper stopped)
        cands.append(dict(at=c['offset'] + (c.get('seconds') or 30) * .6, source='viewer clip', views=c['views'], title=c['title'], url=c['url']))
    heat = info.get('heatmap') or []
    if heat:
        vals = sorted(h['value'] for h in heat)
        med = vals[len(vals) // 2]
        for h in sorted(heat, key=lambda h: -h['value'])[:12]:
            if h['value'] > med * 1.6 and t_from <= h['start_time'] <= t_to:
                cands.append(dict(at=(h['start_time'] + h['end_time']) / 2, source='most replayed', strength=round(h['value'], 2)))
    for k in peaks([c for _, c in curve], int(a.top) * 2, max(1, 60 // step)):
        t, val = curve[k]
        cands.append(dict(at=max(0, t + step / 2 - LAG), source='chat spike', strength=round(val, 2), chat=samples[k]['texts'][:12],
                          allchat=samples[k]['texts'] + (samples[k + 1]['texts'] if k + 1 < len(samples) else [])))
    # merge candidates that are the same moment; rank
    cands.sort(key=lambda c: c['at'])
    merged = []
    for c in cands:
        if merged and abs(c['at'] - merged[-1]['at']) < 45:
            m = merged[-1]
            m['sources'] = sorted(set(m['sources']) | {c['source']})
            m['views'] = max(m.get('views', 0), c.get('views', 0))
            m['strength'] = max(m.get('strength', 0), c.get('strength', 0))
            if c.get('title'):
                m.setdefault('clip_titles', []).append(c['title'])
            if c.get('chat'):
                m['chat'] = (m.get('chat') or []) + c['chat']
                m['allchat'] = (m.get('allchat') or []) + c.get('allchat', [])
            if c['source'] == 'viewer clip' and c.get('views', 0) >= max(m.get('views', 0), 1):
                m['at'] = c['at']
        else:
            merged.append(dict(at=c['at'], sources=[c['source']], views=c.get('views', 0), strength=c.get('strength', 0),
                               clip_titles=[c['title']] if c.get('title') else [], chat=c.get('chat') or [], allchat=c.get('allchat') or [],
                               clip_url=c.get('url')))
    want = [w.strip().lower() for w in (a.want or 'any').split(',')]
    want = ['shock' if w in ('interesting', 'shocking') else 'hype' if w in ('exciting', 'hype') else w for w in want]
    for m in merged:
        texts = m.pop('allchat', []) or m.get('chat', [])
        m['mood_mix'] = mood_of(texts + m.get('clip_titles', [])) if texts or m.get('clip_titles') else {}
        m['mood'] = top_mood(m['mood_mix'])
        m['score'] = round(math.log10(1 + m['views']) * 5 + 4 * math.log2(1 + m['strength'] / 2) + 2 * (len(m['sources']) - 1), 2)  # what people already clipped and watched counts most
        if 'any' not in want and 'popular' not in want and m['mood_mix']:
            m['score'] = round(m['score'] * (1 + 2.5 * sum(m['mood_mix'].get(w, 0) for w in want)), 2)  # boost the kind the user asked for
        if 'popular' in want:
            m['score'] = round(m['score'] + math.log10(1 + m['views']) * 5, 2)
        m['from'] = max(0, m['at'] - PRE)
        m['to'] = min(total, m['at'] + POST)
    merged.sort(key=lambda m: -m['score'])
    res = dict(info={k: v for k, v in info.items() if k != 'heatmap'}, scanned=[t_from, t_to], step=step, candidates=merged[:int(a.top) * 2],
               signals=dict(viewer_clips=len(clips), chat_points=len(samples), heatmap=bool(heat)))
    sc.jdump(res, os.path.join(folder, 'scan.json'))
    if not merged:
        print('No strong moments found (no viewer clips, chat, or replay graph for this stream). Try another stream, or scan a '
              'shorter part (--from/--to) and make clips with clip.py new + prep, judging moments by the transcript.')
    print(f'Found {len(merged)} candidate moments in {sc.human_time(time.time() - t0)}. Top {min(len(merged), int(a.top))}:')
    for k, m in enumerate(merged[:int(a.top)]):
        extra = f" | {m['views']:,}-view viewer clip: {m['clip_titles'][0]!r}" if m['views'] else ''
        mood = f"  ({MOOD_WORDS[m['mood']]})" if m.get('mood') else ''
        print(f"{k + 1:>2}. {hms(m['at'])}  score {m['score']:5.1f}  [{', '.join(m['sources'])}]{mood}{extra}")
    print(f'\nSaved: {folder}\nNext: find.py listen "{folder}" --top {a.top}')


def grab_audio(info, a_, b_, out):
    """Only the sound of one window, from wherever the stream lives."""
    url = info.get('source') if info['platform'] == 'kick' else info['url']
    cmd = [sc.VPY(), '-m', 'yt_dlp', '-q', '--no-warnings', '-f', 'ba/worst', '--download-sections', f'*{a_:.1f}-{b_:.1f}',
           '-x', '--audio-format', 'wav', '--postprocessor-args', 'ExtractAudio:-ar 16000 -ac 1', '-o', out.replace('.wav', '.%(ext)s'),
           *sc.cookie_args(), url]
    if info['platform'] in ('twitch', 'kick'):
        r = sc.hls_section(info['url'] if info['platform'] == 'twitch' else info['source'], a_, b_, out, audio_only=True)
        return r['ok'], r['muted']
    subprocess.run(cmd, capture_output=True, timeout=600)
    return os.path.exists(out), False


def cmd_listen(a):
    folder = a.folder if os.path.isdir(a.folder) else os.path.join(sc.conf()['work'], 'streams', a.folder)
    res = sc.jload(os.path.join(folder, 'scan.json'))
    info = res['info']
    cands = res['candidates'][:int(a.top)]
    sc.log(f'Listening to the top {len(cands)} moments ({sum(c["to"] - c["from"] for c in cands) / 60:.0f} min of sound)...')
    lines = [f"# Candidates: {info.get('streamer')} - {info['title']}", f"Stream: {info['url']}", '',
             'Each window starts ~35 s before the moment and ends ~15 s after it. Words are timed in seconds of the STREAM.', '']
    for k, c in enumerate(cands):
        wav = os.path.join(folder, f'_c{k}.wav')
        ok = muted = False
        try:
            ok, muted = grab_audio(info, c['from'], c['to'], wav)
        except Exception as e:
            sc.log(f'  moment {k + 1}: could not download the sound ({e})')
        words = []
        if ok:
            words = sc.transcribe(wav)
            os.remove(wav)
        c['words'] = [dict(w, s=round(w['s'] + c['from'], 2), e=round(w['e'] + c['from'], 2)) for w in words]
        lines.append(f"## {k + 1}. {hms(c['at'])}  (window {hms(c['from'])} to {hms(c['to'])})  score {c['score']}  [{', '.join(c['sources'])}]")
        if c.get('mood_mix'):
            mix = ', '.join(f"{MOOD_WORDS[k]} {int(v * 100)}%" for k, v in sorted(c['mood_mix'].items(), key=lambda kv: -kv[1]) if v >= .05)
            lines.append(f"Chat mood: {mix or 'mixed'}" + (f"  -> looks {MOOD_WORDS[c['mood']]}" if c.get('mood') else ''))
        if muted:
            c['muted'] = True
            lines.append('WARNING: Twitch muted part of this window for copyrighted music (DMCA). The clip will have silence there.')
        if c.get('views'):
            lines.append(f"Viewer clip: {c['views']:,} views, titled {c['clip_titles'][0]!r}  {c.get('clip_url') or ''}")
        if c.get('chat'):
            lines.append('Chat right after: ' + ' | '.join(x[:40] for x in c['chat'][:12]))
        text, cur = [], []
        for w in c['words']:
            cur.append(w['w'])
            if re.search(r'[.!?]$', w['w']) or len(cur) > 18:
                text.append(f"[{hms(w['s'])}] " + ' '.join(cur)); cur = []
        if cur:
            text.append(' '.join(cur))
        lines.append('Said: ' + ('\n'.join(text) if text else '(no clear talking: a gameplay or music moment; judge by the signals)'))
        lines.append('')
        sc.log(f'  {k + 1}/{len(cands)} done')
    res['candidates'][:int(a.top)] = cands
    sc.jdump(res, os.path.join(folder, 'scan.json'))
    sc.write_text(os.path.join(folder, 'candidates.md'), '\n'.join(lines))
    print(os.path.join(folder, 'candidates.md'))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('hot'); s.add_argument('channel'); s.add_argument('--days', default=1); s.add_argument('--top', type=int, default=15)
    s = sub.add_parser('vods'); s.add_argument('channel')
    s = sub.add_parser('scan'); s.add_argument('link'); s.add_argument('--from', dest='start'); s.add_argument('--to', dest='end')
    s.add_argument('--step', default=15); s.add_argument('--top', default=12)
    s.add_argument('--want', default='any', help='any, popular, funny, hype (exciting), drama, shock (interesting); several with commas')
    s = sub.add_parser('listen'); s.add_argument('folder'); s.add_argument('--top', default=12)
    a = ap.parse_args()
    dict(hot=cmd_hot, vods=cmd_vods, scan=cmd_scan, listen=cmd_listen)[a.cmd](a)


if __name__ == '__main__':
    main()
