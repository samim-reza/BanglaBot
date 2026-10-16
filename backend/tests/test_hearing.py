from app.flows import hearing


def test_yes_and_no():
    for text in ("yes", "yeah sure", "ok confirm it", "no problem, send it", "sure, go ahead", "absolutely"):
        assert hearing.supports(text, "confirm"), text
        assert not hearing.supports(text, "cancel"), text
    for text in ("no", "nope, cancel it", "I didn't order this", "don't want it", "cancel"):
        assert hearing.supports(text, "cancel"), text
        assert not hearing.supports(text, "confirm"), text


def test_phrase_outweighs_lone_word():
    assert hearing.supports("no, go ahead", "confirm")
    assert hearing.supports("yes, I don't need it", "cancel")
    assert hearing.supports("yes cancel it", "cancel")


def test_later_is_neither_confirm_nor_cancel():
    for text in ("call me later", "not now, call me back", "I'm busy right now"):
        assert hearing.supports(text, "later"), text
        assert not hearing.supports(text, "confirm"), text
        assert not hearing.supports(text, "cancel"), text
    assert not hearing.supports("yes, but later", "confirm")


def test_identity_denials():
    for text in ("not me, I'm his brother", "I don't know them", "wrong number", "this is not Rahim", "he's not here"):
        assert hearing.denies_identity(text), text
        assert not hearing.supports(text, "confirm"), text
        # Identity talk never counts as an order decision.
        assert not hearing.supports(text, "cancel"), text
    assert hearing.supports("I don't know them", "wrong_number")
    assert hearing.supports("I'm his brother, I'll tell him", "knows")
    assert not hearing.denies_identity("yes, speaking")
    assert hearing.supports("speaking", "is_me")
    assert hearing.supports("yes", "is_me")


def test_questions_are_not_answers():
    assert not hearing.supports("should I confirm it", "confirm")
    assert not hearing.supports("Would you like to confirm the order?", "confirm")
    assert hearing.looks_like_question("Is this Rahim Uddin?")


def test_unusable_lines():
    assert hearing.is_unusable("")
    assert hearing.is_unusable("hmm")
    assert hearing.is_unusable("uh um hmm")
    assert hearing.is_unusable("Thank you for watching")
    assert hearing.is_unusable("the the the the the the the")
    assert not hearing.is_unusable("no no no I don't want it")  # emphatic, real
    assert not hearing.is_unusable("yes")


def test_echo_and_prompt_echo_filters():
    agent = ["Am I speaking with Rahim Uddin?"]
    assert hearing.echoes_agent_line("am I speaking with Rahim Uddin", agent)
    assert not hearing.echoes_agent_line("yes speaking", agent)  # short answers survive
    prompt = "Phone call. Yes, no, okay, sure, cancel, later, wrong number."
    assert hearing.is_prompt_echo("phone call yes no okay", prompt)
    assert not hearing.is_prompt_echo("yes", prompt)


def test_echo_guard_needs_the_agent_words_in_order():
    from app.flows.hearing import echoes_agent_line

    agent = ["Hello, this is Demo Shop calling. Am I speaking with Nusrat Jahan?"]
    assert echoes_agent_line("Am I speaking with Nusrat Jahan", agent)  # our own question coming back
    assert not echoes_agent_line("Yes, this is Nusrat speaking", agent)  # a real answer reusing the words


def test_everyday_english_affirmatives_and_their_negations():
    for text in ("Perfect", "Great", "Sounds great", "That works", "Yes please"):
        assert hearing.supports(text, "confirm"), text
    for text in ("not great", "not really", "not that day"):
        assert not hearing.supports(text, "confirm"), text
