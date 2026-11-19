"""Installs everything the GTA 6 Clipper needs into ~/.stream-clipper (no password, no admin rights).
Run through setup.sh, which brings uv and Python 3.11. Prints plain-English steps and READY at the end."""
import json, os, platform, shutil, subprocess, sys, tempfile, time, urllib.request, zipfile

HOME = os.path.expanduser('~')
TOOLS = os.path.join(HOME, '.stream-clipper')
WORK = os.path.join(HOME, 'Stream Clips')
CONF = os.path.join(TOOLS, 'config.json')
WIN = os.name == 'nt'
MAC = sys.platform == 'darwin'
ARM = platform.machine().lower() in ('arm64', 'aarch64')
VPY = os.path.join(TOOLS, 'venv', 'Scripts' if WIN else 'bin', 'python.exe' if WIN else 'python')
EXE = '.exe' if WIN else ''
# opencv-python (not -headless): the text reader needs it anyway, and two OpenCV packages share one folder and break each other
PKGS = ['numpy', 'opencv-python<5', 'pillow', 'yt-dlp', 'curl_cffi', 'requests', 'send2trash']
WHISPER = 'mlx-whisper' if MAC and ARM else 'faster-whisper'
# Windows on ARM (Snapdragon laptops) has no OpenCV build, so it uses the normal Windows Python, which runs fine there
PYVER = 'cpython-3.11-windows-x86_64-none' if WIN else '3.11'


def say(msg):
    print(msg, flush=True)


def load():
    try:
        return json.load(open(CONF))
    except Exception:
        return {}


def check():
    c = load()
    ok = c.get('ready') and all(os.path.exists(c.get(k, '')) for k in ('python', 'ffmpeg', 'ffprobe'))
    print('READY' if ok else 'NOT READY: run setup')
    return 0 if ok else 1


def fetch(url, dst):
    req = urllib.request.Request(url, headers={'User-Agent': 'stream-clipper-setup'})
    with urllib.request.urlopen(req, timeout=120) as r, open(dst, 'wb') as f:
        shutil.copyfileobj(r, f)


def ffmpeg_paths():
    """Use ffmpeg if the computer already has it, otherwise download a ready-made copy (about 80 MB)."""
    have = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if all(have):
        return have
    bin_ = os.path.join(TOOLS, 'bin')
    os.makedirs(bin_, exist_ok=True)
    mine = os.path.join(bin_, 'ffmpeg' + EXE), os.path.join(bin_, 'ffprobe' + EXE)
    if all(os.path.exists(p) for p in mine):
        return mine
    tmp = tempfile.mkdtemp()
    if WIN:
        z = os.path.join(tmp, 'ff.zip')
        fetch('https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip', z)
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                b = os.path.basename(n)
                if b in ('ffmpeg.exe', 'ffprobe.exe'):
                    with zf.open(n) as s, open(os.path.join(bin_, b), 'wb') as d:
                        shutil.copyfileobj(s, d)
    else:
        osn = 'macos' if MAC else 'linux'
        arch = 'arm64' if ARM else 'amd64'
        for tool in ('ffmpeg', 'ffprobe'):
            z = os.path.join(tmp, tool + '.zip')
            for chan in ('release', 'snapshot'):
                try:
                    fetch(f'https://ffmpeg.martin-riedl.de/redirect/latest/{osn}/{arch}/{chan}/{tool}.zip', z)
                    break
                except Exception:
                    continue
            else:
                raise SystemExit(f'NOT READY: could not download {tool}. Check the internet connection and run setup again.')
            with zipfile.ZipFile(z) as zf:  # the program may sit at the top of the zip or in a folder inside it
                n = next((n for n in zf.namelist() if os.path.basename(n) == tool), None)
                if not n:
                    raise SystemExit(f'NOT READY: the {tool} download was not as expected. Run setup again.')
                with zf.open(n) as s, open(os.path.join(bin_, tool), 'wb') as d:
                    shutil.copyfileobj(s, d)
            os.chmod(os.path.join(bin_, tool), 0o755)
            if MAC:
                subprocess.run(['xattr', '-d', 'com.apple.quarantine', os.path.join(bin_, tool)], capture_output=True)
    shutil.rmtree(tmp, ignore_errors=True)
    if not all(os.path.exists(p) for p in mine):
        raise SystemExit('NOT READY: ffmpeg did not install. Run setup again.')
    return mine


def pip(*a):
    subprocess.run(['uv', 'pip', 'install', '-q', '--python', VPY, *a], check=True)


def main():
    if '--check' in sys.argv:
        sys.exit(check())
    os.makedirs(TOOLS, exist_ok=True)
    for d in ('streams', 'clips', 'finished', 'channels'):
        os.makedirs(os.path.join(WORK, d), exist_ok=True)
    c = load()

    say('Step 2 of 6: getting ffmpeg (the tool that cuts and joins video)...')
    ff, fp = ffmpeg_paths()
    say('  done')

    say('Step 3 of 6: making a private Python just for the clipper...')
    if not os.path.exists(VPY):
        subprocess.run(['uv', 'venv', '-q', '--python', PYVER, os.path.join(TOOLS, 'venv')], check=True)
    say('  done')

    say('Step 4 of 6: installing the editing tools (about 300 MB, 1 to 3 minutes)...')
    pip(*PKGS, WHISPER)
    say('  done')

    say('Step 5 of 6: downloading the speech-to-text brain for captions (about 1.6 GB, 2 to 10 minutes the first time)...')
    if WHISPER == 'mlx-whisper':
        code = "from huggingface_hub import snapshot_download as d; d('mlx-community/whisper-large-v3-turbo')"
    else:
        code = "from faster_whisper import WhisperModel; WhisperModel('large-v3-turbo', compute_type='int8')"
    subprocess.run([VPY, '-c', code], check=True)
    say('  done')

    say('Step 6 of 6: test run (checks your computer can render, and times it)...')
    tmp = tempfile.mkdtemp()
    t = time.time()
    subprocess.run([ff, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=1080x1920:rate=30:duration=4',
                    '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', os.path.join(tmp, 't.mp4')], check=True)
    enc = (time.time() - t) / 4  # seconds of work per second of finished video, for encoding alone
    shutil.rmtree(tmp, ignore_errors=True)
    c.update(python=VPY, ffmpeg=ff, ffprobe=fp, whisper=WHISPER, work=WORK, encode_rate=round(enc, 3), ready=True,
             setup_at=time.strftime('%Y-%m-%d'))
    c.setdefault('speed', {})
    json.dump(c, open(CONF, 'w'), indent=1)
    say('  done')
    say(f'Your streams, clips and finished videos live in: {WORK}')
    say('READY')


if __name__ == '__main__':
    main()
