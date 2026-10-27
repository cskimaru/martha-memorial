"""Suggest a caption from a photo's file name."""

import re
from pathlib import PurePath

# Names cameras, phones and apps give photos, which say nothing about the picture.
CAMERA_NAME = re.compile(
    r"^(img|dsc|dscn|dcim|pxl|mvimg|photo|image|picture|whatsapp image|screenshot|signal|scan|p)"
    r"[\s_-]*[\d\s_.-]*(at[\s\d._-]*)?(\(\d+\))?$",
    re.IGNORECASE,
)


def caption_from_name(name: str) -> str:
    """'Mama_at_church-1985.jpg' -> 'Mama at church 1985'; 'IMG_2041.JPG' -> ''."""
    stem = PurePath(name).stem
    stem = re.sub(r"^\d{10,}-", "", stem)  # collision prefix added by the inbox service
    stem = re.sub(r"\s*\(\d+\)$", "", stem)  # "Mama (2)": a second copy of the same name
    if not stem or CAMERA_NAME.match(stem) or re.fullmatch(r"[\d\s_.-]+", stem):
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[_]+|(?<=\w)-(?=\w)", " ", stem)).strip()[:240]
