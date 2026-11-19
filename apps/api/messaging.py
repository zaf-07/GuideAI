import os
from urllib.parse import quote

SANDBOX_NUMBER = "+14155238886"
MAX_BODY = 1500


class MessageError(Exception):
    pass


def configured() -> bool:
    return bool(os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN"))


def whatsapp_link(phone: str, text: str) -> str:
    return f"https://wa.me/{phone}?text={quote(text)}"


async def send_whatsapp(phone: str, text: str) -> dict:
    import httpx

    sid, token = os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]
    sender = os.getenv("TWILIO_WHATSAPP_FROM", SANDBOX_NUMBER)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            response = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                auth=(sid, token),
                data={"From": f"whatsapp:{sender}", "To": f"whatsapp:+{phone}", "Body": text[:MAX_BODY]},
            )
    except Exception as error:
        raise MessageError("I could not reach the message service.") from error
    if response.status_code >= 400:
        raise MessageError("The message service refused the message.")
    body = response.json()
    return {"id": body.get("sid"), "status": body.get("status")}
