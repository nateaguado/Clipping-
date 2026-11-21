"""The editing layer that makes a clip feel alive: caption looks taken from viral clip channels, coloured key words,
*SOUND* tags, emoji pops, punch-in zooms with a shake, and sound effects.

The caption looks were measured from the most-viewed streamer clip Shorts in Nov 2026 (frames studied one by one):
  comic   the MrBeast-style comic caption: 1-2 slanted words, thick black outline, hard shadow, key words yellow/green
          (Jynxzi clips, 15M views)
  punch   ONE big condensed word at a time, white with a soft dark glow, loud words yellow (Kai Cenat Live, 10M;
          Live Speedy, 782K), *SOUND* tags
  speedy  2-3 heavy italic condensed words, key words yellow/green (SpeedUniverse, 9.1M)
  classic Montserrat Black, 3 words, the word being said in yellow (the Hormozi look)
  bold    Luckiest Guy, 2 words, green word being said
  clean   TikTok Sans sentence case with a soft shadow, 5 words
"""
import glob, math, os, re, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import sc

FONTS = os.path.join(sc.SKILL, 'fonts')
YELLOW, GREEN, RED, CYAN = '#FFE500', '#3BF26B', '#FF3B3B', '#38E1FF'

LOOKS = {
    'comic':   dict(font='luckiest-guy/luckiest-guy-v25-latin-regular.ttf', size=118, case='upper', fill='#FFFFFF', mode='keywords',
                    colors=[YELLOW, GREEN], stroke=11, shadow='hard', skew=.18, words=2, anim='pop'),
    'punch':   dict(font='barlow-condensed/barlow-condensed-v13-latin-900.ttf', size=150, case='upper', fill='#FFFFFF', mode='keywords',
                    colors=[YELLOW], stroke=9, shadow='glow', skew=0, words=1, anim='pop'),
    'speedy':  dict(font='barlow-condensed/barlow-condensed-v13-latin-900italic.ttf', size=118, case='upper', fill='#FFFFFF', mode='keywords',
                    colors=[YELLOW, GREEN], stroke=9, shadow='hard', skew=0, words=3, anim='pop'),
    'classic': dict(font='montserrat/montserrat-v31-latin-900.ttf', size=78, case='upper', fill='#FFFFFF', mode='current',
                    colors=[YELLOW], stroke=9, shadow=None, words=3, anim='pop'),
    'bold':    dict(font='luckiest-guy/luckiest-guy-v25-latin-regular.ttf', size=92, case='upper', fill='#FFFFFF', mode='current',
                    colors=[GREEN], stroke=10, shadow=None, words=2, anim='pop'),
    'clean':   dict(font='tiktok-sans/tiktok-sans-v8-latin-700.ttf', size=64, case='sentence', fill='#FFFFFF', mode='none',
                    colors=[], stroke=0, shadow='soft', words=5, anim=None),
    # the podcast-clip look (Michael Porter Jr. clips): tall condensed slanted capitals, 2-3 words, no outline, soft shadow,
    # the WHOLE phrase in one colour when it holds a key word (yellow, green, red), otherwise white
    'porter':  dict(font='bebas-neue/bebas-neue-v16-latin-regular.ttf', size=112, case='upper', fill='#FFFFFF', mode='group',
                    colors=[YELLOW, GREEN, RED], stroke=0, shadow='soft', skew=.12, words=3, anim='soft', slam=False),
    # the Hormozi look: Montserrat Black capitals, 3 words, the word being said in yellow, thick outline + hard shadow
    'hormozi': dict(font='montserrat/montserrat-v31-latin-900.ttf', size=80, case='upper', fill='#FFFFFF', mode='current',
                    colors=[YELLOW], stroke=9, shadow='hard', skew=0, words=3, anim='pop'),
    # the storytelling look of big IG/TikTok story edits: lowercase, 2-3 words, white with a soft shadow, no outline;
    # only the lines you colour (another person's words, the punchline) turn yellow
    'story':   dict(font='inter/inter-v20-latin-700.ttf', size=66, case='lower', fill='#FFFFFF', mode='keywords', auto_keys=False,
                    colors=[YELLOW], stroke=0, shadow='soft', skew=0, words=3, anim='soft', slam=False),
}
NAMED = dict(yellow=YELLOW, green=GREEN, red=RED, blue=CYAN, cyan=CYAN, white='#FFFFFF', orange='#FF9F1C', pink='#FF4FD8', purple='#A970FF')
STOP = set('a an the and or but so to of in on at for with is are was were be been am i you he she it we they me him her us them my your '
           'his its our their this that these those do does did not no yes yeah ok okay like just um uh oh ah if then than as by from up '
           'out what who how why when where there here can could would should will im its dont thats youre hes shes'.split())


def color(c):
    return NAMED.get(str(c).lower(), c)


def font_file(rel):
    """A font from the skill's fonts/, the user's own ~/Stream Clips/fonts, or a full path."""
    if rel and os.path.isabs(rel) and os.path.exists(rel):
        return rel
    mine = os.path.join(sc.conf().get('work', ''), 'fonts')
    for root in (FONTS, mine):
        f = os.path.join(root, rel or '')
        if rel and os.path.exists(f):
            return f
        hit = glob.glob(os.path.join(root, '**', os.path.basename(rel or 'x')), recursive=True)
        if hit:
            return hit[0]
    return os.path.join(FONTS, 'montserrat', 'montserrat-v31-latin-900.ttf')


def all_fonts():
    mine = os.path.join(sc.conf().get('work', ''), 'fonts')
    fs = sorted(glob.glob(os.path.join(FONTS, '*', '*.ttf'))) + sorted(glob.glob(os.path.join(mine, '**', '*.[ot]tf'), recursive=True))
    return fs


# ---------------------------------------------------------------- loudness: screamed words get colour, size and a punch

def word_loudness(media, words):
    """-> {word index: loudness 0..1 against this clip} from the clip's sound."""
    try:
        raw = subprocess.run([sc.FF(), '-v', 'error', '-i', media, '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                             capture_output=True, timeout=300).stdout
    except Exception:
        return {}
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    if not len(a):
        return {}
    db = {}
    for w in words:
        s, e = int(w['s'] * 16000), int(max(w['e'], w['s'] + .08) * 16000)
        seg = a[s:e]
        if len(seg):
            db[w['i']] = 20 * math.log10(float(np.sqrt(np.mean(seg ** 2))) + 1e-6)
    if not db:
        return {}
    v = np.array(list(db.values()))
    lo, hi = np.percentile(v, 20), np.percentile(v, 98)
    return {k: float(min(1, max(0, (x - lo) / max(3.0, hi - lo)))) for k, x in db.items()}


def loud_moments(media, total, top=6, gap=3.5):
    """Peaks of the sound (screams, crashes, big laughs): -> [(time, strength 0..1)], strongest first."""
    try:
        raw = subprocess.run([sc.FF(), '-v', 'error', '-i', media, '-vn', '-ac', '1', '-ar', '8000', '-f', 's16le', '-'],
                             capture_output=True, timeout=300).stdout
    except Exception:
        return []
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 800  # 0.1 s
    if len(a) < hop * 10:
        return []
    r = np.sqrt(np.convolve(a ** 2, np.ones(hop) / hop, 'valid')[::hop]) + 1e-6
    d = 20 * np.log10(r)
    base = np.percentile(d, 50)
    peak = np.percentile(d, 99.5)
    if peak - base < 8:  # a flat clip: nothing stands out
        return []
    out = []
    for k in np.argsort(-d):
        t = k / 10
        if d[k] < base + (peak - base) * .75:
            break
        if 1.0 < t < total - .5 and all(abs(t - o) > gap for o, _ in out):
            out.append((t, float((d[k] - base) / (peak - base))))
        if len(out) >= top:
            break
    return out


def keywords(words, loud, chosen=None, every=3):
    """Which words get the key colour: the ones Claude chose, else loud ones, numbers and names (about 1 in `every`)."""
    if chosen:
        return dict(chosen)
    out, last = {}, -9
    for k, w in enumerate(words):
        core = re.sub(r"[^\w']", '', w['w']).lower()
        if not core or core in STOP or len(core) < 3:
            continue
        lv = loud.get(w['i'], 0)
        big = lv > .78 or re.search(r'\d', core) or (w['w'][:1].isupper() and k and not re.search(r'[.!?]$', words[k - 1]['w']))
        if big and k - last >= 2:
            out[w['i']] = None
            last = k
        elif k - last >= every * 2 and lv > .55 and len(core) > 3:
            out[w['i']] = None
            last = k
    return out


# ---------------------------------------------------------------- caption pictures

class Pics:
    def __init__(self, look):
        self.look = look
        self.size = int(look['size'])
        self.font = ImageFont.truetype(font_file(look['font']), self.size)
        self.cache = {}

    def caption(self, toks, maxw=920):
        """toks: [(text, colour or None)]. -> RGBA picture."""
        key = tuple(toks)
        if key in self.cache:
            return self.cache[key]
        lk, f = self.look, self.font
        sp = f.getlength(' ')
        lines, cur = [], []
        for t in toks:
            if cur and f.getlength(' '.join(x[0] for x in cur + [t])) > maxw:
                lines.append(cur); cur = []
            cur.append(t)
        if cur:
            lines.append(cur)
        asc, desc = f.getmetrics()
        lh = int((asc + desc) * .98)
        st = int(lk.get('stroke') or 0)
        skew = float(lk.get('skew') or 0)
        pad = st + int(self.size * .35) + int(abs(skew) * lh * len(lines))
        widths = [sum(f.getlength(t) for t, _ in L) + sp * (len(L) - 1) for L in lines]
        size = (int(max(widths) + 2 * pad), int(lh * len(lines) + 2 * pad))
        txt = Image.new('RGBA', size, (0, 0, 0, 0))
        self._draw(ImageDraw.Draw(txt), lines, widths, pad, lh, sp, size[0])
        sh = lk.get('shadow')
        im = Image.new('RGBA', size, (0, 0, 0, 0))
        if sh:
            mask = Image.new('RGBA', size, (0, 0, 0, 0))
            self._draw(ImageDraw.Draw(mask), lines, widths, pad, lh, sp, size[0], solid=(0, 0, 0, 255))
            if sh == 'hard':  # a solid offset copy under the text: the comic / MrBeast look
                im.alpha_composite(mask, (0, int(self.size * .07)))
            elif sh == 'glow':  # a soft dark cloud: keeps one word readable on any background
                g = mask.filter(ImageFilter.GaussianBlur(self.size * .16))
                a = np.array(g); a[..., 3] = np.clip(a[..., 3].astype(np.int32) * 2, 0, 230).astype(np.uint8)
                im.alpha_composite(Image.fromarray(a))
            else:
                s = mask.filter(ImageFilter.GaussianBlur(self.size * .08))
                a = np.array(s); a[..., 3] = np.clip(a[..., 3].astype(np.int32) * 1.5, 0, 235).astype(np.uint8)
                im.alpha_composite(Image.fromarray(a), (0, int(self.size * .04)))
        im.alpha_composite(txt)
        if skew:
            im = im.transform(im.size, Image.AFFINE, (1, skew, -skew * im.height / 2, 0, 1, 0), Image.BICUBIC)
        bb = im.getbbox()
        if bb:
            m = 6
            im = im.crop((max(0, bb[0] - m), max(0, bb[1] - m), min(im.width, bb[2] + m), min(im.height, bb[3] + m)))
        self.cache[key] = im
        return im

    def _draw(self, d, lines, widths, pad, lh, sp, Wc, solid=None):
        lk, y = self.look, pad
        st = int(lk.get('stroke') or 0)
        for L, wd in zip(lines, widths):
            x = (Wc - wd) / 2
            for t, col in L:
                fill = solid or sc.hexrgb(color(col) if col else lk['fill'])
                kw = dict(stroke_width=st, stroke_fill=(0, 0, 0, 255)) if st else {}
                d.text((x, y), t, font=self.font, fill=fill, **kw)
                x += self.font.getlength(t) + sp
            y += lh


def shown(word, look, swears=None):
    t = word.strip()
    if swears:
        core = re.sub(r'[^a-z]', '', t.lower())
        if core in swears:
            t = re.sub(re.escape(core), swears[core], t, flags=re.I)
    if look.get('case') == 'upper':
        t = re.sub(r'[.,;:]+$', '', t)
        t = re.sub(r'(\d)S\b', r'\1s', t.upper())
    elif look.get('case') == 'lower':
        t = re.sub(r'[,;:]+$', '', t.lower())
    return t


def track(words, look, swears, total, keys, loud):
    """Caption groups over time. Each entry: s, e, first (when the group appeared), toks, loud (0..1)."""
    n = int(look.get('words') or 3)
    groups, cur = [], []
    for w in words:
        if not shown(w['w'], look, swears):
            continue
        brk = cur and (len(cur) >= n or w['s'] - cur[-1]['e'] > .4 or re.search(r'[.!?,]$', cur[-1]['w']))
        if brk:
            groups.append(cur); cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    cols = look.get('colors') or [YELLOW]
    out, ci = [], 0
    kcol = {}
    for g in groups:
        for w in g:
            if w['i'] in keys:
                kcol[w['i']] = color(keys[w['i']]) if keys[w['i']] else cols[ci % len(cols)]
                if not keys[w['i']]:
                    ci += 1
    for k, g in enumerate(groups):
        s = g[0]['s']
        e = groups[k + 1][0]['s'] if k + 1 < len(groups) and groups[k + 1][0]['s'] - g[-1]['e'] < .5 else g[-1]['e'] + .25
        e = min(e, total)
        lv = max(loud.get(w['i'], 0) for w in g)
        mode = look.get('mode')
        if mode == 'current':
            for j, w in enumerate(g):
                s_ = s if j == 0 else w['s']
                e_ = e if j == len(g) - 1 else g[j + 1]['s']
                out.append(dict(s=s_, e=e_, first=s, loud=lv, toks=[(shown(x['w'], look, swears), cols[0] if x is w else None) for x in g]))
        elif mode == 'group':  # one colour for the whole phrase: the colour of its key word, if it has one
            gc = next((kcol[x['i']] for x in g if x['i'] in kcol), None)
            out.append(dict(s=s, e=e, first=s, loud=lv, toks=[(shown(x['w'], look, swears), gc) for x in g]))
        else:
            out.append(dict(s=s, e=e, first=s, loud=lv,
                            toks=[(shown(x['w'], look, swears), kcol.get(x['i']) if mode == 'keywords' else None) for x in g]))
    return [t for t in out if t['e'] > t['s']]


def anim_scale(look, k, loud):
    """Entrance: a pop (small -> a bit big -> settle); a screamed word slams in from big instead."""
    if not look.get('anim'):
        return 1.0
    if look.get('anim') == 'soft':  # a small, calm settle for story captions
        return (.9, .96, 1.0)[k] if k < 3 else 1.0
    if loud > .85 and look.get('slam', True):
        seq = (1.45, 1.22, 1.06, .97, 1.0)
    else:
        seq = (.72, .9, 1.08, 1.03, 1.0)
    return seq[k] if k < len(seq) else 1.0


# ---------------------------------------------------------------- emoji

_EMOJI_FONTS = ['/System/Library/Fonts/Apple Color Emoji.ttc', 'C:/Windows/Fonts/seguiemj.ttf',
                '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf']
_emoji_cache = {}


def emoji_pic(e, size=150):
    """A colour emoji picture (Apple's on a Mac, Segoe's on Windows), or None if this computer can't draw it."""
    if (e, size) in _emoji_cache:
        return _emoji_cache[(e, size)]
    im = None
    for f in _EMOJI_FONTS:
        if not os.path.exists(f):
            continue
        for fs in (160, 137, 109, 96, 64, 128, 72):
            try:
                font = ImageFont.truetype(f, fs)
                c = Image.new('RGBA', (fs * 3, fs * 2), (0, 0, 0, 0))
                ImageDraw.Draw(c).text((fs // 2, fs // 4), e, font=font, embedded_color=True)
                bb = c.getbbox()
                if bb:
                    im = c.crop(bb)
                    break
            except Exception:
                continue
        if im is not None:
            break
    if im is not None:
        k = size / max(im.size)
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    _emoji_cache[(e, size)] = im
    return im


# ---------------------------------------------------------------- punch-in zoom and shake

def punch_at(punches, t):
    """-> (zoom, dx, dy) for time t. A punch snaps in over 2 frames, holds, then eases back out over 5 frames."""
    z, dx, dy = 1.0, 0.0, 0.0
    for p in punches:
        s, e = p['s'], p['e']
        if not (s <= t < e + 5 / sc.FPS):
            continue
        k = (t - s) * sc.FPS
        amt = p['zoom'] - 1
        if k < 2:
            f = (k + 1) / 3
        elif t < e:
            f = 1.0
        else:
            f = max(0.0, 1 - (t - e) * sc.FPS / 5)
        z = max(z, 1 + amt * f)
        if p.get('shake') and k < 9:
            rng = np.random.default_rng(int(s * 1000) + int(k))
            m = p['shake'] * (1 - k / 9)
            dx, dy = float(rng.uniform(-m, m)), float(rng.uniform(-m, m))
    return z, dx, dy


def apply_zoom(region, z, dx=0.0, dy=0.0, cy=.42, cx=.5):
    """Zoom a picture region (in place) around a point (cx, cy as shares of its width/height), with a shake offset in px."""
    import cv2
    if z <= 1.001 and not dx and not dy:
        return region
    h, w = region.shape[:2]
    cx_, cy_ = w * cx, h * cy
    M = np.float32([[z, 0, cx_ - z * cx_ + dx], [0, z, cy_ - z * cy_ + dy]])
    region[:] = cv2.warpAffine(region, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return region


def flash(frame, k, n=3, strength=.55):
    if k < n:
        a = strength * (1 - k / n)
        frame[:] = (frame.astype(np.float32) * (1 - a) + 255 * a).astype(np.uint8)


# ---------------------------------------------------------------- sound effects (made from scratch: no licence worries)

SR = 48000


def _env(n, attack, release):
    e = np.ones(n, np.float32)
    a = max(1, int(attack * SR)); r = max(1, int(release * SR))
    e[:a] = np.linspace(0, 1, a)
    e[-r:] *= np.linspace(1, 0, r) ** 2
    return e


def _lowpass(x, cutoff):
    # one-pole low-pass, cutoff can change over time
    y = np.zeros_like(x)
    cut = np.broadcast_to(np.asarray(cutoff, np.float32), x.shape)
    acc = 0.0
    al = 1 - np.exp(-2 * np.pi * cut / SR)
    for i in range(len(x)):
        acc += al[i] * (x[i] - acc)
        y[i] = acc
    return y


def make_sfx(name):
    rng = np.random.default_rng(7)
    if name == 'whoosh':
        n = int(.45 * SR); t = np.arange(n) / SR
        noise = rng.standard_normal(n).astype(np.float32)
        sweep = 300 + 5000 * np.sin(np.pi * t / t[-1]) ** 2
        x = _lowpass(noise, sweep) * np.sin(np.pi * t / t[-1]) ** 1.5
    elif name == 'boom':  # the deep hit under a big moment
        n = int(1.1 * SR); t = np.arange(n) / SR
        f = 38 + 70 * np.exp(-t * 9)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
        x += .35 * _lowpass(rng.standard_normal(n).astype(np.float32), 900) * np.exp(-t * 14)
        x = np.tanh(x * 2.2)
    elif name == 'pop':
        n = int(.12 * SR); t = np.arange(n) / SR
        f = 900 * np.exp(-t * 25) + 300
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 40)
    elif name == 'ding':
        n = int(.9 * SR); t = np.arange(n) / SR
        x = (np.sin(2 * np.pi * 1318 * t) + .4 * np.sin(2 * np.pi * 2637 * t)) * np.exp(-t * 5)
    elif name == 'riser':
        n = int(1.4 * SR); t = np.arange(n) / SR
        noise = rng.standard_normal(n).astype(np.float32)
        x = _lowpass(noise, 200 + 7000 * (t / t[-1]) ** 2) * (t / t[-1]) ** 2
        x += .25 * np.sin(2 * np.pi * np.cumsum(200 + 600 * t / t[-1]) / SR) * (t / t[-1])
    else:
        return None
    x = x.astype(np.float32)
    x *= _env(len(x), .004, .03)
    x /= max(1e-6, np.abs(x).max())
    return x


def sfx_sound(name):
    """A mono float array at 48 kHz: a built-in name (boom, whoosh, pop, ding, riser) or a sound file of the user's."""
    if name and os.path.exists(os.path.expanduser(name)):
        raw = subprocess.run([sc.FF(), '-v', 'error', '-i', os.path.expanduser(name), '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'],
                             capture_output=True).stdout
        return np.frombuffer(raw, np.float32).copy()
    mine = glob.glob(os.path.join(sc.conf().get('work', ''), 'sounds', f'{name}.*'))
    if mine:
        return sfx_sound(mine[0])
    cache = os.path.join(sc.TOOLS, 'sfx', f'{name}.npy')
    if os.path.exists(cache):
        return np.load(cache)
    x = make_sfx(name)
    if x is not None:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        np.save(cache, x)
    return x


def mix_sfx(wav_in, wav_out, hits):
    """Add sound effects onto the clip's sound. hits: [(time, name, volume 0..1)]."""
    with wave.open(wav_in) as w:
        ch, sr, n = w.getnchannels(), w.getframerate(), w.getnframes()
        a = np.frombuffer(w.readframes(n), np.int16).astype(np.float32).reshape(-1, ch) / 32768
    for t, name, vol in hits:
        x = sfx_sound(name)
        if x is None:
            continue
        if sr != SR:
            x = np.interp(np.arange(0, len(x), SR / sr), np.arange(len(x)), x).astype(np.float32)
        s = int(t * sr)
        if s >= len(a):
            continue
        x = x[:len(a) - s]
        a[s:s + len(x)] += (x * vol)[:, None]
    peak = np.abs(a).max()
    if peak > .98:
        a *= .98 / peak
    with wave.open(wav_out, 'wb') as w:
        w.setnchannels(ch); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((a * 32767).astype(np.int16).tobytes())


# ---------------------------------------------------------------- reference sheets: copy a creator's own reference look

def font_sheet(out):
    """Every caption font with a sample word, numbered, so a reference clip's font can be matched by eye."""
    fs = all_fonts()
    cols, cw, ch = 3, 620, 150
    rows = math.ceil(len(fs) / cols)
    im = Image.new('RGB', (cols * cw, rows * ch), (24, 120, 88))
    d = ImageDraw.Draw(im)
    small = ImageFont.truetype(font_file('inter/inter-v20-latin-700.ttf'), 20)
    for k, f in enumerate(fs):
        x, y = (k % cols) * cw, (k // cols) * ch
        try:
            F = ImageFont.truetype(f, 76)
            d.text((x + 20, y + 14), 'NO WAY 45', font=F, fill='white', stroke_width=6, stroke_fill='black')
        except Exception:
            pass
        rel = os.path.relpath(f, FONTS) if f.startswith(FONTS) else f
        d.text((x + 20, y + 118), f'{k + 1}. {rel}', font=small, fill=(255, 255, 255))
    im.save(out, quality=88)
    return out, fs
