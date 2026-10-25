"""Validate and re-encode uploaded photographs.

Every upload is decoded and written out fresh as a JPEG. This removes EXIF
metadata (including GPS location), rejects files that are not real images,
and neutralises anything hidden inside the original file.
"""

import hashlib
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "MPO"}


class InvalidImage(ValueError):
    pass


@dataclass
class Processed:
    full: bytes
    thumb: bytes
    width: int
    height: int
    sha256: str


def _encode(im: Image.Image, quality: int) -> bytes:
    out = BytesIO()
    im.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
    return out.getvalue()


def process(data: bytes, *, max_pixels: int, max_dim: int, thumb_dim: int, quality: int) -> Processed:
    Image.MAX_IMAGE_PIXELS = max_pixels
    try:
        with Image.open(BytesIO(data)) as probe:
            fmt = probe.format
            probe.verify()
        if fmt not in ALLOWED_FORMATS:
            raise InvalidImage("Use a JPEG, PNG, WebP or GIF photograph.")
        with Image.open(BytesIO(data)) as im:
            im.seek(0)
            im = ImageOps.exif_transpose(im)
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            else:
                im = im.convert("RGB")
            im.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            full = _encode(im, quality)
            width, height = im.size
            th = im.copy()
            th.thumbnail((thumb_dim, thumb_dim), Image.Resampling.LANCZOS)
            thumb = _encode(th, 80)
    except Image.DecompressionBombError as e:
        raise InvalidImage("That image is too large to process.") from e
    except (UnidentifiedImageError, OSError, SyntaxError) as e:
        raise InvalidImage("That file isn't a photograph we can read.") from e
    return Processed(full=full, thumb=thumb, width=width, height=height, sha256=hashlib.sha256(full).hexdigest())
