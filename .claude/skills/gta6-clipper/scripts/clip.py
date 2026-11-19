"""The clip editor: turns a moment from a stream or YouTube video into a finished 1080x1920 clip.

  clip.py new <name> --src <file or link> [--from 1:02:03 --to 1:03:10]   grab the moment (only that part is downloaded)
  clip.py new <name> --src <link> --parts "0:05-0:10,0:31-0:41,6:03-6:07"   a story: several moments joined in order
  clip.py auto <stream link> [--top 6]   one command: the top chat spikes cut and rendered as captioned drafts
  clip.py prep <name>          words with numbers + the layout it found (camcheck.jpg shows the facecam box)
  clip.py still <name> 3.5     one finished frame at 3.5 s (or at a word: w12), for a quick look
  clip.py render <name>        the finished MP4, into ~/Stream Clips/finished
  clip.py batch <n1> <n2> ...  render several, one after another
  clip.py ref <look name> --src <link or file>   study a reference clip's look (frames sheet + numbered font samples)
  clip.py fonts                 every caption font on one numbered sheet

A clip is a folder in ~/Stream Clips/clips/ with clip.json (see references/CLIP-JSON.md).
"""
import argparse, glob, json, os, re, subprocess, sys, time
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sc
import fx as FX

W, H, FPS = sc.W, sc.H, sc.FPS
FONTS = os.path.join(sc.SKILL, 'fonts')
SWEARS = {'fuck': 'f*ck', 'fucking': 'f*cking', 'fucked': 'f*cked', 'motherfucker': 'motherf*cker', 'shit': 'sh*t', 'bitch': 'b*tch',
          'bitches': 'b*tches', 'nigga': 'n*gga', 'niggas': 'n*ggas', 'pussy': 'p*ssy', 'dick': 'd*ck', 'cunt': 'c*nt', 'asshole': 'a**hole'}
CAPTION_LOOKS = FX.LOOKS


def clips_dir():
    return os.path.join(sc.conf()['work'], 'clips')


def clip_dir(name):
    d = name if os.path.isdir(name) else os.path.join(clips_dir(), name)
    if not os.path.exists(os.path.join(d, 'clip.json')):
        raise SystemExit(f'no clip called {name}')
    return d


def load(d):
    return sc.jload(os.path.join(d, 'clip.json'))


def save(d, p):
    sc.jdump(p, os.path.join(d, 'clip.json'))


def secs(x):
    """'1:02:03', '62:03', '3723' or 3723.5 -> seconds."""
    if isinstance(x, (int, float)):
        return float(x)
    parts = [float(v) for v in str(x).strip().split(':')]
    s = 0.0
    for v in parts:
        s = s * 60 + v
    return s


def hms(s):
    s = max(0, s)
    return f'{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:05.2f}'


def font_file(rel):
    f = rel if os.path.isabs(rel) else os.path.join(FONTS, rel)
    if not os.path.exists(f):
        hit = glob.glob(os.path.join(FONTS, '**', os.path.basename(rel)), recursive=True)
        f = hit[0] if hit else os.path.join(FONTS, 'montserrat', 'montserrat-v31-latin-900.ttf')
    return f


# ---------------------------------------------------------------- new: grab the moment

def grab(srcarg, t0, t1, src, d):
    """Download (or copy) one moment of a stream, video or file to `src`. Returns where it came from."""
    hls = None
    if re.search(r'twitch\.tv/videos/', srcarg):
        hls = srcarg
    elif re.search(r'kick\.com/[^/]+/videos/', srcarg):
        import find
        hls = find.kick_vod(re.search(r'videos/([0-9a-f-]{36})', srcarg).group(1))['source']
    if hls:
        if t0 is None or t1 is None:
            raise SystemExit('For a stream link, give --from and --to (only the moment is downloaded).')
        sc.log(f'Downloading {hms(t0)} to {hms(t1)} of the stream ({t1 - t0:.0f} s)...')
        r = sc.hls_section(hls, t0, t1, src)
        if r['muted']:
            sc.log('WARNING: Twitch muted part of this moment for copyrighted music: that part is silent.')
        origin = dict(url=srcarg, start=t0, end=t1, muted=r['muted'])
    elif re.match(r'https?://', srcarg):
        if t0 is None or t1 is None:
            raise SystemExit('For a link, give --from and --to (a stream is hours long; only the moment is downloaded).')
        sc.log(f'Downloading {hms(t0)} to {hms(t1)} from the link ({t1 - t0:.0f} s)...')
        tmpl = os.path.join(d, '_dl.%(ext)s')
        cmd = [sc.VPY(), '-m', 'yt_dlp', '-q', '--no-warnings', '--no-playlist', '-f', 'bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b',
               '--download-sections', f'*{t0:.2f}-{t1:.2f}', '--force-keyframes-at-cuts', '--merge-output-format', 'mp4', '-o', tmpl]
        cmd += sc.cookie_args()
        for attempt in range(3):  # YouTube sometimes drops one section download: try again before giving up
            for x in glob.glob(os.path.join(d, '_dl.*')):
                os.remove(x)
            r = subprocess.run(cmd + [srcarg])
            got = glob.glob(os.path.join(d, '_dl.*'))
            if not r.returncode and got:
                break
            time.sleep(3)
        if r.returncode or not got:
            raise SystemExit('DOWNLOAD_FAILED: the link could not be downloaded. If it is subscriber-only or private, ask the user to '
                             'download the VOD part themselves and use --src with the file.')
        os.replace(got[0], src)
        origin = dict(url=srcarg, start=t0, end=t1)
    else:
        if not os.path.isfile(srcarg):
            raise SystemExit(f'cannot find the video: {srcarg}')
        cmd = [sc.FF(), '-v', 'error', '-y']
        if t0 is not None:
            cmd += ['-ss', f'{t0:.3f}']
        if t1 is not None:
            cmd += ['-to', f'{t1:.3f}']
        sc.run(*cmd, '-i', srcarg, '-c:v', 'libx264', '-preset', 'fast', '-crf', '16', '-c:a', 'aac', '-b:a', '192k', src)
        origin = dict(file=os.path.abspath(srcarg), start=t0 or 0, end=t1)
    return origin


def cmd_new(a):
    base = os.path.join(clips_dir(), re.sub(r'[^A-Za-z0-9 _-]+', '', a.name).strip() or 'clip')
    d, k = base, 2
    while os.path.exists(os.path.join(d, 'clip.json')):  # never overwrite another clip
        d, k = f'{base} {k}', k + 1
    os.makedirs(d, exist_ok=True)
    src = os.path.join(d, 'source.mp4')
    keep = None
    if a.parts:
        # a story clip: several moments of the same stream or video, joined in order (setup, twist, payoff).
        # Each part is downloaded with 1 s spare on both sides; `keep` starts on the exact parts.
        parts = []
        for chunk in a.parts.split(','):
            lo, _, hi = chunk.strip().partition('-')
            parts.append((secs(lo), secs(hi)))
        files, keep, t = [], [], 0.0
        for k_, (lo, hi) in enumerate(parts):
            f_ = os.path.join(d, f'_part{k_}.mp4')
            lo2 = max(0.0, lo - 1)
            sc.log(f'Part {k_ + 1} of {len(parts)}:')
            grab(a.src, lo2, hi + 1, f_, d)
            dur = sc.probe(f_)['dur']
            keep.append([round(t + lo - lo2, 2), round(min(t + dur, t + hi - lo2), 2)])
            files.append(f_); t += dur
        ins = sum([['-i', f_] for f_ in files], [])
        w0, h0 = sc.probe(files[0])['w'], sc.probe(files[0])['h']  # every part at the first part's size
        fc = ''.join(f'[{k_}:v]fps={FPS},scale={w0}:{h0}:force_original_aspect_ratio=decrease,pad={w0}:{h0}:-1:-1,setsar=1[v{k_}];'
                     f'[{k_}:a]aresample=48000[a{k_}];' for k_ in range(len(files)))
        fc += ''.join(f'[v{k_}][a{k_}]' for k_ in range(len(files))) + f'concat=n={len(files)}:v=1:a=1[v][a]'
        sc.run(sc.FF(), '-v', 'error', '-y', *ins, '-filter_complex', fc, '-map', '[v]', '-map', '[a]', '-c:v', 'libx264',
               '-preset', 'fast', '-crf', '16', '-c:a', 'aac', '-b:a', '192k', src)
        for f_ in files:
            os.remove(f_)
        origin = dict(url=a.src, parts=parts)
    else:
        t0, t1 = (secs(a.start) if a.start else None), (secs(a.end) if a.end else None)
        origin = grab(a.src, t0, t1, src, d)
    i = sc.probe(src)
    p = dict(name=os.path.basename(d), origin=origin, seconds=round(i['dur'], 2), size=[i['w'], i['h']], layout='auto',
             captions='comic', hook=None, keep=keep, drop=[], spell={}, censor=True, credit=None,
             created=time.strftime('%Y-%m-%d %H:%M'))
    if a.streamer:
        p['streamer'] = a.streamer
    save(d, p)
    sc.log(f'Saved {i["dur"]:.1f} s ({i["w"]}x{i["h"]}).')
    print(d)


# ---------------------------------------------------------------- prep: words + layout

def cmd_prep(a, d=None):
    d = d or clip_dir(a.name)
    p = load(d)
    src = os.path.join(d, 'source.mp4')
    t0 = time.time()
    sc.log(f'Listening to every word ({p["seconds"]:.0f} s)...')
    wav = os.path.join(d, '_audio16k.wav')
    sc.run(sc.FF(), '-v', 'error', '-y', '-i', src, '-ar', '16000', '-ac', '1', wav)
    words = sc.transcribe(wav)
    os.remove(wav)
    for k, w in enumerate(words):
        w['i'] = k
    sc.jdump(dict(words=words), os.path.join(d, 'words.json'))
    sc.log('Finding the layout (facecam, gameplay, or a full-screen face)...')
    lay = detect_layout(src)
    sc.jdump(lay, os.path.join(d, 'layout.json'))
    camcheck(src, lay, os.path.join(d, 'camcheck.jpg'))
    sc.learn('prep', p['seconds'], time.time() - t0)
    print_words(words)
    sc.log(f"LAYOUT: {lay['kind']}  ({lay['why']})")
    if lay.get('cam'):
        sc.log(f"FACECAM BOX (x, y, w, h in the source): {lay['cam']}  -> look at camcheck.jpg; if the green box is off, "
               'set "cam": [x, y, w, h] in clip.json')
    sc.log(f'Ready. {len(words)} words. {os.path.join(d, "camcheck.jpg")}')


def print_words(words):
    line, out = [], []
    for w in words:
        line.append(f"{w['i']}:{w['w']}")
        if re.search(r'[.!?]$', w['w']) or len(line) >= 14:
            out.append(f"[{words[int(line[0].split(':')[0])]['s']:6.2f}s] " + ' '.join(line)); line = []
    if line:
        out.append(f"[{words[int(line[0].split(':')[0])]['s']:6.2f}s] " + ' '.join(line))
    print('\n'.join(out) if out else '(no talking heard)')


def sample_frames(src, n=24, width=640):
    cap = cv2.VideoCapture(src)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    sw, sh = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out = []
    for i in np.linspace(total * .03, total * .97, n).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, img = cap.read()
        if ok:
            out.append(cv2.resize(img, (width, int(width * sh / sw))))
    cap.release()
    return out, (sw, sh)


def detect_layout(src):
    """What kind of stream picture this is:
       stack - gameplay with a small facecam: the clip shows the facecam on top and the gameplay under it
       full  - a big face (IRL, just chatting, reaction): the clip follows the face, full screen
       game  - no face at all: gameplay across the middle with a blurred copy behind it"""
    frames, (sw, sh) = sample_frames(src, width=1280)
    if not frames:
        raise SystemExit('could not read the video')
    fw_, fh_ = frames[0].shape[1], frames[0].shape[0]
    det = sc.face_detector(fw_, fh_, score=.6)
    faces = []
    pairs = 0
    for img in frames:
        _, f = det.detect(img)
        if f is not None and len(f):
            f = [r for r in f.tolist() if r[14] >= .8 and r[2] >= img.shape[1] * .012]  # sure faces, not a poster in the back
            if f:
                x, y, w, h = max((r[:4] for r in f), key=lambda r: r[2] * r[3])
                faces.append((x, y, w, h))
                big = [r for r in f if r[2] >= w * .5]
                if len(big) >= 2 and max(r[0] for r in big) - min(r[0] for r in big) > w * 3:
                    pairs += 1  # two people far apart in the same picture
    k = sw / fw_
    if len(faces) < max(3, len(frames) * .3):
        return dict(kind='game', why=f'a face was seen in only {len(faces)} of {len(frames)} frames', size=[sw, sh])
    fx, fy, fw, fh = (float(np.median([f[j] for f in faces])) for j in range(4))
    share = fw / fw_
    if pairs >= len(frames) * .35 and sw > sh:
        return dict(kind='game', why='two people far apart in the picture: the whole picture is shown so nobody is cut off', size=[sw, sh],
                    face=[round(v * k) for v in (fx, fy, fw, fh)])
    if share >= .1 or sh > sw:
        return dict(kind='full', why=f'the face fills {share:.0%} of the width', size=[sw, sh], face=[round(v * k) for v in (fx, fy, fw, fh)])
    # a facecam face stays inside its little box; a face that walks around the picture is a room camera (IRL)
    near = [f for f in faces if abs(f[0] - fx) < fw * 1.2 and abs(f[1] - fy) < fh * 1.2]
    if len(near) < len(faces) * .7:
        return dict(kind='full', why=f'the face moves around the whole picture (a room or IRL camera, not a facecam)', size=[sw, sh],
                    face=[round(v * k) for v in (fx, fy, fw, fh)])
    fx, fy, fw, fh = (float(np.median([f[j] for f in near])) for j in range(4))
    cam = cam_box(frames, (fx, fy, fw, fh))
    if cam[2] * cam[3] > fw_ * fh_ * .4:  # a 'facecam' this big is the whole camera picture: no game behind it
        return dict(kind='full', why='the camera fills the picture (IRL or a real-life scene, no gameplay)', size=[sw, sh],
                    face=[round(v * k) for v in (fx, fy, fw, fh)])
    return dict(kind='stack', why=f'a small face ({share:.0%} of the width) sits in a facecam', size=[sw, sh],
                face=[round(v * k) for v in (fx, fy, fw, fh)], cam=[round(v * k) for v in cam])


def cam_box(frames, face):
    """The facecam rectangle around a small face. A facecam's border does not move while the game does, so in the
    median of many frames its edges are long unbroken lines: first the top and bottom (lines running across the
    face's whole column), then the sides (lines running that exact height). A missing side is filled in from the
    webcam's 16:9 shape. camcheck.jpg shows the result on a grid so Claude can correct it by eye."""
    fx, fy, fw, fh = face
    med = np.median(np.stack([cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]), axis=0).astype(np.float32)
    Hh, Ww = med.shape
    gx = np.abs(cv2.Sobel(med, cv2.CV_32F, 1, 0, ksize=3)) > 24
    gy = np.abs(cv2.Sobel(med, cv2.CV_32F, 0, 1, ksize=3)) > 24
    x0, x1 = int(max(0, fx - 2.5 * fw)), int(min(Ww, fx + 3.5 * fw))

    def hline(lo, hi, nearest_to):
        ys = [(gy[y, x0:x1].mean(), -abs(y - nearest_to), y) for y in range(int(max(1, lo)), int(min(Hh - 1, hi)))]
        ys = [t for t in ys if t[0] >= .8]
        return max(ys)[2] if ys else None  # the most unbroken line; if equal, the nearest

    T = hline(fy - 6 * fh, fy - .3 * fh, fy)
    B = hline(fy + 1.3 * fh, fy + 8 * fh, fy + fh)
    if T is None:
        T = 0 if fy < fh * 3 else None
    if B is None:
        B = Hh if Hh - (fy + fh) < fh * 3 else None
    if T is None or B is None:  # no clear border: a 16:9 box where the face is about a third of the width
        dw = min(Ww, fw * 3.4); dh = dw * 9 / 16
        L, T_ = max(0, fx + fw / 2 - dw / 2), max(0, fy + fh / 2 - dh * .45)
        return L, T_, min(Ww - L, dw), min(Hh - T_, dh)
    ch = B - T

    def vline(lo, hi, nearest_to):
        xs = [(gx[int(T) + 3:int(B) - 3, x].mean(), -abs(x - nearest_to), x) for x in range(int(max(1, lo)), int(min(Ww - 1, hi)))]
        xs = [t for t in xs if t[0] >= .85]
        return max(xs)[2] if xs else None

    L = vline(fx - ch * 2.2, fx - .4 * fw, fx)
    R = vline(fx + fw * 1.4, fx + ch * 2.2, fx + fw)
    want = ch * 16 / 9
    if L is None and R is None:
        L = fx + fw / 2 - want / 2; R = L + want
    elif L is None:
        L = R - want
    elif R is None:
        R = L + want
    if L < fw * .8:  # within a sliver of the frame edge: the facecam starts at the edge
        L = 0
    if Ww - R < fw * .8:
        R = Ww
    L, R = max(0, L), min(Ww, R)
    return L, T, R - L, ch


def camcheck(src, lay, out):
    """A frame with the facecam box (green) and the face (orange) drawn on it, plus a grid labelled in source pixels
    every 100 px, so a wrong box can be read off and corrected in clip.json."""
    frames, (sw, sh) = sample_frames(src, n=3, width=1280)
    img = frames[len(frames) // 2].copy()
    k = img.shape[1] / sw
    for v in range(100, max(sw, sh), 100):
        col = (255, 255, 255) if v % 500 else (0, 255, 255)
        if v < sw:
            cv2.line(img, (int(v * k), 0), (int(v * k), img.shape[0]), col, 1)
            cv2.putText(img, str(v), (int(v * k) + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, .35, col, 1)
        if v < sh:
            cv2.line(img, (0, int(v * k)), (img.shape[1], int(v * k)), col, 1)
            cv2.putText(img, str(v), (2, int(v * k) - 2), cv2.FONT_HERSHEY_SIMPLEX, .35, col, 1)
    if lay.get('cam'):
        x, y, w, h = [int(v * k) for v in lay['cam']]
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 3)
    if lay.get('face'):
        x, y, w, h = [int(v * k) for v in lay['face']]
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 160, 255), 2)
    sc.imwrite(out, img, [cv2.IMWRITE_JPEG_QUALITY, 88])


def sw_small(src):
    return 960


# ---------------------------------------------------------------- the cut

def plan_cut(p, words, total):
    """Which parts of the moment stay. `keep` ranges (seconds) set the in and out points (several ranges join into
    one clip: a setup and its payoff). `drop` removes words, `tighten` shortens long silences. Stream moments are
    often loud without words (a scream, a crash), so silence is only cut when asked."""
    keep = p.get('keep') or [[0, total]]
    segs = [[max(0, secs(a)), min(total, secs(b))] for a, b in keep]
    drop = set()
    for r in p.get('drop', []):
        lo, _, hi = str(r).replace('w', '').partition('-')
        drop.update(range(int(lo), int(hi or lo) + 1))
    for i in sorted(drop):
        w = next((x for x in words if x['i'] == i), None)
        if not w:
            continue
        nxt = [s for s in segs]
        segs = []
        for a, b in nxt:
            if w['s'] >= b or w['e'] <= a:
                segs.append([a, b]); continue
            if w['s'] - .02 > a:
                segs.append([a, w['s'] - .02])
            if w['e'] + .02 < b:
                segs.append([w['e'] + .02, b])
    tg = p.get('tighten')
    if tg:
        out = []
        for a, b in segs:
            inside = [w for w in words if a <= w['s'] < b and w['i'] not in drop]
            cur = a
            for w1, w2 in zip(inside, inside[1:]):
                if w2['s'] - w1['e'] > tg:
                    out.append([cur, w1['e'] + .15]); cur = w2['s'] - .1
            out.append([cur, b])
        segs = out
    segs = [(round(a, 3), round(b, 3)) for a, b in segs if b - a > .08]
    if not segs:
        raise SystemExit('Nothing is left after keep/drop: check clip.json.')
    return segs, drop


def remap(words, segs, drop):
    out, t, bounds = [], 0.0, []
    for a, b in segs:
        bounds.append((a, b, t)); t += b - a
    for w in words:
        if w['i'] in drop:
            continue
        for a, b, o in bounds:
            if a - 1e-3 <= w['s'] < b:
                out.append(dict(w, s=round(w['s'] - a + o, 3), e=round(min(w['e'], b) - a + o, 3)))
                break
    return out, t, [o for _, _, o in bounds]


def cut_for(d, segs):
    out = os.path.join(d, '_cut.mp4')
    try:
        if os.path.exists(out) and [list(x) for x in sc.jload(os.path.join(d, '_cut.json'))] == [list(x) for x in segs]:
            return out
    except Exception:
        pass
    src = os.path.join(d, 'source.mp4')
    f = ''.join(f'[0:v]trim={a}:{b},setpts=PTS-STARTPTS,fps={FPS}[v{k}];[0:a]atrim={a}:{b},asetpts=PTS-STARTPTS,'
                f'afade=t=in:d=0.015,afade=t=out:st={max(0, b - a - .015):.3f}:d=0.015[a{k}];' for k, (a, b) in enumerate(segs))
    f += ''.join(f'[v{k}][a{k}]' for k in range(len(segs))) + f'concat=n={len(segs)}:v=1:a=1[v][a]'
    tmp = os.path.join(d, '_cut.mov')
    sc.run(sc.FF(), '-v', 'error', '-y', '-i', src, '-filter_complex', f, '-map', '[v]', '-map', '[a]',
           '-c:v', 'libx264', '-preset', 'fast', '-crf', '15', '-g', '15', '-pix_fmt', 'yuv420p', '-c:a', 'pcm_s16le', tmp)
    os.replace(tmp, out)
    sc.jdump(segs, os.path.join(d, '_cut.json'))
    for x in glob.glob(os.path.join(d, '_track.json')):
        os.remove(x)
    return out


# ---------------------------------------------------------------- captions and text

def shown(word, look, censor):
    t = word.strip()
    if censor:
        core = re.sub(r'[^a-z]', '', t.lower())
        if core in SWEARS:
            t = re.sub(re.escape(core), SWEARS[core], t, flags=re.I)
    t = re.sub(r'[.,;:]+$', '', t) if look.get('case') == 'upper' else t
    if look.get('case') == 'upper':
        t = re.sub(r'(\d)S\b', r'\1s', t.upper())  # 45s, 90s: the s after a number stays small
    return t


def strip_emoji(s):
    return re.sub('[\U0001F000-\U0001FAFF☀-➿️‍]', '', s).strip()


def hook_pic(text, size=58, maxw=880, style='white'):
    """The title at the top. style: `white` (black words on a white box), `black` (white on a dark box) or `outline`
    (white bold italic words with a black outline and an emoji at the end, like the big clip pages)."""
    emo = re.findall('[\U0001F000-\U0001FAFF\u2600-\u27BF]', text) if style == 'outline' else []
    plain = strip_emoji(text)
    if style == 'outline':
        f = ImageFont.truetype(FX.font_file('poppins/poppins-v24-latin-800italic.ttf'), size)
    elif style == 'plate':  # the story-page plate: heavy black capitals on a white rounded box, under the captions
        f = ImageFont.truetype(font_file('inter/inter-v20-latin-900.ttf'), size)
        plain = plain.upper()
    else:
        f = ImageFont.truetype(font_file('montserrat/montserrat-v31-latin-900.ttf'), size)
    words = plain.split()
    lines = balanced(words, f, maxw)
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * 1.08)
    px, py = int(size * .55), int(size * .38)
    wmax = max(f.getlength(L) for L in lines)
    im = Image.new('RGBA', (int(wmax + 2 * px), int(lh * len(lines) + 2 * py)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if style == 'outline':
        st = max(5, size // 9)
        for k, L in enumerate(lines):
            d.text(((im.width - f.getlength(L)) / 2, py + k * lh), L, font=f, fill=(255, 255, 255, 255), stroke_width=st, stroke_fill=(0, 0, 0, 255))
        if emo:  # the emoji goes right after the last word, as big as a capital letter and a half
            ep = FX.emoji_pic(emo[0], int(size * 1.5))
            if ep is not None:
                lastw = f.getlength(lines[-1])
                x0 = int((im.width + lastw) / 2 + size * .2)
                big = Image.new('RGBA', (max(im.width, x0 + ep.width) + px, im.height + int(size * .3)), (0, 0, 0, 0))
                off = (big.width - im.width) // 2 if x0 + ep.width <= im.width else 0
                big.alpha_composite(im, (off, 0))
                big.alpha_composite(ep, (x0 + off, int(py + (len(lines) - 1) * lh + lh / 2 - ep.height / 2)))
                im = big
        return im
    bg, fg = ((255, 255, 255, 255), (0, 0, 0, 255)) if style in ('white', 'plate') else ((0, 0, 0, 230), (255, 255, 255, 255))
    d.rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=int(size * .35), fill=bg)
    for k, L in enumerate(lines):
        d.text(((im.width - f.getlength(L)) / 2, py + k * lh), L, font=f, fill=fg)
    return im


def balanced(words, f, maxw):
    """Fewest lines that fit, with the words shared out evenly (no single word left alone on the last line)."""
    total = f.getlength(' '.join(words))
    for n in range(1, len(words) + 1):
        target = total / n
        lines, cur = [], []
        for w in words:
            if cur and f.getlength(' '.join(cur + [w])) > target * 1.12 and len(lines) < n - 1:
                lines.append(' '.join(cur)); cur = []
            cur.append(w)
        lines.append(' '.join(cur))
        if all(f.getlength(L) <= maxw for L in lines):
            return lines
    return [' '.join(words)]


def credit_pic(text, size=34):
    f = ImageFont.truetype(font_file('montserrat/montserrat-v31-latin-800.ttf'), size)
    text = strip_emoji(text)
    w = int(f.getlength(text) + size * 1.1)
    im = Image.new('RGBA', (w, int(size * 1.7)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=im.height // 2, fill=(0, 0, 0, 150))
    d.text((size * .55, size * .3), text, font=f, fill=(255, 255, 255, 235))
    return im


def paste(frame, im, cx, cy, scale=1.0):
    if scale != 1.0:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BILINEAR)
    a = np.array(im)[..., [2, 1, 0, 3]]
    h, w = a.shape[:2]
    x0, y0 = int(round(cx - w / 2)), int(round(cy - h / 2))
    fx0, fy0 = max(0, x0), max(0, y0)
    fx1, fy1 = min(frame.shape[1], x0 + w), min(frame.shape[0], y0 + h)
    if fx1 <= fx0 or fy1 <= fy0:
        return
    sub = a[fy0 - y0: fy1 - y0, fx0 - x0: fx1 - x0].astype(np.float32)
    al = sub[..., 3:4] / 255
    reg = frame[fy0:fy1, fx0:fx1].astype(np.float32)
    frame[fy0:fy1, fx0:fx1] = (reg * (1 - al) + sub[..., :3] * al).astype(np.uint8)


def pop_scale(k):
    """Caption entrance: a quick pop (80% -> 108% -> 100% over 4 frames)."""
    return (.8, .96, 1.08, 1.03)[k] if k < 4 else 1.0


# ---------------------------------------------------------------- layouts

def crop_to(img, x, y, w, h, ow, oh):
    """The (x, y, w, h) part of img, scaled to ow x oh (cover: the part is trimmed to the right shape around its centre)."""
    ar = ow / oh
    if w / h > ar:
        nw = h * ar; x += (w - nw) / 2; w = nw
    else:
        nh = w / ar; y += (h - nh) / 2; h = nh
    sh_, sw_ = img.shape[:2]
    x, y = min(max(0, x), max(0, sw_ - w)), min(max(0, y), max(0, sh_ - h))
    k = ow / w
    M = np.float32([[k, 0, -x * k], [0, k, -y * k]])
    return cv2.warpAffine(img, M, (ow, oh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def face_path(cut, n, sw, sh, starts=()):
    """For the full-screen layout: where the face is, smoothed like a slow camera operator (it only moves when the
    face drifts out of the middle, then glides). At every cut (the clip's own joins and the shot changes inside the
    footage) the window jumps straight to the new face instead of panning across."""
    cap = cv2.VideoCapture(cut)
    small = 480
    det = sc.face_detector(small, int(small * sh / sw), score=.6)
    raw, cuts = {}, {0}
    cuts.update(min(n - 1, int(round(t * FPS))) for t in starts)
    prev = None
    i = 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        th = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (48, 27)).astype(np.float32)
        if prev is not None and float(np.mean(np.abs(th - prev))) > 38:
            cuts.add(i)
        prev = th
        if i % 5 == 0 or i in cuts:
            _, f = det.detect(cv2.resize(img, (small, int(small * sh / sw))))
            if f is not None and len(f):
                x, y, w, h = max(f[:, :4].tolist(), key=lambda r: r[2] * r[3])
                raw[i] = ((x + w / 2) / small * sw, (y + h * .4) / small * sw, w / small * sw)
        i += 1
    cap.release()
    fws = [w for k, (_, _, w) in raw.items() if k < n]
    if not fws:
        return np.full(n, sw / 2), np.full(n, sh * .4), None
    bounds = sorted(c for c in cuts if c < n) + [n]
    out_x, out_y = np.empty(n), np.empty(n)
    lastx, lasty = sw / 2, sh * .4
    for a, b in zip(bounds, bounds[1:]):
        ks = [k for k in raw if a <= k < b]
        idx = np.arange(a, b)
        if ks:
            xs = np.interp(idx, ks, [raw[k][0] for k in ks])
            ys = np.interp(idx, ks, [raw[k][1] for k in ks])
        else:  # no face in this shot: hold the middle of the picture
            xs, ys = np.full(b - a, sw / 2), np.full(b - a, lasty)
        cx, cy = xs[0], ys[0]
        for j in range(b - a):  # dead zone + glide, inside this shot only
            if abs(xs[j] - cx) > sw * .06:
                cx += (xs[j] - cx) * .06
            if abs(ys[j] - cy) > sh * .06:
                cy += (ys[j] - cy) * .06
            out_x[a + j], out_y[a + j] = cx, cy
        lastx, lasty = cx, cy
    return out_x, out_y, float(np.median(fws))


def sticker_pic(src, at, width, box=None, tilt=0):
    """A photo card cut from the footage (or an image file): white border, rounded corners, a slight tilt.
    For pop-ins: the car he asked for, the dad who is paying, the thing they are talking about."""
    if isinstance(at, str) and os.path.exists(os.path.expanduser(at)):
        img = cv2.imread(os.path.expanduser(at))
    else:
        cap = cv2.VideoCapture(src)
        cap.set(cv2.CAP_PROP_POS_MSEC, float(at) * 1000)
        ok, img = cap.read()
        cap.release()
        if not ok:
            return None
    if box:
        x, y, w, h = [int(v) for v in box]
        img = img[max(0, y):y + h, max(0, x):x + w]
    h0, w0 = img.shape[:2]
    bw = max(8, width // 40)
    inner = Image.fromarray(cv2.cvtColor(cv2.resize(img, (width - 2 * bw, int((width - 2 * bw) * h0 / w0)), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)).convert('RGBA')
    r = width // 18
    card = Image.new('RGBA', (width, inner.height + 2 * bw), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle([0, 0, card.width - 1, card.height - 1], radius=r, fill=(255, 255, 255, 255))
    m = Image.new('L', inner.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, inner.width - 1, inner.height - 1], radius=max(2, r - bw), fill=255)
    card.paste(inner, (bw, bw), m)
    if tilt:
        card = card.rotate(float(tilt), resample=Image.BICUBIC, expand=True)
    return card


def blur_bg(img):
    bg = crop_to(img, 0, 0, img.shape[1], img.shape[0], 216, 384)
    bg = cv2.GaussianBlur(bg, (0, 0), 9)
    bg = (cv2.resize(bg, (W, H)) * .55).astype(np.uint8)
    return bg


# ---------------------------------------------------------------- render

def cmd_render(a, d=None, still=None):
    d = d or clip_dir(a.name)
    p = load(d)
    if not os.path.exists(os.path.join(d, 'words.json')):
        cmd_prep(a, d)
    words = sc.jload(os.path.join(d, 'words.json'))['words']
    lay = sc.jload(os.path.join(d, 'layout.json'))
    spell = {int(str(k).lstrip('w')): v for k, v in (p.get('spell') or {}).items()}
    words = [dict(w, w=spell[w['i']]) if w['i'] in spell else w for w in words]
    added = {}  # lines the speech reader missed (a quiet phone call, someone off camera): {"text", "at", "until"} in source seconds
    for k_, aw in enumerate(p.get('add_words') or []):
        toks = aw['text'].split()
        a_, b_ = secs(aw['at']), secs(aw.get('until', secs(aw['at']) + .32 * len(toks)))
        L = sum(len(x) + 2 for x in toks); c_ = a_
        for j, tk in enumerate(toks):
            dur = (b_ - a_) * (len(tk) + 2) / L
            wi = 100000 + k_ * 100 + j
            words.append(dict(i=wi, w=tk, s=round(c_, 3), e=round(c_ + dur * .9, 3)))
            if aw.get('color'):
                added[wi] = aw['color']
            c_ += dur
    words.sort(key=lambda w: w['s'])
    segs, drop = plan_cut(p, words, p['seconds'])
    owords, total, starts = remap(words, segs, drop)
    owords = [w for w in owords if w['w'].strip()]
    t_of = lambda x: (lambda m: (min(owords, key=lambda w: abs(w['i'] - int(m.group(1))))[('e' if m.group(2) else 's')]) if m else float(x))(
        re.fullmatch(r'w(\d+)(e?)', str(x).strip()))
    if still is not None:
        still = min(max(0.0, t_of(still)), max(0.0, total - 1 / FPS))
    if still is None:
        sc.log(f'Rendering a {total:.1f} s clip. About {sc.human_time(sc.estimate("render", total))}.')
    t0 = time.time()
    cut = cut_for(d, segs)
    n = int(round(total * FPS))
    sw, sh = lay['size']
    kind = p.get('layout') if p.get('layout') not in (None, 'auto') else lay['kind']
    cam = p.get('cam') or lay.get('cam')
    if kind == 'stack' and not cam:
        kind = 'full'
    look = load_look(p.get('captions') or 'comic') if p.get('captions') != 'none' else None
    if look and isinstance(p.get('caption_style'), dict):
        look.update(p['caption_style'])
    loud = FX.word_loudness(cut, owords)
    chosen = None
    if p.get('colors'):  # Claude's own pick of key words: {"w12": "yellow", "w30": null}
        chosen = {}
        for k_, v_ in p['colors'].items():
            m_ = re.fullmatch(r'w?(\d+)(?:-(\d+))?', str(k_).strip())
            if m_:
                for wi in range(int(m_.group(1)), int(m_.group(2) or m_.group(1)) + 1):
                    chosen[wi] = v_
    if added:
        chosen = {**(chosen or {}), **added}
    keys = FX.keywords(owords, loud, chosen) if look and (chosen or look.get('auto_keys', True)) else {}
    pics = FX.Pics(look) if look else None
    track = FX.track(owords, look, SWEARS if p.get('censor', True) else None, total, keys, loud) if look else []
    tags = []  # *SOUND* tags shown in place of the captions: *FALLS*, *AURA*, *DOOR SLAMS*
    for tg in p.get('tags') or []:
        s_ = t_of(tg.get('at', 0))
        e_ = t_of(tg['until']) if tg.get('until') is not None else s_ + float(tg.get('for', 1.0))
        txt = tg['text'] if tg['text'].startswith('*') else f"*{tg['text'].strip('*')}*"
        tags.append(dict(s=s_, e=min(e_, total), first=s_, loud=.5, toks=[(txt.upper() if look and look.get('case') == 'upper' else txt, tg.get('color', 'yellow'))]))
    if tags:
        track = [c for c in track if not any(tg['s'] - .05 <= c['s'] < tg['e'] for tg in tags)] + tags
        track.sort(key=lambda c: c['s'])
    emojis = []
    for em in p.get('emoji') or []:
        pic = FX.emoji_pic(em['e'], int(em.get('size', 150)))
        if pic is not None:
            s_ = t_of(em.get('at', 0))
            emojis.append((s_, s_ + float(em.get('for', 1.2)), pic, em.get('y')))
    stickers = []  # photo cards that pop in: [{"at": "w12", "for": 2, "src": 41.5, "box": [x, y, w, h], "x": 300, "y": 700, "w": 460, "tilt": -6}]
    for st in p.get('stickers') or []:
        pic = sticker_pic(os.path.join(d, 'source.mp4'), st.get('src', 0), int(st.get('w', 460)), st.get('box'), st.get('tilt', 0))
        if pic is not None:
            s_ = t_of(st.get('at', 0))
            stickers.append((s_, t_of(st['until']) if st.get('until') is not None else s_ + float(st.get('for', 2.0)), pic,
                             float(st.get('x', W / 2)), float(st.get('y', 700))))
    # punch-ins: the camera snaps closer on the big moments (auto on the loudest ones, plus Claude's own)
    punches, hits = [], []
    fx_on = look is not None and look.get('anim') and p.get('effects', True)
    if fx_on and p.get('auto_punch', True):
        for t_, st_ in FX.loud_moments(cut, total, top=max(1, int(total / 7))):
            big = st_ > .93
            punches.append(dict(s=max(0, t_ - .1), e=t_ + .9, zoom=1.22 if big else 1.14, shake=16 if big else 0))
            if big:
                hits.append((max(0, t_ - .1), 'boom', .55))
    for pu in p.get('punch') or []:
        s_ = t_of(pu.get('at', 0))
        punches.append(dict(s=s_, e=s_ + float(pu.get('for', .9)), zoom=float(pu.get('zoom', 1.2)),
                            shake=16 if pu.get('shake') else 0, flash=bool(pu.get('flash'))))
        if pu.get('sound'):
            hits.append((s_, pu['sound'], float(pu.get('volume', .55))))
    if fx_on and p.get('auto_sounds', True):
        hits += [(tg['s'], 'pop', .35) for tg in tags] + [(x[0], 'pop', .3) for x in stickers]
    for sx in p.get('sounds') or []:
        hits.append((t_of(sx.get('at', 0)), sx['sound'], float(sx.get('volume', .5))))

    # geometry of each layout
    cam_h = int(H * float(p.get('cam_share', .42)))
    gz = float(p.get('game_zoom', 1.0))
    gx = float(p.get('game_x', .5))
    if kind == 'stack':
        cap_y = int(p.get('caption_y') or cam_h)  # on the seam between facecam and gameplay
    elif kind == 'game':
        cap_y = int(p.get('caption_y') or 1330)
    else:
        cap_y = int(p.get('caption_y') or 1250)
    fx = fy = None
    if kind == 'full':
        fj = os.path.join(d, '_track.json')
        if os.path.exists(fj):
            T = sc.jload(fj); fx, fy, ffw = np.array(T['x']), np.array(T['y']), T['fw']
        else:
            fx, fy, ffw = face_path(cut, n, sw, sh, starts)
            sc.jdump(dict(x=fx.tolist(), y=fy.tolist(), fw=ffw), fj)
        zoom = float(p.get('zoom', 1.0))
        full_w = min(sw, sh * W / H)
        crop_w = full_w / max(1.0, zoom)
        crop_h = crop_w * H / W

    hook = p.get('hook') or {}
    hook_img = hook_pic(hook['text'], size=int(hook.get('size', 56)), style=hook.get('style', 'white'),
                        maxw=980 if hook.get('style') == 'plate' else 880) if hook.get('text') else None
    hook_until = total if str(hook.get('until', 'end')) == 'end' else t_of(hook.get('until'))
    hook_y = int(hook.get('y') or (290 if kind != 'stack' else 250))
    if hook_img is not None and kind == 'stack' and not hook.get('y'):
        # keep the title off the streamer's face: the face sits in the facecam panel
        fc = lay.get('face')
        if fc and cam:
            cx_, cy_, cw_, ch_ = cam
            ar = W / cam_h
            if cw_ / ch_ > ar:
                vis_h = ch_; vis_y = cy_
            else:
                vis_h = cw_ / ar; vis_y = cy_ + (ch_ - vis_h) / 2
            face_top = (fc[1] - vis_y) / vis_h * cam_h
            if face_top < hook_y + hook_img.height / 2 + 10:
                hook_y = max(hook_img.height // 2 + 150, int(face_top - hook_img.height / 2 - 14))
                if hook_y - hook_img.height / 2 < 140:  # no room above the face: put it on the gameplay instead
                    hook_y = cam_h + 60 + hook_img.height // 2 + (110 if look else 0)
    if hook_img is not None and kind == 'full' and not hook.get('y') and fx is not None:
        # where the face sits on screen while the title shows; if the title would cover it, it goes under the chin
        sc_ = W / crop_w
        ks = range(0, min(n, int(hook_until * FPS) + 1), 15)
        fh_out = (ffw or sw * .08) * 1.3 * sc_
        tops, bots = [], []
        for k in ks:
            cy0 = min(max(0, fy[k] - crop_h * .36), max(0, sh - crop_h))
            yy = (fy[k] - cy0) * sc_
            tops.append(yy - fh_out * .55); bots.append(yy + fh_out * .75)
        if tops:
            ft, fb = float(np.median(tops)), float(np.median(bots))
            ht, hb = hook_y - hook_img.height / 2, hook_y + hook_img.height / 2
            if hb > ft and ht < fb:
                hook_y = int(fb + 40 + hook_img.height / 2)
                if hook_y + hook_img.height / 2 > cap_y - 120:  # no room under the face either: back on top
                    hook_y = int(hook.get('y') or 290)
    notes = []  # context lines the clipper adds ("He has been awake for 31 hours"): the clip's own value, not a repost
    for nt in p.get('notes') or []:
        img_ = hook_pic(nt['text'], size=int(nt.get('size', 44)), maxw=860, style=nt.get('style', 'black'))
        s_ = t_of(nt.get('at', 0))
        e_ = t_of(nt['until']) if nt.get('until') is not None else s_ + max(1.8, len(nt['text'].split()) * .38)
        y_ = int(nt.get('y') or (cam_h + 140 if kind == 'stack' else 520))
        notes.append((s_, e_, y_, img_))
    credit = p.get('credit')
    credit_img = credit_pic(credit) if credit else None

    frames = [int(round(still * FPS))] if still is not None else range(n)
    out = os.path.join(sc.conf()['work'], 'finished', f"{p['name']}.mp4") if still is None else os.path.join(d, f'still_{still:.2f}.jpg')
    vid = os.path.join(d, '_video.mp4')
    enc = None
    if still is None:
        enc = subprocess.Popen([sc.FF(), '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                                '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-pix_fmt', 'yuv420p', vid], stdin=subprocess.PIPE)
    src = cv2.VideoCapture(cut)
    for i in frames:
        t = i / FPS
        if still is not None:
            src.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, img = src.read()
        if not ok:
            img = np.zeros((sh, sw, 3), np.uint8)
        if img.shape[1] != sw or img.shape[0] != sh:
            img = cv2.resize(img, (sw, sh))
        if kind == 'stack':
            frame = np.zeros((H, W, 3), np.uint8)
            x, y, w_, h_ = cam
            frame[:cam_h] = crop_to(img, x, y, w_, h_, W, cam_h)
            gh = H - cam_h
            vw = sh * W / gh / gz
            vh = sh / gz
            frame[cam_h:] = crop_to(img, gx * sw - vw / 2, (sh - vh) / 2, vw, vh, W, gh)
            frame[cam_h - 3: cam_h + 3] = 0
        elif kind == 'full':
            k = min(i, n - 1)
            frame = crop_to(img, fx[k] - crop_w / 2, fy[k] - crop_h * .36, crop_w, crop_h, W, H)
        else:  # game: the whole picture across the middle, a blurred copy behind
            frame = blur_bg(img)
            gw = W
            gh_ = int(round(gw * sh / sw))
            vw = sw / gz
            fit = crop_to(img, gx * sw - vw / 2, (sh - sh / gz) / 2, vw, sh / gz, gw, gh_)
            y0 = int(p.get('game_y', 960)) - gh_ // 2
            frame[y0:y0 + gh_] = fit
        if punches:
            z_, dx_, dy_ = FX.punch_at(punches, t)
            if z_ > 1.001 or dx_ or dy_:
                region = frame[:cam_h] if kind == 'stack' else frame
                FX.apply_zoom(region, z_, dx_, dy_, cy=.45 if kind == 'stack' else .38)
            for pu in punches:
                if pu.get('flash') and pu['s'] <= t < pu['s'] + .15:
                    FX.flash(frame, int((t - pu['s']) * FPS))
        for bl in p.get('blur') or []:  # hide burned-in text from the original (its own subtitles, a watermark)
            if t_of(bl.get('from', 0)) <= t < t_of(bl.get('until', total)):
                bx, by, bw_, bh_ = [int(v) for v in bl['box']]
                reg = frame[by:by + bh_, bx:bx + bw_]
                if reg.size:
                    frame[by:by + bh_, bx:bx + bw_] = cv2.GaussianBlur(reg, (0, 0), 18)
        if credit_img is not None and not (hook_img is not None and t < hook_until and hook_y + hook_img.height / 2 > H - 470):
            paste(frame, credit_img, 50 + credit_img.width / 2, H - 430)  # low on the left, clear of captions and the apps' buttons
        for s_, e_, y_, img_ in notes:
            if s_ <= t < e_:
                paste(frame, img_, W / 2, y_, pop_scale(int(round((t - s_) * FPS))))
        for s_, e_, pic, x_, y_ in stickers:
            if s_ <= t < e_:
                k = int(round((t - s_) * FPS))
                paste(frame, pic, x_, y_, (.4, .75, 1.08, 1.02)[k] if k < 4 else 1.0)
        if hook_img is not None and t < hook_until:
            paste(frame, hook_img, W / 2, hook_y)
        ct = next((c for c in track if c['s'] <= t < c['e']), None)
        cw_now = 0
        if ct:
            im = pics.caption(ct['toks'])
            cw_now = im.width
            k = int(round((t - ct['first']) * FPS))
            paste(frame, im, W / 2, cap_y, FX.anim_scale(look, k, ct.get('loud', 0)))
        for s_, e_, pic, y_ in emojis:
            if s_ <= t < e_:
                k = int(round((t - s_) * FPS))
                # beside the caption (never on the face): to its right, tilted up a little
                ex = W / 2 + max(cw_now, 300) / 2 + pic.width / 2 + 10
                ey = y_ or (cap_y - 40)
                if ex > W - pic.width / 2 - 30:  # no room beside it: sit on the caption's top right corner
                    ex, ey = min(W - pic.width / 2 - 40, W / 2 + cw_now / 2 - pic.width * .3), y_ or (cap_y - 125)
                paste(frame, pic, ex, ey, (.5, .8, 1.12, 1.04)[k] if k < 4 else 1.0)
        if still is not None:
            sc.imwrite(out, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            print(out)
            return out
        try:
            enc.stdin.write(frame.tobytes())
        except (BrokenPipeError, OSError):
            raise SystemExit('RENDER_STOPPED: the video writer stopped (often a full disk). Check free space and render again.')
        if i and i % 450 == 0:
            done = i / n
            sc.log(f'  {int(done * 100)}% done, {sc.human_time((time.time() - t0) / done * (1 - done))} left')
    enc.stdin.close(); enc.wait()
    src.release()
    aud = os.path.join(d, '_mix.wav')
    sc.run(sc.FF(), '-v', 'error', '-y', '-i', cut, '-vn', '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', '-ar', '48000', '-ac', '2', aud)
    if hits:
        FX.mix_sfx(aud, aud, hits)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sc.run(sc.FF(), '-v', 'error', '-y', '-i', vid, '-i', aud, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
           '-shortest', '-movflags', '+faststart', out)
    os.remove(vid); os.remove(aud)
    sc.learn('render', total, time.time() - t0)
    p['last_render'] = dict(file=out, seconds=round(total, 2), layout=kind, at=time.strftime('%Y-%m-%d %H:%M'))
    save(d, p)
    sc.jdump(dict(words=owords, captions=[dict(s=c['s'], e=c['e'], text=' '.join(t for t, _ in c['toks'])) for c in track],
                    punches=[dict(s=round(x['s'], 2), zoom=x['zoom'], shake=bool(x['shake'])) for x in punches]),
             os.path.join(d, 'edit_map.json'))
    sc.log(f'Finished in {sc.human_time(time.time() - t0)}: {out}')
    print(out)
    return out


def load_look(name):
    """A built-in caption look, or one saved from a reference clip in ~/Stream Clips/styles/<name>.json."""
    if name in CAPTION_LOOKS:
        return dict(CAPTION_LOOKS[name])
    f = os.path.join(sc.conf()['work'], 'styles', f'{name}.json')
    if os.path.exists(f):
        lk = dict(CAPTION_LOOKS.get(sc.jload(f).get('base', 'comic'), CAPTION_LOOKS['comic']))
        lk.update({k: v for k, v in sc.jload(f).items() if k not in ('base', 'from', 'notes')})
        return lk
    sc.log(f'WARNING: no caption look called {name!r}; using comic.')
    return dict(CAPTION_LOOKS['comic'])


def cmd_ref(a):
    """Study a reference clip the user likes: frames every half second (first 20 s) on one sheet, plus single frames."""
    out = os.path.join(sc.conf()['work'], 'styles', re.sub(r'[^\w -]', '', a.name).strip() or 'reference')
    os.makedirs(out, exist_ok=True)
    src = a.src
    if not os.path.exists(src):
        sc.log('Downloading the reference (first 40 s)...')
        dst = os.path.join(out, 'reference.mp4')
        subprocess.run([sc.VPY(), '-m', 'yt_dlp', '-q', '--no-warnings', '-f', 'bv*[height<=1080]+ba/b[height<=1080]/b',
                        '--download-sections', '*0-40', '--merge-output-format', 'mp4', '-o', dst, *sc.cookie_args(), src], timeout=600)
        if not os.path.exists(dst):
            raise SystemExit('DOWNLOAD_FAILED: could not get that link. Ask the user to save the video and give the file instead.')
        src = dst
    fdir = os.path.join(out, 'frames')
    os.makedirs(fdir, exist_ok=True)
    sc.run(sc.FF(), '-v', 'error', '-y', '-t', '20', '-i', src, '-vf', 'fps=2,scale=540:-2', os.path.join(fdir, 'f_%03d.jpg'))
    fr = sorted(glob.glob(os.path.join(fdir, 'f_*.jpg')))[:40]
    if fr:
        th = [Image.open(f).convert('RGB') for f in fr]
        tw, thh = 240, int(240 * th[0].height / th[0].width)
        cols = 8
        sheet_im = Image.new('RGB', (cols * tw, ((len(th) + cols - 1) // cols) * thh), (0, 0, 0))
        dr = ImageDraw.Draw(sheet_im)
        lab = ImageFont.truetype(font_file('inter/inter-v20-latin-700.ttf'), 18)
        for k, im_ in enumerate(th):
            x_, y_ = (k % cols) * tw, (k // cols) * thh
            sheet_im.paste(im_.resize((tw, thh)), (x_, y_))
            dr.rectangle([x_, y_, x_ + 52, y_ + 24], fill=(0, 0, 0))
            dr.text((x_ + 5, y_ + 2), f'{k / 2:.1f}s', font=lab, fill=(255, 255, 255))
        sheet_im.save(os.path.join(out, 'sheet.jpg'), quality=85)
    sheet, fs = FX.font_sheet(os.path.join(out, 'fonts.jpg'))
    print(f'Reference sheet: {os.path.join(out, "sheet.jpg")}\nSingle frames: {fdir}\nFont samples (numbered): {sheet}\n'
          f'Write the look to {out}.json (see references/STYLES.md), then use "captions": "{os.path.basename(out)}".')


def cmd_fonts(a):
    out, fs = FX.font_sheet(os.path.join(sc.conf()['work'], 'styles', 'fonts.jpg'))
    for k, f in enumerate(fs):
        print(f'{k + 1}. {os.path.relpath(f, FX.FONTS) if f.startswith(FX.FONTS) else f}')
    print(out)


def cmd_still(a):
    cmd_render(a, clip_dir(a.name), still=a.at)


def cmd_batch(a):
    ds = [clip_dir(x) for x in a.names]
    sc.log(f'{len(ds)} clips. About {sc.human_time(sum(sc.estimate("render", load(d)["seconds"]) for d in ds))} in all.')
    done = []
    for k, d in enumerate(ds):
        sc.log(f'--- Clip {k + 1} of {len(ds)}: {os.path.basename(d)}')
        if not os.path.exists(os.path.join(d, 'words.json')):
            cmd_prep(a, d)
        done.append(cmd_render(a, d))
    sc.log('All done:\n' + '\n'.join(done))


def cmd_auto(a):
    """One command, a folder of finished clips: scan a stream (or reuse a scan folder), take the top chat spikes, cut each
    from a bit before the moment (chat reacts 5 to 20 s late) to just after, and render them with captions.
    These are first drafts with no title hook: Claude then watches them, keeps the best, adds hooks and re-renders."""
    src = a.src
    if os.path.isdir(src) and os.path.exists(os.path.join(src, 'scan.json')):
        folder = src
    else:
        sc.log('Step 1: finding the moments (chat spikes, viewer clips, most-replayed)...')
        cmd = [sc.VPY(), os.path.join(HERE, 'find.py'), 'scan', src, '--top', str(max(12, a.top * 2))]
        if a.start:
            cmd += ['--from', a.start]
        if a.end:
            cmd += ['--to', a.end]
        if a.want:
            cmd += ['--want', a.want]
        r = subprocess.run(cmd, capture_output=True, text=True)
        m = re.search(r'Saved: (.+)', r.stdout or '')
        if not m:
            raise SystemExit('The scan did not work:\n' + ((r.stdout or '') + (r.stderr or ''))[-1500:])
        folder = m.group(1).strip()
    res = sc.jload(os.path.join(folder, 'scan.json'))
    info = res['info']
    url = info.get('url') or src
    streamer = info.get('streamer') or ''
    picks, used = [], []
    for c in sorted(res['candidates'], key=lambda c: -c.get('score', 0)):
        if all(abs(c['at'] - u) > 75 for u in used):
            picks.append(c); used.append(c['at'])
        if len(picks) >= a.top:
            break
    if not picks:
        raise SystemExit('No strong moments in that stream. Try another part (--from/--to) or another stream.')
    sc.log(f'Step 2: making {len(picks)} clips (about {sc.human_time(len(picks) * (60 + sc.estimate("render", a.before + a.after)))}).')
    made = []
    for k, c in enumerate(picks):
        t0, t1 = max(0, c['at'] - a.before), c['at'] + a.after
        name = f"auto {re.sub(r'[^A-Za-z0-9 ]', '', streamer)[:20]} {int(c['at']) // 3600}-{int(c['at']) % 3600 // 60:02d}-{int(c['at']) % 60:02d}".strip()
        sc.log(f'--- Clip {k + 1} of {len(picks)}: {int(c["at"]) // 3600}:{int(c["at"]) % 3600 // 60:02d}:{int(c["at"]) % 60:02d} ({c.get("mood") or "mixed"}, {", ".join(c.get("sources", []))})')
        r = subprocess.run([sc.VPY(), os.path.join(HERE, 'clip.py'), 'new', name, '--src', url, '--from', f'{t0:.1f}', '--to', f'{t1:.1f}',
                            '--streamer', streamer], capture_output=True, text=True)
        d = (r.stdout or '').strip().splitlines()[-1] if r.returncode == 0 and (r.stdout or '').strip() else None
        if not d or not os.path.isdir(d):
            sc.log('    could not download that moment, skipped'); continue
        p = load(d)
        p['captions'] = a.look
        p['credit'] = None
        save(d, p)
        try:
            cmd_prep(a, d)
            out = cmd_render(a, d)
        except SystemExit as e:
            sc.log(f'    skipped: {e}'); continue
        made.append((c, d, out))
    lst = os.path.join(folder, 'auto-clips.md')
    with open(lst, 'w') as fh:
        fh.write(f"# Auto clips: {info.get('title')}\n\nDrafts with captions and no title hook. Keep the good ones, add a hook "
                 "(references/HOOKS.md), tighten `keep`, and render again.\n\n")
        for c, d, out in made:
            fh.write(f"- **{int(c['at']) // 3600}:{int(c['at']) % 3600 // 60:02d}:{int(c['at']) % 60:02d}** · {c.get('mood') or 'mixed'} · chat: {' | '.join((c.get('chat') or [])[:8])} · "
                     f"folder `{os.path.basename(d)}` · file `{out}`\n")
    sc.log(f'Done: {len(made)} clips in {os.path.join(sc.conf()["work"], "finished")}. List: {lst}')
    print(lst)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('new'); s.add_argument('name'); s.add_argument('--src', required=True)
    s.add_argument('--from', dest='start'); s.add_argument('--to', dest='end'); s.add_argument('--streamer')
    s.add_argument('--parts', help='a story clip: several moments joined, like "0:05-0:10,0:31-0:41,6:03-6:07"')
    s = sub.add_parser('prep'); s.add_argument('name')
    s = sub.add_parser('render'); s.add_argument('name')
    s = sub.add_parser('still'); s.add_argument('name'); s.add_argument('at')
    s = sub.add_parser('batch'); s.add_argument('names', nargs='+')
    s = sub.add_parser('auto'); s.add_argument('src'); s.add_argument('--top', type=int, default=6)
    s.add_argument('--from', dest='start'); s.add_argument('--to', dest='end'); s.add_argument('--want')
    s.add_argument('--look', default='comic'); s.add_argument('--before', type=float, default=25); s.add_argument('--after', type=float, default=12)
    s = sub.add_parser('ref'); s.add_argument('name'); s.add_argument('--src', required=True)
    s = sub.add_parser('fonts')
    a = ap.parse_args()
    dict(new=cmd_new, prep=cmd_prep, render=cmd_render, still=cmd_still, batch=cmd_batch, auto=cmd_auto, ref=cmd_ref, fonts=cmd_fonts)[a.cmd](a)


if __name__ == '__main__':
    main()
