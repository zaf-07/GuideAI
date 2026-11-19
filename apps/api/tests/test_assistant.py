import time

import pytest

import checkout
import navigation
import payments
from assistant import Assistant, message_body, parse_duration, route, timer_label
from conftest import FakeDetector, detection, run
from family import Family
from navigation import Navigator
from payments import Orders, PaymentError

HOME = (37.7606, -122.3866)
SHOP = (37.7650, -122.3866)
CORNER = (37.7628, -122.3866)


async def place_name(lat, lon):
    return "20th Street, Dogpatch"


async def fake_place(term, lat, lon):
    return {"name": "Safeway", "lat": SHOP[0], "lon": SHOP[1], "distance_m": 490}


async def no_place(term, lat, lon):
    return None


async def fake_route(lat, lon, dest_lat, dest_lon):
    return {"distance_m": 490, "duration_s": 360, "steps": [
        {"say": "Head north on 20th Street for 250 feet.", "lat": HOME[0], "lon": HOME[1], "distance_m": 245},
        {"say": "Turn left onto Illinois Street. Then continue for 800 feet.", "lat": CORNER[0], "lon": CORNER[1], "distance_m": 245},
        {"say": "You have arrived.", "lat": SHOP[0], "lon": SHOP[1], "distance_m": 0},
    ]}


def make(detections=(), frame=None, **options):
    async def read_frame(image, mime):
        return frame

    family = options.pop("family", None) or Family(":memory:")
    options.setdefault("navigator", Navigator(fake_place, fake_route))
    return Assistant(family, Orders(), FakeDetector(detections), place_name=place_name, read_frame=read_frame, **options)


def test_intents():
    cases = {
        "What's in front of me?": "see",
        "What does that sign say?": "see",
        "Tell me what is in front of me": "see",
        "Where did I leave my keys?": "recall",
        "Remember this": "remember",
        "Buy me a coffee": "pay_quote",
        "Pay this": "scan_pay",
        "Scan the code and pay": "scan_pay",
        "Forget everything": "forget",
        "Start Bridge": "bridge",
        "Call Alex": "call",
        "Open WhatsApp": "open_app",
        "Tell Mom where I am": "message",
        "Where am I?": "where_am_i",
        "What's around me?": "where_am_i",
        "Take me to the nearest supermarket": "navigate",
        "Get me to Safeway": "navigate",
        "Get me a coffee": "pay_quote",
        "Where is the closest pharmacy?": "navigate",
        "Take me back": "go_back",
        "Stop navigation": "nav_stop",
        "yes": "nothing_pending",
    }
    for text, intent in cases.items():
        assert route(text) == intent, text


def test_only_a_short_yes_or_no_matters_while_something_is_pending():
    long_request = "Okay. Can you set a timer I'm going to Safeway near Safeway in fifteen minutes."
    assert route(long_request) == "timer"
    assert route("Okay, what is in front of me right now please") == "see"
    assert route("Yes, pay", True) == "pay_confirm"
    assert route("Okay do it", True) == "pay_confirm"
    assert route("no thanks", True) == "pay_cancel"
    assert route("buy me a sandwich", True) == "pay_waiting"
    assert route("yesterday was nice", True) == "pay_waiting"
    assert route(long_request, True) == "pay_waiting"


def test_payment_needs_a_spoken_yes():
    assistant = make()
    quote = run(assistant.respond("s", "Buy me a latte"))
    assert quote["intent"] == "pay_quote"
    assert "$4.50" in quote["say"] and "Say yes" in quote["say"]
    assert run(assistant.respond("s", "what is in front of me"))["intent"] == "pay_waiting"
    paid = run(assistant.respond("s", "Yes"))
    assert paid["intent"] == "pay_confirm"
    assert "simulated" in paid["say"]


def test_no_cancels_without_paying():
    assistant = make()
    run(assistant.respond("s", "Buy me a coffee"))
    assert run(assistant.respond("s", "No"))["say"] == "Cancelled. Nothing was paid."
    assert run(assistant.respond("s", "yes"))["intent"] == "nothing_pending"


def test_a_long_okay_sentence_never_pays():
    assistant = make()
    run(assistant.respond("s", "Buy me a coffee"))
    reply = run(assistant.respond("s", "Okay so I was thinking we could go to the park later today"))
    assert reply["intent"] == "pay_waiting"


def test_unknown_item_is_refused():
    reply = run(make().respond("s", "Buy me a helicopter"))
    assert reply["order"] is None
    assert "will not pay" in reply["say"]


def test_orders_quote_expire_and_stay_per_session():
    orders = Orders()
    order = orders.quote("s", "buy me a coffee")
    assert (order["item"], order["price"]) == ("one medium coffee", "$3.50")
    assert run(orders.confirm("s"))["mode"] == "simulated"
    with pytest.raises(PaymentError):
        run(orders.confirm("s"))
    assert orders.quote("s", "buy me a helicopter") is None
    orders.quote("s", "buy a tea", now=1000)
    assert orders.pending("s", now=1030) is not None
    assert orders.pending("s", now=1000 + payments.ORDER_TTL_SECONDS + 1) is None
    orders.quote("alice", "buy a tea")
    assert orders.pending("bob") is None


def test_only_stripe_test_keys_are_accepted(monkeypatch):
    assert payments.is_test_key("sk_test_abc") and payments.is_test_key("rk_test_abc")
    assert not payments.is_test_key("sk_live_abc") and not payments.is_test_key("rk_live_abc")
    assert payments.mode() == "simulated"
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_not_a_real_key")
    assert payments.mode() == "refused_live_key"
    with pytest.raises(PaymentError):
        run(payments.charge({"id": "x", "item": "tea", "amount": 300, "currency": "usd"}))


def test_payment_codes():
    assert checkout.parse_payment_code(checkout.payment_code("Iced Latte", 5.25)) == ("Iced Latte", 525)
    assert checkout.parse_payment_code('{"item": "Sandwich", "amount": 8.5}') == ("Sandwich", 850)
    assert checkout.parse_payment_code("Coffee $4.50") == ("Coffee", 450)
    for text in ["", "https://example.com/menu", "hello world", '{"item": "x", "amount": 0}', "Table 12"]:
        assert checkout.parse_payment_code(text) is None, text


def test_qr_round_trip():
    pytest.importorskip("cv2")
    code = checkout.payment_code("Coffee", 4.5)
    assert checkout.read_qr(checkout.make_qr_png(code)) == code
    assert checkout.read_qr(b"not an image") == ""


def test_scanned_code_still_needs_a_yes():
    assistant = make(frame=("Coffee", 450, "qr"))
    quote = run(assistant.respond("s", "Pay this", b"frame"))
    assert quote["confirm"] == "Pay $4.50 for Coffee?"
    assert "Say yes to pay" in quote["say"]
    paid = run(assistant.respond("s", "Yes"))
    assert paid["intent"] == "pay_confirm"
    assert "I paid $4.50 for Coffee" in paid["say"]


def test_unreadable_frame_or_no_camera_pays_nothing():
    assert "Nothing was paid" in run(make().respond("s", "Pay this", b"frame"))["say"]
    assert "need the camera" in run(make(frame=("Coffee", 450, "qr")).respond("s", "Pay this"))["say"]


def test_spending_limit():
    reply = run(make(frame=("Television", 89900, "price")).respond("s", "Buy this", b"frame"))
    assert "over your $50.00 limit" in reply["say"]
    assert reply["order"] is None


def test_message_body():
    assert message_body("Text Alex saying I am running late.") == "I am running late"
    assert message_body("Tell Mom where I am") == ""


def test_location_message_needs_contact_location_and_yes():
    family = Family(":memory:")
    assistant = make(family=family)
    assert "contacts" in run(assistant.respond("s", "Tell Mom where I am", location=HOME))["say"]
    family.add_contact("s", "Mom", "+14155550100")
    assert "need your location" in run(assistant.respond("s", "Tell Mom where I am"))["say"]
    draft = run(assistant.respond("s", "Tell Mom where I am", location=HOME))
    assert draft["confirm"] == "Send to Mom on WhatsApp?"
    assert "I am near 20th Street, Dogpatch." in draft["say"]
    assert draft["open_url"] is None
    sent = run(assistant.respond("s", "Yes"))
    assert sent["intent"] == "message_confirm"
    assert sent["open_url"].startswith("https://wa.me/14155550100?text=I%20am%20near")
    assert "maps.google.com" in sent["open_url"]


def test_with_a_message_service_yes_sends_directly(monkeypatch):
    sent = []

    async def send(phone, text):
        sent.append((phone, text))

    family = Family(":memory:")
    family.add_contact("s", "Mom", "+14155550100")
    assistant = make(family=family, send_whatsapp=send)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    run(assistant.respond("s", "Text Mom saying I am on my way"))
    assert sent == []
    reply = run(assistant.respond("s", "Yes"))
    assert sent == [("14155550100", "I am on my way")]
    assert (reply["say"], reply["open_url"]) == ("Sent to Mom on WhatsApp.", None)


def test_direct_sends_are_capped_per_hour(monkeypatch):
    sent = []

    async def send(phone, text):
        sent.append(phone)

    family = Family(":memory:")
    family.add_contact("s", "Mom", "+14155550100")
    assistant = make(family=family, send_whatsapp=send)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setenv("MESSAGE_SENDS_PER_HOUR", "1")
    run(assistant.respond("s", "Text Mom saying one"))
    assert run(assistant.respond("s", "Yes"))["open_url"] is None
    run(assistant.respond("s", "Text Mom saying two"))
    capped = run(assistant.respond("s", "Yes"))
    assert len(sent) == 1
    assert capped["open_url"].startswith("https://wa.me/14155550100")


def test_dictated_message_and_cancel():
    family = Family(":memory:")
    family.add_contact("s", "Alex", "+14155550111")
    assistant = make(family=family)
    draft = run(assistant.respond("s", "Text Alex saying I am running late"))
    assert "Message to Alex: I am running late" in draft["say"]
    cancelled = run(assistant.respond("s", "No"))
    assert (cancelled["intent"], cancelled["say"]) == ("message_cancel", "Cancelled. Nothing was sent.")
    assert run(assistant.respond("s", "Yes"))["intent"] == "nothing_pending"


def test_one_persons_contacts_are_never_used_for_another():
    family = Family(":memory:")
    family.add_contact("alice", "Mom", "+14155550100")
    assistant = make(family=family)
    reply = run(assistant.respond("bob", "Tell Mom where I am", location=HOME))
    assert reply["confirm"] is None
    assert "no contacts yet" in reply["say"]


def test_call_requires_confirmation_and_returns_dial_url():
    family = Family(":memory:")
    family.add_contact("s", "Alex", "+14155550111")
    assistant = make(family=family)
    draft = run(assistant.respond("s", "Call Alex"))
    assert (draft["intent"], draft["confirm"]) == ("call", "Call Alex?")
    called = run(assistant.respond("s", "Yes"))
    assert (called["open_url"], called["say"]) == ("tel:+14155550111", "Calling Alex.")


def test_open_app_uses_allowlisted_url():
    reply = run(make().respond("s", "Open WhatsApp"))
    assert (reply["intent"], reply["open_url"]) == ("open_app", "whatsapp://")


def test_seeing_needs_a_camera_frame():
    assert "camera" in run(make().respond("s", "What's in front of me?"))["say"]


def test_see_offline_uses_the_detector():
    seen = run(make([detection("chair", 0.2, 0.5)]).respond("s", "What's in front of me?", b"frame"))
    assert (seen["provider"], seen["warnings"]) == ("local", ["Chair ahead, left."])
    assert "a chair ahead, left" in seen["say"]


def test_memory_requests_point_to_the_memory_screen():
    assistant = make([detection("backpack", 0.4, 0.6)])
    for text in ["Remember this", "Where did I leave my keys?", "Forget everything"]:
        assert "Memory" in run(assistant.respond("s", text, b"frame"))["say"], text


def test_where_am_i_without_location():
    assert "do not have your location" in run(make().respond("s", "Where am I?"))["say"]


def test_durations_and_timers():
    assert parse_duration("set a timer for 15 minutes") == 900
    assert parse_duration("in fifteen minutes") == 900
    assert parse_duration("timer for twenty five minutes") == 1500
    assert parse_duration("remind me in an hour") == 3600
    assert parse_duration("wake me in half an hour") == 1800
    assert parse_duration("thirty seconds") == 30
    assert parse_duration("set a timer") is None
    assistant = make()
    reply = run(assistant.respond("s", "Okay. Can you set a timer I'm going to Safeway in fifteen minutes."))
    assert reply["timer"]["seconds"] == 900
    assert "Timer set for 15 minutes" in reply["say"]
    reminder = run(assistant.respond("s", "Remind me to take my pills in ten minutes"))
    assert reminder["timer"] == {"seconds": 600, "label": "take my pills"}
    assert timer_label("set a timer for five minutes") == ""
    assert "For how long" in run(assistant.respond("s", "Set a timer"))["say"]


def test_directions_need_a_location_and_come_with_a_map_link():
    assistant = make()
    assert "need your location" in run(assistant.respond("s", "Take me to Safeway"))["say"]
    reply = run(assistant.respond("s", "Take me to the nearest supermarket", location=HOME))
    assert reply["navigating"]
    assert "Safeway is" in reply["say"]
    assert "travelmode=walking" in reply["map_url"]
    assert "destination=37.765000,-122.386600" in reply["map_url"]
    assert run(assistant.respond("s", "Stop navigation"))["say"] == "Navigation stopped."


def test_a_failed_request_does_not_reuse_the_previous_map():
    async def nowhere(text, lat=None, lon=None):
        return None

    navigator = Navigator(fake_place, fake_route)
    first = run(make(navigator=navigator).respond("s", "Take me to the nearest supermarket", location=HOME))
    assert "destination=37.765000" in first["map_url"]
    navigator._find_place = no_place
    failed = run(make(navigator=navigator, geocode=nowhere).respond("s", "Take me to Atlantis", location=HOME))
    assert "could not find" in failed["say"]
    assert failed["map_url"] is None


def test_a_far_away_place_is_found_on_the_whole_map():
    async def whole_map(text, lat=None, lon=None):
        return {"label": "161, Mission Falls Lane, Fremont", "lat": 37.4845, "lon": -121.9273}

    assistant = make(navigator=Navigator(no_place, fake_route), geocode=whole_map)
    reply = run(assistant.respond("s", "Get directions to 161 Mission Falls Lane Fremont", location=HOME))
    assert reply["navigating"]
    assert "destination=37.484500,-121.927300" in reply["map_url"]


def test_take_me_back_uses_where_the_walk_began():
    assistant = make()
    assert "close to where you started" in run(assistant.respond("s", "Take me back", location=HOME))["say"]
    assistant.track("walker", *SHOP, now=time.time() - 300)
    assistant.track("walker", *CORNER, now=time.time() - 100)
    reply = run(assistant.respond("walker", "Take me back", location=HOME))
    assert "your starting point is" in reply["say"]


def test_a_long_pause_starts_a_new_walk():
    assistant = make()
    assistant.track("s", *HOME, now=1000)
    assistant.track("s", *CORNER, now=1000 + 3600)
    assistant.track("s", *SHOP, now=1000 + 3700)
    assert assistant.trip_start("s", now=1000 + 3750)["lat"] == CORNER[0]
    assert assistant.trip_start("s", now=1000 + 3700 + 3600) is None


def test_saving_home_is_read_back_before_it_is_kept():
    async def geocode(text, lat=None, lon=None):
        return {"label": "161, Mission Falls Lane, Fremont", "lat": 37.4845, "lon": -121.9273}

    family = Family(":memory:")
    assistant = make(family=family, geocode=geocode)
    offer = run(assistant.respond("s", "My home address is 161 Mission Falls Lane Fremont"))
    assert offer["confirm"] == "Save 161, Mission Falls Lane, Fremont as your home?"
    assert family.place("s", "home") is None
    saved = run(assistant.respond("s", "Yes"))
    assert saved["intent"] == "place_saved"
    assert family.place("s", "home")["lat"] == 37.4845
    reply = run(assistant.respond("s", "Take me home", location=HOME))
    assert reply["navigating"]
    assert "Your home is" in reply["say"]
    assert "do not know your work address" in run(assistant.respond("s", "Take me to work", location=HOME))["say"]


def test_navigation_helpers():
    assert abs(navigation.haversine(*HOME, *SHOP) - 489) < 3
    assert navigation.spoken_distance(10) == "a few steps"
    assert navigation.spoken_distance(120) == "400 feet"
    assert navigation.spoken_distance(800) == "0.5 miles"
    assert navigation.destination_query("Take me to the nearest supermarket")[0] == "supermarket"
    assert navigation.destination_query("Where is the closest grocery store?")[0] == "supermarket"
    assert navigation.destination_query("Guide me to Safeway.")[0] == "safeway"
    depart = {"maneuver": {"type": "depart", "bearing_after": 264}, "name": "20th Street", "distance": 120}
    assert navigation.instruction(depart) == "Head west on 20th Street for 400 feet."
    turn = {"maneuver": {"type": "turn", "modifier": "left"}, "name": "Illinois Street", "distance": 150}
    assert navigation.instruction(turn) == "Turn left onto Illinois Street. Then continue for 500 feet."
    assert navigation.instruction({"maneuver": {"type": "arrive"}}) == "You have arrived."


def test_build_route_drops_tiny_connectors_but_keeps_arrival():
    osrm = {"routes": [{"distance": 300, "duration": 240, "legs": [{"steps": [
        {"maneuver": {"type": "depart", "bearing_after": 0, "location": [0, 0]}, "name": "A", "distance": 100},
        {"maneuver": {"type": "turn", "modifier": "right", "location": [0, 1]}, "name": "", "distance": 5},
        {"maneuver": {"type": "turn", "modifier": "left", "location": [0, 2]}, "name": "B", "distance": 195},
        {"maneuver": {"type": "arrive", "location": [0, 3]}, "name": "B", "distance": 0},
    ]}]}]}
    steps = navigation.build_route(osrm)["steps"]
    assert len(steps) == 3
    assert steps[-1]["say"] == "You have arrived."


def test_route_is_spoken_turn_by_turn():
    navigator = Navigator(fake_place, fake_route)
    intro = run(navigator.start("s", "Take me to the nearest supermarket", *HOME))
    assert "Safeway is 0.3 miles away, about 6 minutes on foot." in intro
    assert "do not mean a crossing is safe" in intro
    assert navigator.update("s", 37.7612, HOME[1])["say"] is None
    assert "Turn left onto Illinois" in navigator.update("s", *CORNER)["say"]
    assert navigator.update("s", *CORNER)["say"] is None
    arrived = navigator.update("s", 37.76485, SHOP[1])
    assert (arrived["say"], arrived["active"]) == ("You have arrived at Safeway.", False)
    assert navigator.update("s", *SHOP) == {"active": False, "say": None}


def test_unknown_place_and_stop():
    navigator = Navigator(no_place, fake_route)
    with pytest.raises(navigation.NavigationError):
        run(navigator.start("s", "Take me to Atlantis", *HOME))
    assert not navigator.stop("s")
