"""Live mode: watch a stream WHILE it is live and catch the moments as they happen.

  live.py watch <twitch or kick channel or link> [--hours 4] [--keep 12] [--sens 1.0] [--max 30]

What it does, all with free tools and no logins:
  1. Records the live stream into a short rolling buffer (10-second pieces, only the last --keep minutes are kept,
     so it never fills the disk).
  2. Reads the live chat anonymously (Twitch: read-only chat login, no account or token; Kick: its public chat feed).
  3. Every 10 seconds it counts the messages and the reaction words (LMAO, skulls, "NO WAY", W/L spam...).
     When chat jumps far above its normal speed, that is a moment.
  4. Chat reacts 5 to 20 s AFTER the moment, so it cuts from 35 s before the spike to 10 s after it, saves that as a
     clip folder (clip.py new), and writes the transcript and layout (clip.py prep) straight away.
  5. Every moment is added to ~/Stream Clips/live/<channel>/moments.md (time, what chat said, the mood, the
     clip folder) so Claude can finish the best ones (hook, look, render) within minutes.

It only works while they are live (it cannot rewind). For a stream that already ended, use find.py scan.
Stop it any time with Ctrl+C (or by stopping the background task); it cleans up its buffer.
"""
import argparse, collections, glob, json, os, re, shutil, socket, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sc  # noqa: E402
import find  # noqa: E402

REACT = re.compile(r"(?i)\b(lmao+|lmfao+|lol+|kek(w)?|omegalul|icant|xd+|haha+|no+ ?way|wtf+|what+|holy|bro+|ayo+|w+|l+|"
                   r"oh my god|omg|clip (it|that)|clipped|insane|crazy|nah+|deadass)\b|💀|😭|😂|🤣|😱|🔥|‼|❗")
SEG = 10  # seconds per recorded piece


def say(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


# ---------------------------------------------------------------- which channel

def resolve(target):
    t = target.strip()
    m = re.search(r'kick\.com/([A-Za-z0-9_-]+)', t)
    if m:
        return 'kick', m.group(1).lower()
    m = re.search(r'twitch\.tv/([A-Za-z0-9_]+)', t)
    if m:
        return 'twitch', m.group(1).lower()
    if re.fullmatch(r'[A-Za-z0-9_-]+', t):
        try:
            plat, _, ident = find.parse(t)
            if plat in ('twitch', 'kick'):
                return plat, ident.lower()
        except SystemExit:
            pass
        return 'twitch', t.lower()
    raise SystemExit('Live mode works with Twitch and Kick channels (a name or a link). For YouTube, use find.py scan '
                     'on the live link now and then.')


def stream_url(plat, name):
    """The live video address (HLS), 720p or lower to keep the buffer small. None if they are offline."""
    page = f'https://www.twitch.tv/{name}' if plat == 'twitch' else f'https://kick.com/{name}'
    r = subprocess.run([sc.VPY(), '-m', 'yt_dlp', '-q', '--no-warnings', '-g', '-f', 'best[height<=720]/best', *sc.cookie_args(), page],
                       capture_output=True, text=True, timeout=90)
    u = (r.stdout or '').strip().splitlines()
    return u[0] if r.returncode == 0 and u else None


# ---------------------------------------------------------------- recording (rolling buffer)

class Recorder(threading.Thread):
    def __init__(self, plat, name, folder, keep_min):
        super().__init__(daemon=True)
        self.plat, self.name, self.folder, self.keep = plat, name, folder, keep_min * 60
        self.stop = threading.Event()
        self.proc = None
        self.ok = False

    def run(self):
        os.makedirs(self.folder, exist_ok=True)
        while not self.stop.is_set():
            url = stream_url(self.plat, self.name)
            if not url:
                self.ok = False
                say('They are not live right now (or the stream could not be opened). Checking again in 60 s...')
                self.stop.wait(60)
                continue
            self.ok = True
            pat = os.path.join(self.folder, 'seg_%s.ts')  # the piece's start time (unix seconds) is in its name
            # the stream's own timestamps: arrival-time stamps (-use_wallclock_as_timestamps) bunch frames into bursts,
            # because HLS arrives a few seconds at a time, so the clips lag and drift out of sync with the sound
            self.proc = subprocess.Popen([sc.FF(), '-v', 'error', '-y', '-fflags', '+genpts', '-i', url, '-map', '0:v:0?', '-map', '0:a:0?', '-c', 'copy',
                                          '-f', 'segment', '-segment_time', str(SEG), '-reset_timestamps', '1', '-strftime', '1', pat],
                                         stdin=subprocess.DEVNULL)
            while self.proc.poll() is None and not self.stop.is_set():
                self.prune()
                self.stop.wait(5)
            if self.proc.poll() is None:
                self.proc.terminate()
            if not self.stop.is_set():
                say('The recording stopped (stream ended or a network hiccup). Reconnecting...')
                self.stop.wait(10)

    def prune(self):
        now = time.time()
        for f in glob.glob(os.path.join(self.folder, 'seg_*.ts')):
            try:
                if now - int(re.search(r'seg_(\d+)', f).group(1)) > self.keep:
                    os.remove(f)
            except (AttributeError, ValueError, OSError):
                pass

    def cut(self, t0, t1, out):
        """Join the pieces that cover wall-clock t0..t1 into one file, trimmed to exactly that window."""
        segs = []
        for f in sorted(glob.glob(os.path.join(self.folder, 'seg_*.ts'))):
            st = int(re.search(r'seg_(\d+)', f).group(1))
            if st + SEG + 2 >= t0 and st <= t1:
                segs.append((st, f))
        if not segs:
            return False
        lst = out + '.txt'
        with open(lst, 'w') as fh:
            fh.write(''.join(f"file '{f}'\n" for _, f in segs))
        first = segs[0][0]
        r = subprocess.run([sc.FF(), '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-ss', f'{max(0, t0 - first):.2f}',
                            '-t', f'{t1 - t0:.2f}', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17', '-c:a', 'aac', '-b:a', '160k', out],
                           capture_output=True)
        os.remove(lst)
        return r.returncode == 0 and os.path.exists(out)

    def close(self):
        self.stop.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


# ---------------------------------------------------------------- chat (anonymous)

class Chat(threading.Thread):
    def __init__(self, plat, name):
        super().__init__(daemon=True)
        self.plat, self.name = plat, name
        self.msgs = collections.deque(maxlen=20000)  # (wall time, text)
        self.stop = threading.Event()
        self.connected = False

    def run(self):
        while not self.stop.is_set():
            try:
                self.twitch() if self.plat == 'twitch' else self.kick()
            except Exception as e:  # network drop: reconnect
                self.connected = False
                say(f'Chat connection dropped ({type(e).__name__}); reconnecting...')
                self.stop.wait(5)

    def twitch(self):
        if os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy'):
            return self.twitch_ws()  # behind a web proxy (cloud sessions) a plain chat connection cannot get out
        s = socket.create_connection(('irc.chat.twitch.tv', 6667), timeout=30)
        s.sendall(b'NICK justinfan%d\r\n' % (int(time.time()) % 100000))  # Twitch's read-only anonymous login
        s.sendall(f'JOIN #{self.name}\r\n'.encode())
        buf = b''
        self.connected = True
        while not self.stop.is_set():
            try:
                data = s.recv(65536)
            except socket.timeout:
                s.sendall(b'PING :keepalive\r\n')
                continue
            if not data:
                raise ConnectionError('closed')
            buf += data
            *lines, buf = buf.split(b'\r\n')
            for ln in lines:
                line = ln.decode('utf-8', 'replace')
                if line.startswith('PING'):
                    s.sendall(('PONG' + line[4:] + '\r\n').encode())
                elif ' PRIVMSG ' in line:
                    self.msgs.append((time.time(), line.split(' :', 1)[-1] if ' :' in line else ''))

    def twitch_ws(self):
        """The same anonymous read-only chat, over Twitch's web chat connection (goes through HTTPS proxies)."""
        from curl_cffi.requests import Session
        ws = Session(impersonate='chrome').ws_connect('wss://irc-ws.chat.twitch.tv:443')
        ws.send_str('NICK justinfan%d' % (int(time.time()) % 100000))  # text frames: Twitch hangs up on binary ones
        ws.send_str(f'JOIN #{self.name}')
        self.connected = True
        while not self.stop.is_set():
            raw, _ = ws.recv()
            if not raw:
                continue
            for line in raw.decode('utf-8', 'replace').split('\r\n'):
                if line.startswith('PING'):
                    ws.send_str('PONG' + line[4:])
                elif ' PRIVMSG ' in line:
                    self.msgs.append((time.time(), line.split(' :', 1)[-1] if ' :' in line else ''))

    def kick(self):
        from curl_cffi.requests import Session
        info = find.get_json(f'https://kick.com/api/v2/channels/{self.name}') or {}
        room = (info.get('chatroom') or {}).get('id')
        if not room:
            raise ConnectionError('no chatroom id')
        ses = Session(impersonate='chrome')
        ws = ses.ws_connect('wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0&flash=false')
        ws.send(json.dumps({'event': 'pusher:subscribe', 'data': {'auth': '', 'channel': f'chatrooms.{room}.v2'}}).encode())
        self.connected = True
        while not self.stop.is_set():
            raw, _ = ws.recv()
            if not raw:
                continue
            try:
                ev = json.loads(raw)
            except ValueError:
                continue
            if ev.get('event') == 'pusher:ping':
                ws.send(json.dumps({'event': 'pusher:pong', 'data': {}}).encode())
            elif 'ChatMessage' in (ev.get('event') or ''):
                try:
                    self.msgs.append((time.time(), json.loads(ev['data']).get('content', '')))
                except (ValueError, TypeError, KeyError):
                    pass

    def window(self, t0, t1):
        return [x for t, x in list(self.msgs) if t0 <= t < t1]


# ---------------------------------------------------------------- spotting moments

def ad_share(path):
    """Share of a moment showing Twitch's ad screen (a smooth colour blur with one line of text). Measured: the ad
    screen scores about 5.5 fine detail per frame, gameplay with a facecam 8 or more."""
    import numpy as np
    w, h = 160, 90
    raw = subprocess.run([sc.FF(), '-v', 'error', '-i', path, '-vf', f'fps=1,scale={w}:{h},format=gray', '-f', 'rawvideo', '-'],
                         capture_output=True).stdout
    if len(raw) < w * h:
        return 0.0
    f = np.frombuffer(raw[:len(raw) // (w * h) * w * h], np.uint8).reshape(-1, h, w).astype(np.float32)
    detail = np.abs(np.diff(f, axis=2)).mean(axis=(1, 2)) + np.abs(np.diff(f, axis=1)).mean(axis=(1, 2))
    return float((detail < 7).mean())


def heat(texts):
    """Messages plus extra weight for reaction words: a burst of 'LMAOOO 💀' counts more than normal talk."""
    return len(texts) + 1.5 * sum(1 for x in texts if REACT.search(x or ''))


def mood(texts):
    try:
        m = find.mood_of(texts)
        return find.top_mood(m) or 'mixed'
    except Exception:
        return 'mixed'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    w = sub.add_parser('watch')
    w.add_argument('channel')
    w.add_argument('--hours', type=float, default=6, help='stop after this long (default 6)')
    w.add_argument('--keep', type=int, default=12, help='minutes of stream kept on disk (default 12)')
    w.add_argument('--sens', type=float, default=1.0, help='higher = fewer, bigger moments (default 1.0)')
    w.add_argument('--max', type=int, default=30, help='stop saving moments after this many (default 30)')
    w.add_argument('--pre', type=int, default=35, help='seconds before the chat spike (default 35)')
    w.add_argument('--post', type=int, default=10, help='seconds after the chat spike (default 10)')
    a = ap.parse_args()

    plat, name = resolve(a.channel)
    work = sc.conf()['work']
    base = os.path.join(work, 'live', name)
    buf = os.path.join(base, '_buffer')
    os.makedirs(base, exist_ok=True)
    log = os.path.join(base, 'moments.md')
    if not os.path.exists(log):
        with open(log, 'w') as fh:
            fh.write(f'# Live moments: {name} ({plat})\n\nEach line: when, how hard chat reacted, the mood, what chat said, the clip folder '
                     '(already downloaded and transcribed). Finish the best ones with a hook and a render.\n\n')
    say(f'Live mode on {plat}: {name}. Recording the last {a.keep} minutes and reading chat. Moments go to {log}')
    rec, chat = Recorder(plat, name, buf, a.keep), Chat(plat, name)
    # stopping the watcher (kill, a stopped background task) must also stop its ffmpeg recorder: an orphaned one
    # keeps writing into the same buffer, and a restarted watcher's moments then have every few seconds twice
    import signal
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGHUP, lambda *_: sys.exit(0))
    rec.start(); chat.start()
    hist = collections.deque(maxlen=36)  # the last 6 minutes of 10-second chat heat
    last_hit, saved, t_end = 0.0, 0, time.time() + a.hours * 3600
    pending = []  # (spike wall time, heat, ratio, texts)
    try:
        while time.time() < t_end and saved < a.max:
            time.sleep(SEG)
            now = time.time()
            texts = chat.window(now - SEG, now)
            h = heat(texts)
            if len(hist) >= 12:  # 2 minutes of normal chat first
                base_h = sorted(hist)[len(hist) // 2] or 1.0
                ratio = h / max(base_h, 3.0)
                need = 2.6 * a.sens
                if ratio >= need and h >= 12 * a.sens and now - last_hit > 45 and rec.ok:
                    last_hit = now
                    pending.append((now, h, ratio, texts))
                    say(f'Chat spike: {len(texts)} messages in 10 s, {ratio:.1f}x normal ({mood(texts)}). Saving it in {a.post} s...')
            hist.append(h)
            ticks = getattr(main, '_ticks', 0) + 1; main._ticks = ticks
            if ticks % 6 == 0:  # once a minute: show it is alive
                base_now = sorted(hist)[len(hist) // 2] if hist else 0
                say(f'Watching: {len(texts)} chat messages in the last 10 s (normal about {base_now:.0f} heat), '
                    f'{"recording" if rec.ok else "waiting for the stream"}, {saved} moment(s) saved so far.')
            for p in list(pending):  # wait until the seconds after the spike are recorded, then cut
                t_spike, h_, ratio, texts_ = p
                if now - t_spike < a.post + SEG + 2:
                    continue
                pending.remove(p)
                stamp = time.strftime('%H%M%S', time.localtime(t_spike))
                tmp = os.path.join(base, f'_moment_{stamp}.mp4')
                if not rec.cut(t_spike - a.pre, t_spike + a.post, tmp):
                    say('Could not cut that moment (the recording had a gap). Skipped.')
                    continue
                share = ad_share(tmp)
                if share >= 0.7:  # the viewer was shown Twitch's ad screen: nothing to clip, don't spend a slot on it
                    os.remove(tmp)
                    with open(log, 'a') as fh:
                        fh.write(f"- **{time.strftime('%H:%M:%S', time.localtime(t_spike))}** · {ratio:.1f}x normal chat · "
                                 f"skipped: Twitch ad break ({share:.0%} of the moment)\n")
                    say(f'Chat spike at {stamp} landed on an ad break ({share:.0%}). Skipped.')
                    continue
                clip_name = f'{name} live {stamp}'
                r = subprocess.run([sc.VPY(), os.path.join(HERE, 'clip.py'), 'new', clip_name, '--src', tmp, '--streamer', name],
                                   capture_output=True, text=True)
                folder = (r.stdout or '').strip().splitlines()[-1] if r.returncode == 0 and r.stdout.strip() else None
                os.remove(tmp)
                if not folder:
                    say('Saving the clip failed:', (r.stderr or '')[-300:]); continue
                subprocess.run([sc.VPY(), os.path.join(HERE, 'clip.py'), 'prep', os.path.basename(folder)], capture_output=True)
                saved += 1
                sample = ' | '.join(x[:40] for x in texts_[:12])
                with open(log, 'a') as fh:
                    fh.write(f"- **{time.strftime('%H:%M:%S', time.localtime(t_spike))}** · {ratio:.1f}x normal chat · "
                             f"{mood(texts_)} · chat: {sample} · clip: `{os.path.basename(folder)}`\n")
                say(f'Moment {saved} saved and transcribed: {os.path.basename(folder)}')
            if len(hist) == 12 and not chat.connected:
                say('Chat is not connected yet; still trying.')
    except KeyboardInterrupt:
        pass
    finally:
        rec.close(); chat.stop.set()
        time.sleep(1)
        shutil.rmtree(buf, ignore_errors=True)
        say(f'Live mode stopped. {saved} moment(s) saved. List: {log}')


if __name__ == '__main__':
    main()
