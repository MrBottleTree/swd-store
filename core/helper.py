import io
import os
import urllib.parse
from operator import attrgetter

from django.core.files.base import ContentFile
from PIL import Image as PILImage, ImageOps, UnidentifiedImageError


MAX_IMAGE_DIMENSION = 1600
JPEG_QUALITY = 82


def compress_image_bytes(source):
    """Resize + re-encode an image as a compressed JPEG.

    `source` may be any file-like object Pillow can open (UploadedFile, BytesIO,
    a path, or an open file handle). Returns the JPEG bytes. Caller handles I/O.

    Pipeline: bake EXIF rotation, flatten alpha onto white, downscale so the
    longest edge is at most MAX_IMAGE_DIMENSION, save progressive JPEG at
    JPEG_QUALITY with optimize=True. Raises whatever Pillow raises on bad input.
    """
    if hasattr(source, 'seek'):
        try:
            source.seek(0)
        except Exception:
            pass

    with PILImage.open(source) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            rgba = img.convert('RGBA')
            background = PILImage.new('RGB', rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[-1])
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        if max(img.size) > MAX_IMAGE_DIMENSION:
            img.thumbnail(
                (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
                PILImage.Resampling.LANCZOS,
            )

        buffer = io.BytesIO()
        img.save(
            buffer,
            format='JPEG',
            quality=JPEG_QUALITY,
            optimize=True,
            progressive=True,
        )

    return buffer.getvalue()


def normalize_uploaded_image(uploaded_file):
    """Resize + re-encode every uploaded image as a compressed JPEG.

    Phone uploads (iPhone HEIC, Android multi-MB JPEGs) are downscaled to a max
    edge of MAX_IMAGE_DIMENSION and re-saved at JPEG_QUALITY so the home page
    serves reasonable bytes instead of full-resolution camera output. On any
    decode failure (corrupt file, unsupported format) we return the original
    file so Django's ImageField validator surfaces its own clean error.
    """
    if uploaded_file is None:
        return uploaded_file

    try:
        compressed = compress_image_bytes(uploaded_file)
    except (UnidentifiedImageError, OSError, ValueError):
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        return uploaded_file

    name = getattr(uploaded_file, 'name', '') or ''
    base = os.path.splitext(os.path.basename(name))[0] or 'image'
    return ContentFile(compressed, name=f'{base}.jpg')


def generate_whatsapp_link(phone_number, message=None):
    phone_number = get_clean_number(phone_number)
    phone_number = phone_number[1:]  # strip leading '+'
    base_url = "https://wa.me/"
    if message:
        encoded_message = urllib.parse.quote(message)
        url = f"{base_url}{phone_number}?text={encoded_message}"
    else:
        url = f"{base_url}{phone_number}"
    return url


def get_clean_number(phone_number):
    phone_number = ''.join(filter(str.isdigit, phone_number))
    phone_number = phone_number.lstrip('0')
    if len(phone_number) == 10:
        phone_number = f"+91{phone_number}"
    elif len(phone_number) == 12 and phone_number.startswith("91"):
        phone_number = f"+{phone_number}"
    elif len(phone_number) == 9:
        phone_number = f"+971{phone_number}"
    elif phone_number.startswith("971"):
        phone_number = f"+{phone_number}"
    return phone_number


def items_sort(items_list, method='0'):
    if not method:
        method = '0'
    items = list(items_list)
    method = str(method)

    unsold = [itm for itm in items if not itm.is_sold]
    sold = [itm for itm in items if itm.is_sold]

    if method == '0':
        key_fn, rev = attrgetter('updated_at'), True
    elif method == '1':
        key_fn, rev = attrgetter('price'), False
    elif method == '2':
        key_fn, rev = attrgetter('price'), True
    else:
        raise ValueError("Invalid method. Use '0', '1' or '2'.")

    unsold_sorted = sorted(unsold, key=key_fn, reverse=rev)
    sold_sorted = sorted(sold, key=key_fn, reverse=rev)

    return unsold_sorted + sold_sorted
