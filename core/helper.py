import io
import os
import urllib.parse
from operator import attrgetter

from django.core.files.base import ContentFile
from PIL import Image as PILImage, ImageOps, UnidentifiedImageError


_HEIC_CONTENT_TYPES = {'image/heic', 'image/heif', 'image/heic-sequence', 'image/heif-sequence'}
_HEIC_EXTENSIONS = {'.heic', '.heif'}


def normalize_uploaded_image(uploaded_file):
    """Convert HEIC/HEIF uploads to JPEG; pass other images through unchanged.

    iPhones save photos as HEIC by default and Pillow's stock build cannot decode
    them, so Django's ImageField validation rejects the upload. We re-encode HEIC
    to JPEG (with EXIF orientation applied) so the rest of the stack sees a normal
    image. On any decode failure we return the original file so non-HEIC uploads
    continue to surface their own validation errors.
    """
    if uploaded_file is None:
        return uploaded_file

    name = getattr(uploaded_file, 'name', '') or ''
    content_type = (getattr(uploaded_file, 'content_type', '') or '').lower()
    ext = os.path.splitext(name)[1].lower()

    if content_type not in _HEIC_CONTENT_TYPES and ext not in _HEIC_EXTENSIONS:
        return uploaded_file

    try:
        uploaded_file.seek(0)
        with PILImage.open(uploaded_file) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=90, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError):
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        return uploaded_file

    base = os.path.splitext(os.path.basename(name))[0] or 'image'
    return ContentFile(buffer.getvalue(), name=f'{base}.jpg')


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
