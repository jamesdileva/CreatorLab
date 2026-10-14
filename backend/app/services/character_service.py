"""Character visual identity — consistent per-creator look (roadmap Sprint 5.2).

Deterministic flat-design portrait renderer: same identity always produces the
same character, different identities produce visibly different characters.
No external image services (offline-first, no keys in repo).
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base

IDENTITY_VERSION = "identity-v1"

WIDTH, HEIGHT = 1080, 1920
FONT_PATH = r"C:\Windows\Fonts\arial.ttf"

_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")

PALETTE_KEYS = (
    "bg_top",
    "bg_bottom",
    "skin",
    "shirt",
    "hair",
    "accent",
    "text",
)

DEFAULT_IDENTITIES: dict[str, dict] = {
    "hank": {
        "display_name": "Hank",
        "palette": {
            "bg_top": "#2b3a1e",
            "bg_bottom": "#141a0d",
            "skin": "#c99b6a",
            "shirt": "#4a5d3a",
            "hair": "#6b4a2f",
            "accent": "#d8a03c",
            "text": "#f5f1e4",
        },
        "accessories": ["cap", "beard"],
        "props": ["gear"],
        "style": "rugged, weathered, workwear",
    },
    "willow": {
        "display_name": "Willow",
        "palette": {
            "bg_top": "#1e3320",
            "bg_bottom": "#0c140d",
            "skin": "#b98a5e",
            "shirt": "#3f6b3a",
            "hair": "#3a2a1a",
            "accent": "#e0784a",
            "text": "#eef3e2",
        },
        "accessories": ["flower"],
        "props": ["mug"],
        "style": "earthy, handmade, garden-worn",
    },
    "alex-exe": {
        "display_name": "Alex.exe",
        "palette": {
            "bg_top": "#101a2e",
            "bg_bottom": "#070b16",
            "skin": "#cfd8e8",
            "shirt": "#22314f",
            "hair": "#1b2436",
            "accent": "#36e0d8",
            "text": "#e8f6ff",
        },
        "accessories": ["visor", "headset"],
        "props": ["terminal"],
        "style": "sleek, glossy, synthetic",
    },
}


def _normalize_hex(value: str) -> str:
    if not _HEX.match(value or ""):
        raise ValueError(f"invalid hex color: {value!r}")
    return "#" + value.lstrip("#").lower()


class CharacterIdentity(Base):
    __tablename__ = "character_identities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("creators.id"), index=True, unique=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(120), default="")
    palette_json: Mapped[dict] = mapped_column(JSON, default=dict)
    accessories: Mapped[list[str]] = mapped_column(JSON, default=list)
    props: Mapped[list[str]] = mapped_column(JSON, default=list)
    style: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[str] = mapped_column(String(32), default=IDENTITY_VERSION)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    @property
    def palette(self) -> dict:
        stored = self.palette_json or {}
        return {k: _normalize_hex(v) for k, v in stored.items() if k in PALETTE_KEYS}


def validate_palette(palette: dict) -> dict:
    cleaned = {}
    for key, value in (palette or {}).items():
        if key not in PALETTE_KEYS:
            raise ValueError(f"unknown palette key: {key}")
        cleaned[key] = _normalize_hex(value)
    if not cleaned:
        raise ValueError("palette must set at least one color")
    return cleaned


def identity_for_creator(db, creator) -> CharacterIdentity:
    """Return the identity, creating the default for known slugs on demand."""
    ident = (
        db.query(CharacterIdentity)
        .filter(CharacterIdentity.creator_id == creator.id)
        .one_or_none()
    )
    if ident is None:
        default = DEFAULT_IDENTITIES.get(creator.slug)
        if default is None:
            raise ValueError(f"no default identity for creator slug: {creator.slug}")
        ident = CharacterIdentity(
            creator_id=creator.id,
            display_name=default["display_name"],
            palette_json=default["palette"],
            accessories=list(default["accessories"]),
            props=list(default["props"]),
            style=default["style"],
            version=IDENTITY_VERSION,
        )
        db.add(ident)
        db.commit()
        db.refresh(ident)
    return ident


def _font(size: int):
    try:
        from PIL import ImageFont as _F

        return _F.truetype(FONT_PATH, size)
    except OSError:
        from PIL import ImageFont as _F

        return _F.load_default()


def _gradient(top: tuple, bottom: tuple) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), top)
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / HEIGHT
        draw.line([(0, y), (WIDTH, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img


def _hex_rgb(value: str) -> tuple:
    v = value.lstrip("#")
    return tuple(int(v[i : i + 2], 16) for i in (0, 2, 4))


def _rounded(draw: ImageDraw.ImageDraw, box, radius, fill) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _draw_accessory_cap(draw, palette, cx, cy, scale):
    w, h = int(210 * scale), int(70 * scale)
    hair = _hex_rgb(palette["hair"])
    accent = _hex_rgb(palette["accent"])
    _rounded(draw, [cx - w, cy - h, cx + w, cy + int(h * 0.6)], 30, accent)
    draw.rectangle([cx - w, cy + int(h * 0.1), cx + w, cy + int(h * 0.45)], fill=accent)


def _draw_beard(draw, palette, cx, cy, scale):
    hair = _hex_rgb(palette["hair"])
    _rounded(draw, [cx - int(95 * scale), cy, cx + int(95 * scale), cy + int(150 * scale)], 70, hair)


def _draw_visor(draw, palette, cx, cy, scale):
    accent = _hex_rgb(palette["accent"])
    _rounded(draw, [cx - int(150 * scale), cy - int(45 * scale), cx + int(150 * scale), cy + int(35 * scale)], 40, accent)


def _draw_headset(draw, palette, cx, cy, scale):
    accent = _hex_rgb(palette["accent"])
    draw.arc([cx - int(160 * scale), cy - int(200 * scale), cx + int(160 * scale), cy + int(80 * scale)], 180, 360, fill=accent, width=int(16 * scale))
    draw.line([(cx + int(150 * scale), cy - int(60 * scale)), (cx + int(190 * scale), cy + int(40 * scale))], fill=accent, width=int(14 * scale))
    _rounded(draw, [cx + int(178 * scale), cy + int(30 * scale), cx + int(206 * scale), cy + int(60 * scale)], 12, accent)


def _draw_flower(draw, palette, cx, cy, scale):
    """Flower crown arc across the hairline."""
    accent = _hex_rgb(palette["accent"])
    text = _hex_rgb(palette["text"])
    for i, dx in enumerate(range(-150, 170, 50)):
        x = cx + int(dx * scale)
        y = cy + int((abs(dx) // 50) * 12 * scale)
        r = int(26 * scale)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=accent if i % 2 == 0 else text)


def _draw_prop_gear(draw, palette, x, y, r):
    accent = _hex_rgb(palette["accent"])
    draw.ellipse([x - r, y - r, x + r, y + r], outline=accent, width=int(r * 0.28))


def _draw_prop_terminal(draw, palette, x, y, w, h):
    accent = _hex_rgb(palette["accent"])
    _rounded(draw, [x, y, x + w, y + h], 18, accent)
    draw.rectangle([x + int(w * 0.12), y + int(h * 0.2), x + int(w * 0.55), y + int(h * 0.3)], fill=(10, 12, 20))


def _draw_prop_mug(draw, palette, x, y, w, h):
    accent = _hex_rgb(palette["accent"])
    _rounded(draw, [x, y, x + w, y + h], 16, accent)
    draw.arc([x + w - 10, y + int(h * 0.2), x + w + 50, y + int(h * 0.75)], 270, 90, fill=accent, width=12)


def render_portrait(identity: CharacterIdentity, path: Path) -> Path:
    """Deterministic portrait bust for this identity (no layout text)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    palette = identity.palette
    img = _gradient(_hex_rgb(palette["bg_top"]), _hex_rgb(palette["bg_bottom"]))
    draw = ImageDraw.Draw(img)

    skin = _hex_rgb(palette["skin"])
    shirt = _hex_rgb(palette["shirt"])
    hair = _hex_rgb(palette["hair"])
    accent = _hex_rgb(palette["accent"])

    cx = WIDTH // 2
    head_cy = 620
    r = 250
    # torso / shoulders
    _rounded(draw, [cx - 520, head_cy + 320, cx + 520, 1750], 220, shirt)
    draw.ellipse([cx - r - 40, head_cy + 260, cx + r + 40, head_cy + 420], fill=shirt)
    # head
    draw.ellipse([cx - r, head_cy - r, cx + r, head_cy + r], fill=skin)

    accessories = set(identity.accessories or [])
    if "cap" in accessories:
        _draw_accessory_cap(draw, palette, cx, head_cy - int(r * 0.75), 1.0)
    if "beard" in accessories:
        _draw_beard(draw, palette, cx, head_cy + int(r * 0.35), 1.0)
    if "visor" in accessories:
        _draw_visor(draw, palette, cx, head_cy - 20, 1.0)
    if "headset" in accessories:
        _draw_headset(draw, palette, cx, head_cy - r, 1.0)
    if "flower" in accessories:
        _draw_flower(draw, palette, cx, head_cy - int(r * 0.8), 1.0)

    props = set(identity.props or [])
    if "gear" in props:
        _draw_prop_gear(draw, palette, 240, 1560, 110)
    if "terminal" in props:
        _draw_prop_terminal(draw, palette, 700, 1500, 200, 130)
    if "mug" in props:
        _draw_prop_mug(draw, palette, 700, 1500, 170, 120)

    img.save(path)
    return path


def render_identity_card(
    identity: CharacterIdentity, title: str, direction: str, path: Path
) -> Path:
    """Scene card: portrait + title block (used by the Sprint 5.1 renderer)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    portrait_path = path.with_name(path.stem + "_portrait.png")
    render_portrait(identity, portrait_path)
    canvas = Image.open(portrait_path).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    text = _hex_rgb(identity.palette["text"])
    accent = _hex_rgb(identity.palette["accent"])

    draw.rectangle([60, 90, WIDTH - 60, 100], fill=accent)
    _wrap_write(draw, (identity.display_name or title).upper(), 80, 130, _font(58), accent)

    _wrap_write(draw, title, 90, 1120, _font(84), text)
    _wrap_write(draw, direction, 90, 1400, _font(40), (200, 200, 200))

    canvas.save(path)
    portrait_path.unlink(missing_ok=True)
    return path


def _wrap_write(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, font, fill) -> None:
    if not text:
        return
    max_w = WIDTH - x - 90
    words, line, lines = text.split(), "", []
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    for i, ln in enumerate(lines[:6]):
        draw.text((x, y + i * 105), ln, font=font, fill=fill)


def identity_snapshot(identity: CharacterIdentity) -> dict:
    """Reproducibility record for a render."""
    return {
        "version": identity.version,
        "palette": identity.palette,
        "accessories": list(identity.accessories or []),
        "props": list(identity.props or []),
        "style": identity.style,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "snapshot": json.dumps(
            {
                "palette": identity.palette,
                "accessories": identity.accessories,
                "props": identity.props,
            },
            sort_keys=True,
        ),
    }
