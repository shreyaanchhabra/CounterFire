"""Small helpers shared by agents."""
import hashlib


def short(s: str, n: int) -> str:
    """Trim to n chars at a word boundary. Gemini doesn't enforce length limits."""
    s = " ".join(s.split())
    if len(s) <= n:
        return s
    cut = s[: n - 1].rsplit(" ", 1)[0].rstrip(",;:-")
    return cut + "…"


def image_hash(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()[:10]


def clean_box(box):
    """Clamp [ymin, xmin, ymax, xmax] to 0-1000. Drop boxes that are empty or cover the whole image."""
    if not box or len(box) != 4:
        return None
    y0, x0, y1, x1 = (max(0, min(1000, int(v))) for v in box)
    y0, y1 = sorted((y0, y1))
    x0, x1 = sorted((x0, x1))
    if y1 - y0 < 10 or x1 - x0 < 10:
        return None
    if (y1 - y0) * (x1 - x0) > 900_000:
        return None
    return [y0, x0, y1, x1]
