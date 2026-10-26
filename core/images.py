"""Uploaded pictures are made small enough for slow mobile data before they're stored."""
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, ImageOps


def square_logo(image_field, size=256):
    """A newly uploaded logo becomes a centred square of size×size (PNG, so transparency is kept)."""
    if not image_field or getattr(image_field, '_committed', True):
        return
    image = ImageOps.exif_transpose(Image.open(image_field))
    image = image.convert('RGBA')
    # Pad to a square rather than crop, so wide logos aren't cut off.
    side = max(image.size)
    canvas = Image.new('RGBA', (side, side), (255, 255, 255, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    canvas = canvas.resize((size, size), Image.LANCZOS)
    buffer = BytesIO()
    canvas.save(buffer, format='PNG', optimize=True)
    image_field.save(Path(image_field.name).stem + '.png', ContentFile(buffer.getvalue()), save=False)
