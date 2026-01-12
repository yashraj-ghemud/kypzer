def inspect(label, func, phrases):
    print(f"=== {label} ===")
    for phrase in phrases:
        res = func(phrase)
        print(phrase)
        print(res)
        print('-' * 60)


from src.assistant.nlu import interpret as nlu_interpret
from src.main import interpret as main_interpret

samples = [
    "describe my screen",
    "toggle airplane mode",
    "awaz thoda kam karo",
    "open chrome and search best laptops under 50k and click on first link",
    "open chrome and search python on stackoverflow",
    "send gm to mummy, papa and yashraj on whatsapp",
    "send info of stokes theorem to aai with ai",
]

inspect("NLU", nlu_interpret, samples)
inspect("MAIN", main_interpret, samples)
