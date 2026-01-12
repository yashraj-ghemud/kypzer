from src.assistant.ai_notepad_workflow import ResponseCleaner, WorkflowConfig, CleaningRule


def test_cleaner_removes_ui_noise_from_chatgpt_copy():
    config = WorkflowConfig()
    cleaner = ResponseCleaner(config)
    topic = "info info about Diwali"
    prompt = config.prompt_template.format(topic=topic)
    raw = (
        "info info about Diwali\n"
        "- Skip to content\n"
        "Please write concise, friendly notes about info info about diwali. Use 5-9 bullet points or short paragraphs with tips and examples. Avoid disclaimers, headings, markdown, or repetition.\n"
        "Diwali is the festival of lights, celebrated by millions across India and the world. It marks the victory of light over darkness and good over evil.\n\n"
        "People clean and decorate their homes with colorful rangolis, oil lamps, and fairy lights to welcome positive energy.\n\n"
        "Families gather to worship Goddess Lakshmi, the deity of wealth and prosperity, and Lord Ganesha for wisdom and success.\n\n"
        "Firecrackers, though traditional, are now often replaced by eco-friendly celebrations to reduce pollution and noise.\n\n"
        "Delicious sweets like laddoos, barfis, and gulab jamuns are shared with friends and neighbors as tokens of love.\n\n"
        "New clothes, gifts, and heartfelt greetings make the festival vibrant and joyful.\n\n"
        "Many also donate to charity or help those in need, symbolizing kindness and sharing.\n\n"
        "Each region celebrates Diwali a bit differently-some link it to Lord Rama's return to Ayodhya, others to Lord Krishna's victory over Narakasura-but all share the spirit of renewal and light.\n\n"
        "- No file chosenNo file chosen\n"
        "ChatGPT can make mistakes. Check important info. See Cookie Preferences.- Skip to ntent\n"
        "se ite ncise,endly bout  nfo ut ali.e bullet points or short paragraphs with tips and examples. Avoid disclaimers, headings, markdown,r ition.wali stival ights,ated ons ss dia d e world. It marks ictory ght  rkness good r evil.People nd corate homes th orful ngolis,il , and fairy lights to welcome positive energy.\n\n"
        "es ather worship dess shmi, eity ealth rosperity, anesha sdom uccess.recrackers,ditional,ten  y eco-friendly celebrations to reduce pollution and noise.\n"
    )
    cleaned, steps = cleaner.clean(topic, raw, prompt=prompt)
    assert CleaningRule.STRIP_PAGE_CHROME in steps
    assert "Skip to content" not in cleaned
    assert "No file chosen" not in cleaned
    expected = (
        "Diwali is the festival of lights, celebrated by millions across India and the world. It marks the victory of light over darkness and good over evil.\n\n"
        "People clean and decorate their homes with colorful rangolis, oil lamps, and fairy lights to welcome positive energy.\n\n"
        "Families gather to worship Goddess Lakshmi, the deity of wealth and prosperity, and Lord Ganesha for wisdom and success.\n\n"
        "Firecrackers, though traditional, are now often replaced by eco-friendly celebrations to reduce pollution and noise.\n\n"
        "Delicious sweets like laddoos, barfis, and gulab jamuns are shared with friends and neighbors as tokens of love.\n\n"
        "New clothes, gifts, and heartfelt greetings make the festival vibrant and joyful.\n\n"
        "Many also donate to charity or help those in need, symbolizing kindness and sharing.\n\n"
        "Each region celebrates Diwali a bit differently-some link it to Lord Rama's return to Ayodhya, others to Lord Krishna's victory over Narakasura-but all share the spirit of renewal and light."
    )
    assert cleaned.strip() == expected.strip()


def test_cleaner_strips_conversation_header():
    config = WorkflowConfig()
    cleaner = ResponseCleaner(config)
    topic = "facts about mars"
    prompt = config.prompt_template.format(topic=topic)
    raw = (
        "- Chat history\n\n"
        "- You said:\n\n"
        "- ChatGPT said:\n"
        "Mars is the fourth planet from the Sun.\n"
        "It has two small moons called Phobos and Deimos.\n"
    )
    cleaned, steps = cleaner.clean(topic, raw, prompt=prompt)
    assert CleaningRule.STRIP_CONVERSATION_HEADER in steps
    first_line = cleaned.splitlines()[0]
    assert "Mars is the fourth planet" in first_line
    assert "Chat history" not in cleaned
    assert "You said" not in cleaned
