from app.voice.languages import normalize_language, normalize_supported, phrase, spoken_amount


def test_phrase_english_and_unknown_key():
    assert phrase("opening_question", "en", customer_name="Rahim") == "Am I speaking with Rahim?"
    assert phrase("still_there", "xx") == phrase("still_there", "en")  # unknown code → English
    assert phrase("no_such_key", "en") == ""
    assert "{customer_name}" in phrase("opening_question", "en")  # missing field never raises


def test_retired_language_code_reads_as_english():
    # Accounts saved before English became the only language may still carry "bn".
    assert normalize_language("bn") == "en"
    assert phrase("still_there", "bn") == phrase("still_there", "en")
    assert normalize_supported("bn", ["bn", "en"]) == ["en"]


def test_spoken_amounts():
    assert spoken_amount("1850.00", "USD", "en") == "1850 dollars"
    assert spoken_amount("12.50", "USD", "en") == "12 dollars and 50 cents"
    assert spoken_amount("89.50", "GBP", "en") == "89 pounds and 50 pence"
    assert spoken_amount("120") == "120 dollars"
    assert spoken_amount("garbage", "USD") == "0 dollars"
    assert spoken_amount("15", "XYZ") == "15 XYZ"


def test_normalize_supported_keeps_primary_first():
    assert normalize_supported("en", ["en", "xx"]) == ["en"]
    assert normalize_supported(None, None) == ["en"]
