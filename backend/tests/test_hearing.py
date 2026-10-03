from app.flows import hearing


def test_bangla_yes_and_no():
    for text in ("হ্যাঁ", "জি", "জি, ঠিক আছে", "হ্যাঁ কনফার্ম করেন", "পাঠিয়ে দেন", "অবশ্যই"):
        assert hearing.supports(text, "confirm"), text
        assert not hearing.supports(text, "cancel"), text
    for text in ("না", "লাগবে না", "না, বাতিল করে দেন", "অর্ডার করিনি", "ক্যান্সেল"):
        assert hearing.supports(text, "cancel"), text
        assert not hearing.supports(text, "confirm"), text


def test_english_and_romanised_answers():
    for text in ("yes", "yeah sure", "ok confirm it", "no problem, send it", "ji", "thik ache"):
        assert hearing.supports(text, "confirm"), text
    for text in ("no", "nope, cancel it", "I didn't order this", "lagbe na", "don't want it"):
        assert hearing.supports(text, "cancel"), text


def test_phrase_outweighs_lone_word():
    assert hearing.supports("না, ঠিক আছে", "confirm")
    assert hearing.supports("হ্যাঁ, লাগবে না", "cancel")
    assert hearing.supports("yes cancel it", "cancel")


def test_later_is_neither_confirm_nor_cancel():
    for text in ("পরে কল দিয়েন", "এখন না, একটু পরে", "call me later", "I'm busy right now"):
        assert hearing.supports(text, "later"), text
        assert not hearing.supports(text, "confirm"), text
        assert not hearing.supports(text, "cancel"), text
    assert not hearing.supports("হ্যাঁ, কিন্তু পরে", "confirm")


def test_identity_denials():
    for text in ("আমি না, ওর ভাই", "চিনি না", "রং নাম্বার", "this is not Rahim", "wrong number", "he's not here"):
        assert hearing.denies_identity(text), text
        assert not hearing.supports(text, "confirm"), text
        # Identity talk never counts as an order decision.
        assert not hearing.supports(text, "cancel"), text
    assert hearing.supports("চিনি না", "wrong_number")
    assert hearing.supports("আমি ওর ভাই, বলে দিব", "knows")
    assert not hearing.denies_identity("জি বলছি")
    assert hearing.supports("speaking", "is_me")
    assert hearing.supports("হ্যাঁ", "is_me")


def test_questions_are_not_answers():
    assert not hearing.supports("অর্ডারটি কনফার্ম করবেন কি", "confirm")
    assert not hearing.supports("Would you like to confirm the order?", "confirm")
    assert hearing.looks_like_question("আপনি কি রাহিম সাহেব কি")


def test_unusable_lines():
    assert hearing.is_unusable("")
    assert hearing.is_unusable("হুম")
    assert hearing.is_unusable("uh um hmm")
    assert hearing.is_unusable("Thank you for watching")
    assert hearing.is_unusable("যা যা যা যা যা যা যা")
    assert not hearing.is_unusable("না না না লাগবে না")  # emphatic, real
    assert not hearing.is_unusable("হ্যাঁ")


def test_echo_and_prompt_echo_filters():
    agent = ["আমি কি রাহিম উদ্দিন-এর সাথে কথা বলছি?"]
    assert hearing.echoes_agent_line("আমি কি রাহিম উদ্দিন এর সাথে কথা বলছি", agent)
    assert not hearing.echoes_agent_line("হ্যাঁ বলছি", agent)  # short answers survive
    prompt = "অর্ডার কনফার্মেশনের ফোন কল। হ্যাঁ, না, জি, ঠিক আছে, বাতিল, পরে, রং নাম্বার।"
    assert hearing.is_prompt_echo("অর্ডার কনফার্মেশনের ফোন কল হ্যাঁ না জি", prompt)
    assert not hearing.is_prompt_echo("হ্যাঁ", prompt)


def test_echo_guard_needs_the_agent_words_in_order():
    from app.flows.hearing import echoes_agent_line

    agent = ["Hello, this is Demo Shop calling. Am I speaking with Nusrat Jahan?"]
    assert echoes_agent_line("Am I speaking with Nusrat Jahan", agent)  # our own question coming back
    assert not echoes_agent_line("Yes, this is Nusrat speaking", agent)  # a real answer reusing the words
    agent_bn = ["আসসালামু আলাইকুম। আমি কেনা শপ থেকে বলছি। আমি কি শামীম রেজা-এর সাথে কথা বলছি?"]
    assert echoes_agent_line("আমি কি শামীম রেজা-এর সাথে কথা বলছি", agent_bn)
    assert not echoes_agent_line("হ্যাঁ আমি শামীম রেজা বলছি ভাই", agent_bn)


def test_everyday_english_affirmatives_and_their_negations():
    for text in ("Perfect", "Great", "Sounds great", "That works", "Yes please"):
        assert hearing.supports(text, "confirm"), text
    for text in ("not great", "not really", "not that day"):
        assert not hearing.supports(text, "confirm"), text
