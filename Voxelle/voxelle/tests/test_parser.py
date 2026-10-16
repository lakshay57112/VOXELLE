from app.parser import parse_schedule, readback


def simple(items):
    return [(i["medicine"], i["time"], i["slot"], i["food"]) for i in items]


def test_two_medicines_hinglish():
    items = parse_schedule("Papa ko subah BP ki goli khaane ke baad, raat ko sugar ki goli")
    assert simple(items) == [
        ("BP ki goli", "08:00", "subah", "after"),
        ("Sugar ki goli", "21:00", "raat", "any"),
    ]


def test_one_medicine_two_slots():
    items = parse_schedule("subah aur raat ko BP ki goli")
    assert simple(items) == [
        ("BP ki goli", "08:00", "subah", "any"),
        ("BP ki goli", "21:00", "raat", "any"),
    ]


def test_trailing_slots_attach_to_previous_medicine():
    items = parse_schedule("thyroid ki goli, subah aur shaam")
    assert [(i["time"], i["slot"]) for i in items] == [("08:00", "subah"), ("18:00", "shaam")]
    assert all(i["medicine"] == "Thyroid ki goli" for i in items)


def test_explicit_times_with_slots():
    items = parse_schedule("subah 7:30 baje thyroid ki goli khali pet, raat 9 baje sugar ki goli")
    assert simple(items) == [
        ("Thyroid ki goli", "07:30", "subah", "before"),
        ("Sugar ki goli", "21:00", "raat", "any"),
    ]


def test_evening_time_is_pm():
    items = parse_schedule("shaam 6 baje BP ki goli")
    assert items[0]["time"] == "18:00"


def test_am_pm():
    items = parse_schedule("BP ki goli 8 am aur calcium tablet 2 pm")
    assert simple(items) == [
        ("BP ki goli", "08:00", "subah", "any"),
        ("Calcium tablet", "14:00", "dopahar", "any"),
    ]


def test_before_food():
    items = parse_schedule("subah khaane se pehle sugar ki goli")
    assert items[0]["food"] == "before"


def test_devanagari():
    items = parse_schedule("सुबह बीपी की गोली खाने के बाद और रात को शुगर की गोली")
    assert len(items) == 2
    assert items[0]["slot"] == "subah" and items[0]["food"] == "after"
    assert items[1]["slot"] == "raat"
    assert "बीपी" in items[0]["medicine"] and "शुगर" in items[1]["medicine"]


def test_hindi_number_word_time():
    items = parse_schedule("subah aath baje BP ki goli")
    assert items[0]["time"] == "08:00"


def test_english():
    items = parse_schedule("BP tablet in the morning after food and sugar tablet at night")
    assert [(i["slot"], i["food"]) for i in items] == [("subah", "after"), ("raat", "any")]


def test_empty_and_noise():
    assert parse_schedule("") == []
    assert parse_schedule("aaj mausam accha hai") == []
    assert "dobara" in readback([])


def test_readback_text():
    items = parse_schedule("subah BP ki goli khaane ke baad")
    text = readback(items, "Papa")
    assert text.startswith("Papa ke liye:")
    assert "Subah 8 baje" in text and "khaane ke baad" in text and text.endswith("Kya yeh sahi hai?")


def test_duplicates_removed():
    items = parse_schedule("subah BP ki goli, subah BP ki goli")
    assert len(items) == 1
