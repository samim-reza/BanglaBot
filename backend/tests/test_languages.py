from app.voice.languages import bangla_number_words, detect_language, normalize_supported, phrase, spoken_amount


def test_phrase_bangla_and_english_and_unknown_key():
    assert "রাহিম" in phrase("opening_question", "bn", customer_name="রাহিম")
    assert phrase("opening_question", "en", customer_name="Rahim") == "Am I speaking with Rahim?"
    assert phrase("still_there", "xx") == phrase("still_there", "bn")  # unknown code → primary (Bangla)
    assert phrase("no_such_key", "bn") == ""
    assert "{customer_name}" in phrase("opening_question", "bn")  # missing field never raises


def test_detect_language_by_script_share():
    assert detect_language("জি, আমি বলছি") == "bn"
    assert detect_language("হ্যাঁ, Cotton saree টা রাখব") == "bn"
    assert detect_language("Yes, this is Rahim speaking") == "en"
    assert detect_language("ok") is None
    assert detect_language("") is None
    assert detect_language("Yes speaking", supported=["bn"]) is None


def test_bangla_numbers_and_amounts():
    assert bangla_number_words(0) == "শূন্য"
    assert bangla_number_words(1850) == "এক হাজার আটশো পঞ্চাশ"
    assert bangla_number_words(250000) == "দুই লাখ পঞ্চাশ হাজার"
    assert spoken_amount("1850.00", "BDT", "bn") == "এক হাজার আটশো পঞ্চাশ টাকা"
    assert spoken_amount("1850.50", "BDT", "bn") == "এক হাজার আটশো পঞ্চাশ টাকা পঞ্চাশ পয়সা"
    assert spoken_amount("1850.00", "BDT", "en") == "1850 taka"
    assert spoken_amount("12.50", "BDT", "en") == "12 taka and 50 poisha"
    assert spoken_amount("89.50", "GBP", "en") == "89 pounds and 50 pence"
    assert spoken_amount("120", "USD", "en") == "120 dollars"
    assert spoken_amount("garbage", "BDT", "bn") == "শূন্য টাকা"


def test_normalize_supported_keeps_primary_first():
    assert normalize_supported("en", ["bn", "en", "xx"]) == ["en", "bn"]
    assert normalize_supported(None, None) == ["bn"]


def test_detect_language_ignores_loanwords_and_single_english_words():
    from app.voice.languages import detect_language

    for text in ("Okay.", "ok", "Yes", "Hello?", "ok thanks", "confirm", "Okay, yes"):
        assert detect_language(text, supported=["bn", "en"]) is None, text
    assert detect_language("Yes, this is Nusrat speaking", supported=["bn", "en"]) == "en"
    assert detect_language("I want to cancel this order", supported=["bn", "en"]) == "en"
    assert detect_language("হ্যাঁ, ওকে confirm", supported=["bn", "en"]) == "bn"


def test_english_word_count_ignores_loanwords():
    from app.voice.languages import english_word_count

    assert english_word_count("Okay, yes") == 0
    assert english_word_count("Do you bulletin?") == 3
    assert english_word_count("Yes, this is Nusrat speaking") == 4
