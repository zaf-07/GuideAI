from __future__ import annotations

import asyncio
import os
import re
import time

import checkout
import llm
import messaging
import navigation
import scene
from family import Family
from payments import Orders, PaymentError

YES = re.compile(r"^\W*(yes|yeah|yep|yup|sure|confirm|go ahead|do it|send( it)?|pay( it| now)?|okay|ok)\b[\w\s,.!']{0,22}$")
NO = re.compile(r"^\W*(no|nope|cancel|stop|not now|never mind|don't|do not)\b[\w\s,.!']{0,22}$")
TIMER = re.compile(
    r"\b(?:set|start|put|make) (?:a |an |the |me a )?(?:\w+ )?(?:timer|alarm|reminder)\b|\bremind me\b|\btimer for\b"
)
DURATION = re.compile(
    r"\b(half an?|an?|\d+|[a-z]+(?:[ -][a-z]+)?) (second|minute|hour)s?\b|\b(half) an (hour)\b"
)
NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60,
}
UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600}

FORGET = re.compile(r"\b(forget everything|(clear|delete|wipe|erase) (all )?(my |your )?memor(y|ies))\b")
REMEMBER = re.compile(r"^\W*(please )?remember\b|\bsave this\b|\bremember (this|that|where)\b")
PAY = re.compile(r"\b(buy|order|purchase|pay for|get me)\b")
SCAN_PAY = re.compile(
    r"\b(pay|scan|buy)\b.*\b(this|that|it|code|qr|bill|total)\b|\bscan (and|to) pay\b|^\W*pay\W*$"
)
RECALL = re.compile(
    r"\bwhere (did|have)\b|\bwhere (is|are|was|were) my\b|\bwhat did\b|\b(did|have) you seen?\b"
    r"|\bdo you remember\b|\blast (saw|seen)\b|\bwhat (do|did) you remember\b"
    r"|\bwhere (was|have) i\b|\bwhere did i go\b|\bwhat (did|have) i (ask|asked|say|said)\b"
)
WHERE = re.compile(
    r"\bwhere am i\b|\bwhat(?:'s| is) (around|near|nearby)( me)?\b|\bmy (current )?location\b|\bwhat street\b"
)
MESSAGE = re.compile(
    r"^\W*(?:please |can you |could you )*(tell|text|message|whatsapp|send|write)\s+"
    r"(?:a (?:message|text|whatsapp) )?(?:to )?(?!me\b)"
    r"|\bshare my location\b|\b(?:send|write) (?:a )?(?:whatsapp |text )?message to\b"
)
LOOSE_MESSAGE = re.compile(r"\b(tell|text|message|whatsapp|write|send)\b")
PLACE_NAMES = {"home": "home", "house": "home", "work": "work", "office": "work", "school": "school", "dorm": "dorm"}
_PLACE = r"(?:(home|house|work|office|school|dorm)(?: address| mattress| adress)?|address|adress)"
PLACE_SET = re.compile(
    r"\b(?:my " + _PLACE + r" is(?: at| in)?"
    r"|(?:change|changing|set|update|make|save|put) my " + _PLACE + r"(?: to| as| is| at)?"
    r"|i live (?:at|in|on))\s+(.+?)[\s.!?]*$"
)
PLACE_ASK = re.compile(r"\b(?:change|changing|set|update|save|edit) my " + _PLACE + r"[\s.!?]*$")
ADDRESS_LEAD = re.compile(
    r"^(?:(?:it is|it's|its|to|at|is|in|the address is|located in|located at)\s+)+", re.IGNORECASE,
)
_LEAD_FILLER = re.compile(
    r"^(?:yeah|yes|yep|no|nope|okay|ok|hello|hi|hey|now|please|thanks|thank you|search it|find it|change it"
    r"|look it up|i said|i mean)[\s.,!?]*$",
    re.IGNORECASE,
)
_TAIL_FILLER = re.compile(
    r"^(?:(?:it )?should be there|i think|please|right now|thank you|thanks|that is it|that's it|okay|ok)[\s.,!?]*$",
    re.IGNORECASE,
)
CONFIRM_ANY = re.compile(r"\b(?:yes|yeah|yep|correct|right|save it|change it|do it|confirm|that's it|that is it)\b")
ADDRESS_LIKE = re.compile(r"\d|[A-Za-z]{3,}\W+[A-Za-z]{3,}")
FILLER = re.compile(
    r"^(?:(?:can|could|would|will) you\b.*|please\b.*|get the\b.*|okay\b.*|um+\b.*|uh+\b.*|now\b.*|oh\b.*"
    r"|i (?:said|mean)\b.*)$"
)
PLACE_LOOKUP_PROMPT = (
    "The text below was spoken aloud and transcribed, so words may be misheard and it may contain filler. "
    "Work out which real place or address is meant and give its full street address on one line, "
    "with city and state. Reply with the address only. If you do not know it, reply with the single word UNKNOWN."
)
PLACE_GO = re.compile(
    r"\b(?:take|get|guide|walk|bring|lead) me (?:to )?(?:my )?(home|house|work|office|school|dorm)\b"
    r"|\b(?:directions?|route|way|go|going|head|navigate) (?:to )?(?:my )?(home|house|work|office|school|dorm)\b"
)
CALL = re.compile(r"\b(?:call|dial|phone)\s+(?:my\s+)?([a-z][a-z0-9 .-]{1,39})\b", re.IGNORECASE)
OPEN_APP = re.compile(r"^\W*(?:open|launch|start)\s+(?:the\s+)?(whatsapp|messages|maps|facetime|calendar)\b", re.IGNORECASE)
BRIDGE = re.compile(r"\bbridge\b")
NAV = re.compile(
    r"\b(take|guide|walk|navigate|lead|bring|get) me to\b|\b(directions?|route|way) to\b"
    r"|\bhow do i get to\b|\bnavigate to\b|\b(nearest|closest)\b"
)
NAV_STOP = re.compile(r"\b(stop|cancel|end) (the )?(navigation|directions|route|guiding)\b")
GO_BACK = re.compile(r"\b(take|guide|walk|lead|bring) me back\b|\bway back\b|\bgo back to (the )?start\b")
READ = re.compile(r"\bread\b|\bwhat does (it|that|this|the) .*\bsay\b|\bwhat is written\b")
HELP = re.compile(r"\bwhat can you do\b|^\W*help\b")
GREETING = re.compile(r"^\W*(hi|hello|hey|good (morning|afternoon|evening)|howdy)\b")

READ_QUESTION = (
    "Read aloud every piece of text you can see in this image, word for word, starting with the largest. "
    "Say only the text itself. If there is no readable text, say that you cannot see any text."
)
SURROUNDINGS_QUESTION = "Briefly describe my surroundings: what kind of place is this and what is around me?"
HELP_TEXT = (
    "I can tell you what is in front of you, read text, tell you where you are, "
    "guide you on foot to a place nearby, message your family, and pay after you say yes. "
    "Try: what is in front of me?"
)
MEMORY_TEXT = "Memory is not connected to the assistant yet. Open Memory from the home screen."
APP_URLS = {
    "whatsapp": "whatsapp://", "messages": "sms:", "maps": "maps://", "facetime": "facetime://", "calendar": "ical://",
}
MESSAGE_TTL_SECONDS = 60
CALL_TTL_SECONDS = 60
PLACE_CHANGE_TTL_SECONDS = 120
TRIP_GAP_SECONDS = 20 * 60
PENDING_SUFFIXES = ("_confirm", "_cancel", "_waiting")


def _number(words: str) -> float | None:
    words = words.strip().lower()
    if words.isdigit():
        return float(words)
    if words in ("half a", "half an"):
        return 0.5
    total = 0
    for word in re.split(r"[ -]", words):
        if word not in NUMBER_WORDS:
            return None
        total += NUMBER_WORDS[word]
    return float(total) if total else None


def parse_duration(text: str) -> int | None:
    for match in DURATION.finditer(text.lower()):
        if match.group(3):
            return 1800
        amount = _number(match.group(1))
        if amount is None:
            amount = _number(match.group(1).split()[-1])
        if amount:
            return int(amount * UNIT_SECONDS[match.group(2)])
    return None


def spoken_duration(seconds: int) -> str:
    if seconds % 3600 == 0:
        count, unit = seconds // 3600, "hour"
    elif seconds >= 60:
        count, unit = round(seconds / 60), "minute"
    else:
        count, unit = seconds, "second"
    return f"{count} {unit}{'s' if count != 1 else ''}"


def timer_label(text: str) -> str:
    match = re.search(r"\bremind me (?:to |that |about )?(.+?)(?: in | after |$)", text, re.IGNORECASE)
    label = match.group(1).strip(" .,!?") if match else ""
    return label if label and not DURATION.search(label.lower()) else ""


def spoken_place(text: str) -> str:
    parts = [part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]
    while parts and _LEAD_FILLER.match(parts[0]):
        parts.pop(0)
    while parts and _TAIL_FILLER.match(parts[-1]):
        parts.pop()
    return " ".join(parts).strip(" .!?,")


def message_body(text: str) -> str:
    match = re.search(r"\b(?:saying|that says|say|that)\b[\s,:]*(.+)$", text, re.IGNORECASE)
    body = match.group(1).strip(" .") if match else ""
    return "" if re.search(r"\bwhere i am\b|\bmy location\b", body, re.IGNORECASE) else body


def route(text: str, has_pending: bool = False) -> str:
    value = text.lower().strip()
    if has_pending:
        if YES.search(value):
            return "pay_confirm"
        if NO.search(value):
            return "pay_cancel"
        return "pay_waiting"
    checks = [
        (FORGET, "forget"), (TIMER, "timer"), (NAV_STOP, "nav_stop"), (GO_BACK, "go_back"),
        (PLACE_SET, "place_set"), (PLACE_ASK, "place_set"), (PLACE_GO, "place_go"), (WHERE, "where_am_i"),
        (MESSAGE, "message"), (CALL, "call"), (OPEN_APP, "open_app"), (NAV, "navigate"),
        (SCAN_PAY, "scan_pay"), (PAY, "pay_quote"), (RECALL, "recall"), (REMEMBER, "remember"),
        (BRIDGE, "bridge"), (HELP, "help"), (GREETING, "greeting"),
    ]
    for pattern, intent in checks:
        if pattern.search(value):
            return intent
    if YES.search(value) or NO.search(value):
        return "nothing_pending"
    return "see"


def blank_reply(intent: str, text: str) -> dict:
    return {
        "intent": intent, "heard": text, "say": "", "order": None, "confirm": None, "open_url": None,
        "map_url": None, "timer": None, "navigating": False, "warnings": [], "detections": [], "provider": None,
    }


class Assistant:
    def __init__(self, family: Family, orders: Orders, detector=None, navigator=None, place_name=None,
                 read_frame=None, send_whatsapp=None, geocode=None, lookup_address=None) -> None:
        self.family = family
        self.orders = orders
        self.detector = detector or scene.detector
        self.navigator = navigator or navigation.Navigator()
        self.place_name = place_name or navigation.place_name
        self.read_frame = read_frame or checkout.read_frame
        self.send_whatsapp = send_whatsapp or messaging.send_whatsapp
        self.geocode = geocode or navigation.geocode
        self.lookup_address = lookup_address or self._lookup_address
        self._messages: dict[str, dict] = {}
        self._calls: dict[str, dict] = {}
        self._place_changes: dict[str, dict] = {}
        self._trips: dict[str, dict] = {}
        self._sent: dict[str, list[float]] = {}

    def _live(self, store: dict[str, dict], session: str) -> dict | None:
        item = store.get(session)
        if item and time.time() > item["expires"]:
            del store[session]
            return None
        return item

    def pending_message(self, session: str) -> dict | None:
        return self._live(self._messages, session)

    def track(self, session: str, lat: float, lon: float, now: float | None = None) -> None:
        now = now or time.time()
        trip = self._trips.get(session)
        if trip is None or now - trip["seen"] > TRIP_GAP_SECONDS:
            self._trips[session] = {"lat": lat, "lon": lon, "seen": now}
        else:
            trip["seen"] = now

    def trip_start(self, session: str, now: float | None = None) -> dict | None:
        trip = self._trips.get(session)
        if trip is None or (now or time.time()) - trip["seen"] > TRIP_GAP_SECONDS:
            return None
        return trip

    async def respond(self, session: str, text: str, image: bytes | None = None, mime: str = "image/jpeg",
                      location: tuple[float, float] | None = None) -> dict:
        if location is not None:
            self.track(session, *location)
        order = self.orders.pending(session)
        message = self.pending_message(session)
        call = self._live(self._calls, session)
        change = self._live(self._place_changes, session)
        if change and not order and not message and not call:
            return await self._continue_place_change(session, change, text, location)
        value = text.lower()
        intent = route(text, bool(order or message))
        named_contact = (
            intent in ("see", "place_go", "navigate", "go_back", "where_am_i", "recall", "help", "timer")
            and LOOSE_MESSAGE.search(value) and self.family.find_contact(session, text)
        )
        if named_contact:
            intent = "message"
        if call and not order and not message:
            intent = "call_confirm" if YES.search(value) else "call_cancel" if NO.search(value) else "call_waiting"
        if message and not order:
            intent = intent.replace("pay_", "message_")
        reply = blank_reply(intent, text)

        if intent == "pay_quote":
            self._quote(reply, self.orders.quote(session, text))
        elif intent == "scan_pay":
            await self._scan_pay(reply, session, image, mime)
        elif intent == "pay_confirm":
            await self._pay(reply, session)
        elif intent == "pay_cancel":
            self.orders.cancel(session)
            reply["say"] = "Cancelled. Nothing was paid."
        elif intent == "pay_waiting":
            reply["order"] = order
            reply["confirm"] = f"Pay {order['price']} for {order['item']}?"
            reply["say"] = f"I am waiting for a yes or no: {order['item']} for {order['price']}."
        elif intent == "message":
            await self._compose_message(reply, session, text, location)
        elif intent == "message_confirm":
            del self._messages[session]
            await self._send_message(reply, session, message)
        elif intent == "message_cancel":
            del self._messages[session]
            reply["say"] = "Cancelled. Nothing was sent."
        elif intent == "message_waiting":
            reply["confirm"] = f"Send to {message['name']} on WhatsApp?"
            reply["say"] = f"I am waiting for a yes or no on the message to {message['name']}."
        elif intent == "call":
            self._prepare_call(reply, session, text)
        elif intent == "call_confirm":
            contact = self._calls.pop(session)
            reply["open_url"] = f"tel:+{contact['phone']}"
            reply["say"] = f"Calling {contact['name']}."
        elif intent == "call_cancel":
            self._calls.pop(session, None)
            reply["say"] = "Cancelled. I will not call anyone."
        elif intent == "call_waiting":
            reply["confirm"] = f"Call {call['name']}?"
            reply["say"] = f"I am waiting for a yes or no before calling {call['name']}."
        elif intent == "open_app":
            self._open_app(reply, text)
        elif intent == "nothing_pending":
            reply["say"] = "There is nothing waiting for your answer."
        elif intent in ("forget", "recall", "remember"):
            reply["say"] = MEMORY_TEXT
        elif intent == "where_am_i":
            await self._where(reply, image, mime, location)
        elif intent == "place_set":
            await self._start_place_change(reply, session, text, location)
        elif intent == "timer":
            self._timer(reply, text)
        elif intent == "place_go":
            before = self.navigator.active(session)
            reply["say"] = await self._go_to_place(session, text, location)
            self._finish_navigation(reply, session, location, before)
        elif intent == "nav_stop":
            reply["say"] = "Navigation stopped." if self.navigator.stop(session) else "No navigation is running."
        elif intent in ("navigate", "go_back"):
            before = self.navigator.active(session)
            reply["say"] = await self._navigate(session, intent, text, location)
            self._finish_navigation(reply, session, location, before)
        elif intent == "bridge":
            reply["say"] = "Bridge is on. I will speak signs I can read, and show what you say as large text."
        elif intent == "help":
            reply["say"] = HELP_TEXT
        elif intent == "greeting":
            reply["say"] = "Hello! I am GuideAI. I can describe what is in front of you, navigate, read text, or message your family."
        elif image is None:
            reply["say"] = "I need the camera for that. Please turn the camera on."
        else:
            await self._look(reply, text, image, mime)
        return reply

    def _quote(self, reply: dict, order: dict | None) -> None:
        if order is None:
            reply["say"] = "I could not find a price for that, so I will not pay for it."
            return
        reply["order"] = order
        reply["confirm"] = f"Pay {order['price']} for {order['item']}?"
        reply["say"] = f"{order['item'].capitalize()} for {order['price']}. Say yes to pay, or no to cancel."

    async def _scan_pay(self, reply: dict, session: str, image: bytes | None, mime: str) -> None:
        if image is None:
            reply["say"] = "I need the camera to read the price. Please turn the camera on."
            return
        found = await self.read_frame(image, mime)
        if found is None:
            reply["say"] = "I cannot read a payment code or a clear price. Hold it closer and try again. Nothing was paid."
            return
        item, cents, source = found
        try:
            order = self.orders.quote_item(session, item, cents)
        except PaymentError as error:
            reply["say"] = str(error)
            return
        self._quote(reply, order)
        reply["say"] = ("I scanned a payment code. " if source == "qr" else "I read the price. ") + reply["say"]

    async def _pay(self, reply: dict, session: str) -> None:
        try:
            receipt = await self.orders.confirm(session)
        except PaymentError as error:
            reply["say"] = str(error)
            return
        reply["order"] = receipt
        note = " This was a simulated payment." if receipt["mode"] == "simulated" else " Paid in Stripe test mode."
        reply["say"] = f"Done. I paid {receipt['price']} for {receipt['item']}.{note}"

    async def _compose_message(self, reply: dict, session: str, text: str,
                               location: tuple[float, float] | None) -> None:
        contact = self.family.find_contact(session, text)
        if contact is None:
            names = [item["name"] for item in self.family.contacts(session)]
            known = (
                " Your contacts are " + ", ".join(names) + "." if names
                else " You have no contacts yet: add them on the Family screen."
            )
            example = names[0] if names else "Mom"
            reply["say"] = f"I did not catch who to message.{known} Say, for example: tell {example} where I am."
            return
        body = message_body(text)
        if not body:
            if location is None:
                reply["say"] = "I need your location to share it. Please turn location on."
                return
            place = await self.place_name(*location)
            lead = f"I am near {place}. " if place else "Here is where I am. "
            body = f"{lead}Map: https://maps.google.com/?q={location[0]:.5f},{location[1]:.5f} (sent with GuideAI)"
        self._messages[session] = {
            "name": contact["name"], "phone": contact["phone"], "text": body,
            "expires": time.time() + MESSAGE_TTL_SECONDS, "url": messaging.whatsapp_link(contact["phone"], body),
        }
        reply["confirm"] = f"Send to {contact['name']} on WhatsApp?"
        spoken = body.split(" Map:")[0]
        reply["say"] = f"Message to {contact['name']}: {spoken} Say yes to send, or no to cancel."

    def _may_send(self, session: str, now: float | None = None) -> bool:
        now = now or time.time()
        limit = int(os.getenv("MESSAGE_SENDS_PER_HOUR", "10"))
        recent = [moment for moment in self._sent.get(session, []) if now - moment < 3600]
        if len(recent) >= limit:
            self._sent[session] = recent
            return False
        self._sent[session] = [*recent, now]
        return True

    async def _send_message(self, reply: dict, session: str, message: dict) -> None:
        if messaging.configured() and self._may_send(session):
            try:
                await self.send_whatsapp(message["phone"], message["text"])
                reply["say"] = f"Sent to {message['name']} on WhatsApp."
                return
            except messaging.MessageError:
                pass
        reply["open_url"] = message["url"]
        reply["say"] = f"Your message to {message['name']} is ready in WhatsApp."

    def _prepare_call(self, reply: dict, session: str, text: str) -> None:
        match = CALL.search(text)
        name = match.group(1).strip() if match else ""
        contact = self.family.find_contact(session, name)
        if contact is None:
            reply["say"] = f"I do not have {name or 'that person'} in your contacts. Add them on the Family screen first."
            return
        self._calls[session] = {**contact, "expires": time.time() + CALL_TTL_SECONDS}
        reply["confirm"] = f"Call {contact['name']}?"
        reply["say"] = f"I found {contact['name']}. Say yes to call, or no to cancel."

    def _open_app(self, reply: dict, text: str) -> None:
        match = OPEN_APP.search(text)
        app = match.group(1).lower() if match else ""
        url = APP_URLS.get(app)
        if url is None:
            reply["say"] = "I can only open WhatsApp, Messages, Maps, FaceTime, or Calendar."
            return
        reply["open_url"] = url
        reply["say"] = f"Opening {app.capitalize()}."

    async def _where(self, reply: dict, image: bytes | None, mime: str,
                     location: tuple[float, float] | None) -> None:
        parts = []
        if location is not None:
            found = await navigation.address(*location)
            parts.append(f"You are at {found}." if found else "I have your GPS position, but could not look up the address.")
        else:
            parts.append("I do not have your location. Turn location on for the address.")
        if image is not None:
            detections = await asyncio.to_thread(self.detector.detect, image)
            answer = await scene.describe(image, mime, SURROUNDINGS_QUESTION, detections)
            parts.append(answer["text"])
            reply.update(detections=detections, provider=answer["provider"])
        reply["say"] = " ".join(parts)

    async def resolve_place(self, wanted: str, location: tuple[float, float] | None) -> dict | None:
        near = location or (None, None)
        found = await self.geocode(wanted, *near)
        if re.search(r"\d", wanted):
            return found
        words = [word for word in re.findall(r"[a-z]+", wanted.lower()) if len(word) > 3]
        label = (found or {}).get("label", "").lower()
        matched = sum(1 for word in words if word in label)
        if found is not None and words and matched / len(words) >= 0.6:
            return found
        address = await self.lookup_address(wanted)
        if address:
            better = await self.geocode(address, *near)
            if better is not None:
                name = spoken_place(wanted)
                short = name and len(name.split()) <= 5
                return {**better, "label": f"{name.title()} ({better['label']})" if short else better["label"]}
        return found

    @staticmethod
    async def _lookup_address(place: str) -> str:
        if not llm.configured():
            return ""
        try:
            answer = (await llm.complete([{"text": f"Place: {place}"}], system=PLACE_LOOKUP_PROMPT)).strip()
        except Exception:
            return ""
        return "" if "UNKNOWN" in answer.upper() or len(answer) > 160 else answer.splitlines()[0]

    async def _start_place_change(self, reply: dict, session: str, text: str,
                                  location: tuple[float, float] | None) -> None:
        value = text.lower().strip()
        asked, match = PLACE_ASK.search(value), PLACE_SET.search(value)
        if asked:
            name, address = PLACE_NAMES[asked.group(1) or "home"], ""
        else:
            name = PLACE_NAMES[match.group(1) or match.group(2) or "home"]
            address = text.strip()[match.start(3):].strip(" .!?")
        change = {"name": name, "stage": "address", "found": None, "expires": time.time() + PLACE_CHANGE_TTL_SECONDS}
        self._place_changes[session] = change
        if len(address) < 3:
            reply["say"] = f"What is your {name} address? Say the street number, the street and the city."
            return
        await self._offer_place(reply, change, address, location)

    async def _offer_place(self, reply: dict, change: dict, address: str,
                           location: tuple[float, float] | None) -> None:
        name = change["name"]
        change["expires"] = time.time() + PLACE_CHANGE_TTL_SECONDS
        change["query"] = address
        try:
            found = await self.resolve_place(address, location)
        except Exception:
            found = None
        if found is None:
            change["stage"] = "address"
            reply["say"] = f'I could not find "{address}" on the map. Say the address again, with the street number and the city.'
            return
        change.update(stage="confirm", found=found)
        reply["confirm"] = f"Save {found['label']} as your {name}?"
        reply["say"] = f"I found {found['label']}. Should I save it as your {name}? Say yes, or say the address again."

    async def _continue_place_change(self, session: str, change: dict, text: str,
                                     location: tuple[float, float] | None) -> dict:
        reply = blank_reply("place_set", text)
        value, name = text.lower().strip(), change["name"]
        short_yes = (
            len(value.split()) <= 6 and CONFIRM_ANY.search(value)
            and not re.search(r"\d", value) and not NO.search(value)
        )
        if change["stage"] == "confirm" and (YES.search(value) or short_yes):
            found = change["found"]
            del self._place_changes[session]
            try:
                self.family.save_place(session, name, found["label"], found["lat"], found["lon"])
            except ValueError as error:
                reply["intent"] = "place_cancel"
                reply["say"] = str(error)
                return reply
            reply["intent"] = "place_saved"
            reply["say"] = f'Saved. Your {name} is {found["label"]}. Say "take me {name}" for directions.'
            return reply
        if NO.search(value):
            if change["stage"] == "confirm":
                change.update(stage="address", found=None, expires=time.time() + PLACE_CHANGE_TTL_SECONDS)
                reply["say"] = "Okay, not saved. Say the address again, with the street number and the city. Or say cancel."
            else:
                del self._place_changes[session]
                reply["intent"] = "place_cancel"
                reply["say"] = f"Okay. Your {name} address is unchanged."
            return reply
        match = PLACE_SET.search(value)
        if not match and route(text) not in ("see", "nothing_pending", "place_set"):
            del self._place_changes[session]
            return await self.respond(session, text, None, "image/jpeg", location)
        address = text.strip()[match.start(3):].strip(" .!?") if match else text.strip(" .!?")
        address = ADDRESS_LEAD.sub("", spoken_place(address) or address).strip()
        continues = (
            change["stage"] == "confirm" and change.get("query") and not match
            and len(address.split()) <= 3 and not re.search(r"\d", address)
        )
        if continues:
            address = f"{change['query']} {address}"
        if not ADDRESS_LIKE.search(address) or FILLER.match(address.lower()):
            change["misses"] = change.get("misses", 0) + 1
            if change["misses"] >= 3:
                del self._place_changes[session]
                reply["intent"] = "place_cancel"
                reply["say"] = f'I will leave your {name} address as it is. Say "change my {name} address" to try again.'
            else:
                reply["say"] = "Say the address: the street number, the street and the city. Or say cancel."
            return reply
        await self._offer_place(reply, change, address, location)
        return reply

    async def _go_to_place(self, session: str, text: str, location: tuple[float, float] | None) -> str:
        match = PLACE_GO.search(text.lower().strip())
        name = PLACE_NAMES[match.group(1) or match.group(2)]
        place = self.family.place(session, name)
        if place is None:
            return f"I do not know your {name} address yet. Say: my {name} address is, followed by the address."
        if location is None:
            return "I need your location for directions. Please turn location on."
        try:
            return await self.navigator.start_to(session, f"Your {name}", *location, place["lat"], place["lon"])
        except navigation.NavigationError as error:
            return str(error)

    def _timer(self, reply: dict, text: str) -> None:
        seconds = parse_duration(text)
        if seconds is None:
            reply["say"] = "For how long? Say, for example: set a timer for ten minutes."
            return
        if seconds > 24 * 3600:
            reply["say"] = "I can only set timers of up to a day."
            return
        label = timer_label(text)
        reply["timer"] = {"seconds": seconds, "label": label}
        about = f" to {label}" if label else ""
        reply["say"] = f"Timer set for {spoken_duration(seconds)}. I will remind you{about}."

    def _finish_navigation(self, reply: dict, session: str, location: tuple[float, float] | None,
                           before: dict | None) -> None:
        active = self.navigator.active(session)
        reply["navigating"] = active is not None
        if active is None or location is None or active is before:
            return
        reply["map_url"] = (
            "https://www.google.com/maps/dir/?api=1&travelmode=walking"
            f"&origin={location[0]:.6f},{location[1]:.6f}&destination={active['lat']:.6f},{active['lon']:.6f}"
        )

    async def _navigate(self, session: str, intent: str, text: str, location: tuple[float, float] | None) -> str:
        if location is None:
            return "I need your location for directions. Please turn location on."
        try:
            if intent == "go_back":
                start = self.trip_start(session)
                if start is None or navigation.haversine(*location, start["lat"], start["lon"]) < 40:
                    return "You are still close to where you started."
                return await self.navigator.start_to(
                    session, "your starting point", *location, start["lat"], start["lon"],
                )
            try:
                return await self.navigator.start(session, text, *location)
            except navigation.NavigationError:
                wanted = navigation.destination_query(text)[1]
                try:
                    found = await self.resolve_place(wanted, location)
                except Exception:
                    found = None
                if found is None:
                    raise
                return await self.navigator.start_to(session, found["label"], *location, found["lat"], found["lon"])
        except navigation.NavigationError as error:
            return str(error)

    async def _look(self, reply: dict, text: str, image: bytes, mime: str) -> None:
        detections = await asyncio.to_thread(self.detector.detect, image)
        reply["detections"] = detections
        reply["warnings"] = scene.hazard_warnings(detections)
        if READ.search(text.lower()):
            answer = await scene.describe(image, mime, READ_QUESTION, [])
        else:
            answer = await scene.describe(image, mime, text, detections)
        reply.update(say=answer["text"], provider=answer["provider"])
