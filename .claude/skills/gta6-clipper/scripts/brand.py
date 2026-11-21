"""The clip page's own frame around every clip: a title bar on top (streamer + game, then the hook), the page's
watermark on the footage, and a footer bar (stars + "follow for daily clips").

Turned on by ~/Stream Clips/channels/brand.json. Without that file nothing changes. Example:
{
 "handle": "@FIVESTARCLIPS",            the watermark text (drawn if there is no logo file)
 "logo": "brand/logo.png",               a transparent PNG watermark, relative to ~/Stream Clips (optional)
 "game": "GTA VI",                       shown after the streamer's name in the title bar
 "footer": "FOLLOW FOR DAILY CLIPS",
 "header_h": 400, "footer_h": 220,       bar heights in a 1080x1920 frame
 "colors": {"bg": "#0B0B10", "accent": "#FFC629", "label": "#FF3D7F", "footer_text": "#C9C9D6", "mark": "#DDDDDE"},
 "captions": {"font": "anton/anton-v27-latin-regular.ttf", "size": 124, "fill": "#FFC629", "mode": "none", ...}
}
A clip opts out with "brand": false in its clip.json."""
import math, os, re
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import sc

FONTS = os.path.join(sc.SKILL, 'fonts')
DEFAULTS = dict(handle=None, logo=None, game='GTA VI', footer='FOLLOW FOR DAILY CLIPS', header_h=400, footer_h=220,
                colors=dict(bg='#0B0B10', accent='#FFC629', label='#FF3D7F', footer_text='#C9C9D6', mark='#DDDDDE', badge_fill='#F4F1EA'),
                header_icon='star', badge=None,
                captions=dict(font='anton/anton-v27-latin-regular.ttf', size=124, case='upper', fill='#FFC629', mode='none',
                              colors=[], stroke=9, shadow='hard', skew=0, words=2, anim='pop'),
                tag_color='white', mark_opacity=.85, mark_width=380)


def load():
    path = os.path.join(sc.conf().get('work', ''), 'channels', 'brand.json')
    if not os.path.exists(path):
        return None
    b = dict(DEFAULTS)
    user = sc.jload(path)
    for k, v in user.items():
        b[k] = dict(DEFAULTS.get(k) or {}, **v) if isinstance(v, dict) and isinstance(DEFAULTS.get(k), dict) else v
    return b


def _font(rel, size):
    return ImageFont.truetype(os.path.join(FONTS, rel), size)


def _rgb(h, a=255):
    return sc.hexrgb(h, a)


def _star(d, cx, cy, r, fill=None, outline=None, width=0):
    pts = []
    for k in range(10):
        rr = r if k % 2 == 0 else r * .42
        ang = -math.pi / 2 + k * math.pi / 5
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    d.polygon(pts, fill=fill, outline=outline, width=width)


def _spaced(d, xy, text, font, fill, track):
    """Letter-spaced text (the small labels in the bars)."""
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += font.getlength(ch) + track
    return x


def label_of(p):
    """Who is in the clip, for the title bar: from the credit ("Kai Cenat on Twitch") or the streamer id."""
    c = (p.get('credit') or '').strip()
    c = re.sub(r'\s+on\s+(Twitch|YouTube|Kick|TikTok)\s*$', '', c, flags=re.I)
    return (c or p.get('streamer') or '').upper()


def _strip_emoji(s):
    return re.sub('[\U0001F000-\U0001FAFF☀-➿️‍]', '', s).strip()


def header(b, W, hook, who):
    h = int(b['header_h'])
    im = Image.new('RGB', (W, h), _rgb(b['colors']['bg'])[:3])
    d = ImageDraw.Draw(im)
    if b.get('header_icon') == 'dot':
        d.ellipse([64, 82, 92, 110], fill=_rgb(b['colors']['accent']))
    else:
        _star(d, 90, 96, 25, fill=_rgb(b['colors']['accent']))
    lab = _font('inter/inter-v20-latin-800.ttf', 30)
    text = ' · '.join(x for x in (who, b.get('game')) if x)
    _spaced(d, (136, 78), text, lab, _rgb(b['colors']['label']), 3.5)
    words = _strip_emoji(hook or '').upper().split()
    if words:
        maxw, top, bottom = W - 128, 142, h - 22
        for size in range(96, 50, -4):  # the biggest size that fits in two lines (three if it must)
            f = _font('anton/anton-v27-latin-regular.ttf', size)
            lines, cur = [], []
            for w in words:
                if cur and f.getlength(' '.join(cur + [w])) > maxw:
                    lines.append(' '.join(cur)); cur = []
                cur.append(w)
            lines.append(' '.join(cur))
            lh = int(size * 1.02)
            if len(lines) <= (2 if size > 70 else 3) and lh * len(lines) <= bottom - top:
                break
        y = top + (bottom - top - lh * len(lines)) // 2
        for L in lines:
            d.text((64, y), L, font=f, fill=(255, 255, 255))
            y += lh
    return np.array(im)[..., ::-1].copy()


def footer(b, W):
    h = int(b['footer_h'])
    im = Image.new('RGB', (W, h), _rgb(b['colors']['bg'])[:3])
    d = ImageDraw.Draw(im)
    cy = h // 2
    tx = 466
    if b.get('badge'):  # a rounded label like the page's logo badge: light fill, coloured border, dark letters
        bf = _font('anton/anton-v27-latin-regular.ttf', 46)
        bw = int(bf.getlength(b['badge'])) + 64
        d.rounded_rectangle([64, cy - 40, 64 + bw, cy + 40], radius=16, fill=_rgb(b['colors']['badge_fill']),
                            outline=_rgb(b['colors']['label']), width=6)
        d.text((64 + bw / 2, cy), b['badge'], font=bf, fill=_rgb(b['colors']['bg']), anchor='mm')
        tx = 64 + bw + 30
    else:
        for k in range(5):
            _star(d, 92 + k * 76, cy, 31, fill=_rgb(b['colors']['accent']))
    f = _font('inter/inter-v20-latin-800.ttf', 31)
    _spaced(d, (tx, cy - 19), b.get('footer') or '', f, _rgb(b['colors']['footer_text']), 4)
    return np.array(im)[..., ::-1].copy()


def watermark(b):
    """The page's mark as RGBA: the logo file if there is one, otherwise the star + handle drawn here."""
    logo = b.get('logo')
    if logo:
        path = logo if os.path.isabs(logo) else os.path.join(sc.conf().get('work', ''), logo)
        if os.path.exists(path):
            im = Image.open(path).convert('RGBA')
            w = int(b.get('mark_width', 380))
            im = im.resize((w, max(1, int(im.height * w / im.width))), Image.LANCZOS)
            return _fade(im, b)
    if not b.get('handle'):
        return None
    f = _font('anton/anton-v27-latin-regular.ttf', 52)
    tw = int(f.getlength(b['handle']))
    im = Image.new('RGBA', (tw + 96, 80), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    _star(d, 38, 40, 30, fill=_rgb(b['colors']['mark']))
    d.text((84, 6), b['handle'], font=f, fill=_rgb(b['colors']['mark']), stroke_width=3, stroke_fill=(0, 0, 0, 140))
    return _fade(im, b)


def _fade(im, b):
    from PIL import ImageFilter
    pad = 14  # a soft dark shadow so the light mark stays readable on bright footage
    sh = Image.new('RGBA', (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    al = Image.new('L', sh.size, 0)
    al.paste(im.getchannel('A'), (pad, pad))
    al = al.filter(ImageFilter.GaussianBlur(7)).point(lambda v: int(v * .75))
    sh.putalpha(al)
    sh.alpha_composite(im, (pad, pad))
    im = sh
    a = np.array(im)
    a[..., 3] = (a[..., 3].astype(np.float32) * float(b.get('mark_opacity', .85))).astype(np.uint8)
    return Image.fromarray(a, 'RGBA')


def logo_from_picture(src, out, bg=None):
    """Turn a logo picture on a flat background (like a screenshot of the handle) into a transparent PNG:
    the background colour becomes see-through and the light mark keeps its edges smooth."""
    a = np.array(Image.open(src).convert('RGB')).astype(np.float32)
    if bg is None:
        corners = np.concatenate([a[:4, :4].reshape(-1, 3), a[-4:, -4:].reshape(-1, 3)])
        bg = np.median(corners, axis=0)
    lum = a.mean(axis=2)
    bl, fl = float(np.mean(bg)), float(np.percentile(lum, 99.5))
    alpha = np.clip((lum - bl) / max(1.0, fl - bl), 0, 1)
    fg = a[lum >= np.percentile(lum, 99)].mean(axis=0)  # the mark's own colour, used for every pixel; alpha does the edges
    rgba = np.dstack([np.full_like(lum, fg[0]), np.full_like(lum, fg[1]), np.full_like(lum, fg[2]), alpha * 255]).astype(np.uint8)
    img = Image.fromarray(rgba, 'RGBA')
    bb = img.getbbox()
    img = img.crop(bb) if bb else img
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)
    return out


class Frame:
    """Puts each rendered picture of the footage into the branded 1080x1920 frame."""

    def __init__(self, b, W, H, p, hook_text):
        self.W, self.H = W, H
        self.hh, self.fh = int(b['header_h']), int(b['footer_h'])
        self.content_h = H - self.hh - self.fh
        self.top = header(b, W, hook_text, label_of(p))
        self.bottom = footer(b, W)
        self.mark = watermark(b)

    def compose(self, content, paste):
        if self.mark is not None:
            paste(content, self.mark, self.W - 34 - self.mark.width / 2, 34 + self.mark.height / 2)
        out = np.empty((self.H, self.W, 3), np.uint8)
        out[:self.hh] = self.top
        out[self.hh:self.hh + self.content_h] = content
        out[self.hh + self.content_h:] = self.bottom
        return out
