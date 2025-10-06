from typing import Iterable

_pairs: Iterable[tuple[str, str]] = [
    ("shch", "щ"), ("yo", "ё"), ("yu", "ю"), ("ya", "я"), ("zh", "ж"), ("ch", "ч"), ("sh", "ш"),
    ("ts", "ц"), ("kh", "х"), ("yi", "ы"), ("ye", "е"), ("e", "е"), ("y", "й"),
]
_single = {
    "a":"а","b":"б","v":"в","g":"г","d":"д","e":"е","z":"з","i":"и","j":"й","k":"к","l":"л","m":"м","n":"н","o":"о","p":"п","r":"р","s":"с","t":"т","u":"у","f":"ф","h":"х","c":"к","q":"к","w":"в","x":"кс"
}

def latin_to_cyr(text: str) -> str:
    s = text
    lower = s.lower()
    for lat, cyr in _pairs:
        lower = lower.replace(lat, cyr)
    out = []
    for ch in lower:
        out.append(_single.get(ch, ch))
    result = "".join(out)
    if s and s[0].isupper():
        result = result[:1].upper() + result[1:]
    return result
