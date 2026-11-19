import json
import re
from urllib.parse import parse_qs, quote, urlparse

import llm

PRICE_PROMPT = (
    "This photo shows something for sale, a price tag, a menu, a receipt or a checkout screen. "
    'Reply with JSON only: {"item": "<short name of the item or \'your order\'>", '
    '"amount": <total price as a number>, "currency": "<three-letter code>"}. '
    "Use the total if one is shown. "
    'If no price is clearly readable, reply {"item": "", "amount": 0, "currency": ""}. Never guess a price.'
)
AMOUNT = re.compile(r"\$?\s*(\d{1,4}(?:[.,]\d{1,2})?)")


def _cents(value) -> int | None:
    try:
        cents = round(float(str(value).replace(",", ".").replace("$", "").strip()) * 100)
    except (TypeError, ValueError):
        return None
    return cents if cents > 0 else None


def payment_code(item: str, amount: float) -> str:
    return f"guideai://pay?item={quote(item)}&amount={amount:.2f}"


def parse_payment_code(text: str) -> tuple[str, int] | None:
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("{"):
        try:
            data = json.loads(text)
            cents = _cents(data.get("amount"))
            return (str(data.get("item") or "your order")[:60], cents) if cents else None
        except (ValueError, AttributeError):
            return None
    if "amount=" in text:
        query = parse_qs(urlparse(text).query or text.split("?", 1)[-1])
        cents = _cents((query.get("amount") or [""])[0])
        return ((query.get("item") or ["your order"])[0][:60], cents) if cents else None
    match = AMOUNT.search(text)
    if match and ("$" in text or "usd" in text.lower()):
        item = AMOUNT.sub("", text).replace("USD", "").strip(" -:$") or "your order"
        cents = _cents(match.group(1))
        return (item[:60], cents) if cents else None
    return None


def read_qr(image: bytes) -> str:
    try:
        import cv2
        import numpy as np

        frame = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return ""
        text, _, _ = cv2.QRCodeDetector().detectAndDecode(frame)
        return text or ""
    except Exception:
        return ""


def make_qr_png(text: str, size: int = 480) -> bytes:
    import cv2

    code = cv2.QRCodeEncoder_create().encode(text)
    code = cv2.copyMakeBorder(code, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    code = cv2.resize(code, (size, size), interpolation=cv2.INTER_NEAREST)
    ok, png = cv2.imencode(".png", code)
    if not ok:
        raise ValueError("Could not draw the QR code")
    return png.tobytes()


async def read_price(image: bytes, mime: str) -> tuple[str, int] | None:
    if not llm.configured():
        return None
    try:
        data = json.loads(await llm.complete([llm.image_part(image, mime), {"text": PRICE_PROMPT}], json_mode=True))
        if str(data.get("currency") or "USD").upper() not in ("USD", "$", ""):
            return None
        cents = _cents(data.get("amount"))
        return (str(data.get("item") or "your order")[:60], cents) if cents else None
    except Exception:
        return None


async def read_frame(image: bytes, mime: str) -> tuple[str, int, str] | None:
    found = parse_payment_code(read_qr(image))
    if found:
        return (*found, "qr")
    found = await read_price(image, mime)
    return (*found, "price") if found else None
