"""
Language intelligence service for WeatherGPT.

Provides deterministic script inspection, transliteration pattern recognition,
and multilingual keyword matching to support English, Hindi (Devanagari),
Roman Hindi (Hinglish), and Konkani naturally.
"""

import re
from services.language.bhashini_service import bhashini

# Common Roman Hindi (Hinglish) markers and vocabulary
HINGLISH_WORDS = {
    "kya", "hai", "hain", "hogi", "hoga", "honge", "karein", "karna", "karu",
    "khet", "kheti", "fasal", "fasle", "paani", "pani", "aaj", "kal", "parso",
    "kaisa", "kaisi", "kaise", "mausam", "mosam", "kisan", "dawai", "chhidkaw",
    "theek", "sahi", "rahega", "rahegi", "batao", "bataye", "chahiye", "rahi",
    "raha", "bahut", "dhoop", "garmi", "thand", "hawa", "kitna", "kitni", "kab",
    "meri", "mera", "mere", "iss", "hum", "aap", "muje", "mujhe", "baarish",
    "barish", "bhi", "toh", "lagana", "bona", "katna", "sinchai", "dophar",
    "shaam", "subah", "bijli", "toofan", "baadh", "loo", "chetavani"
}

KONKANI_DEVANAGARI_MARKERS = {
    "पावस", "हवामान", "शेतकार", "सल्लो", "फाल्या", "न्हय", "आसा", "आयचें",
    "इशारो", "विशीं", "उतरांनी", "सद्या", "कसलोच", "पडटलो", "मारचें"
}

MARATHI_DEVANAGARI_MARKERS = {
    "पाऊस", "शेतकरी", "सल्ला", "उद्या", "नाही", "आहे", "आजचे",
    "इशारा", "फवारणी", "कधी", "होईल", "कसा", "कशी", "काढणी", "पेरणी"
}

# Multilingual keywords for domain routing (Devanagari, Roman Hindi, and English)
ALERT_KEYWORDS = [
    # English
    "alert", "warning", "cyclone", "flood", "flooding", "heatwave",
    "lightning", "storm", "disaster", "danger", "evacuate",
    # Hindi Devanagari
    "चेतावनी", "अलर्ट", "चक्रवात", "तूफ़ान", "तूफान", "बाढ़", "लू", "बिजली", "ख़तरा", "खतरा", "आपदा",
    # Konkani Devanagari & Roman
    "इशारो", "isharo",
    # Roman Hindi / Hinglish
    "chetavani", "toofan", "baadh", "badh", "bijli", "khatra", "aapad", "cyclone", "loo"
]

AGRICULTURE_KEYWORDS = [
    # English
    "crop", "crops", "plant", "planting", "farmer", "farming", "farm",
    "rice", "paddy", "wheat", "cotton", "tomato", "onion", "harvest",
    "harvesting", "irrigation", "irrigate", "spray", "pesticide",
    "fertilizer", "sowing", "soil", "orchard", "fruit",
    # Hindi Devanagari
    "फसल", "फ़सल", "खेती", "किसान", "छिड़काव", "दवाई", "दवा", "कीटनाशक", "खाद",
    "बोना", "बुवाई", "कटाई", "सिंचाई", "धान", "चावल", "गेहूं", "गेहूँ", "कपास",
    "टमाटर", "प्याज", "प्याज़", "सब्जी", "सब्जियां", "खेत", "बाग",
    # Konkani Devanagari & Roman
    "शेतकार", "सल्लो", "मारचें", "पिक", "shetkar", "sallo",
    # Roman Hindi / Hinglish
    "fasal", "phasal", "kheti", "kisan", "chhidkaw", "dawai", "keetnashak",
    "khad", "bona", "buwai", "katai", "sinchai", "dhan", "chawal", "gehun",
    "gehu", "kapas", "tamatar", "pyaz", "sabji", "khet"
]

WEATHER_KEYWORDS = [
    # English
    "weather", "rain", "rainfall", "temperature", "hot", "cold", "wind",
    "humidity", "forecast", "cloud", "sunny", "umbrella", "picnic",
    "travel", "outdoor", "today", "tomorrow", "weekend", "shower",
    "drizzle", "monsoon", "climate", "fishing", "sail", "wear",
    # Hindi Devanagari
    "मौसम", "बारिश", "बरसात", "वर्षा", "तापमान", "गरमी", "गर्मी", "ठंड",
    "सर्दी", "हवा", "नमी", "बादल", "धूप", "छाता", "कल", "आज", "परसों",
    "हफ्ते", "सप्ताह", "घूमने", "पिकनिक", "यात्रा", "कपड़े",
    # Konkani Devanagari & Roman
    "पावस", "पावतलो", "पडटलो", "हवामान", "फाल्या", "आयचें", "paavs", "paavatlo", "havaman", "falya", "falyan",
    # Roman Hindi / Hinglish
    "mausam", "mosam", "baarish", "barish", "barsat", "tapman", "garmi",
    "thand", "sardi", "hawa", "nami", "baadal", "badal", "dhoop", "chata",
    "chhaata", "aaj", "kal", "parso", "hafte", "ghoomne", "picnic", "kapde"
]


def detect_language(query: str, requested_lang: str | None = None) -> str:
    """
    Deterministically detect the language of the user's query.
    Supports all 11 Indian languages: en, hi, mr, gu, bn, ta, te, kn, ml, pa, or, plus hi-Latn and kok.
    """
    valid_langs = {"en", "hi", "mr", "gu", "bn", "ta", "te", "kn", "ml", "pa", "or", "kok"}

    if not query or not query.strip():
        return requested_lang if requested_lang in valid_langs else "en"

    text = query.strip()

    # 1. Check for distinct Indian Unicode scripts (>= 2 chars)
    if len(re.findall(r"[\u0A80-\u0AFF]", text)) >= 2:
        return "gu"
    if len(re.findall(r"[\u0980-\u09FF]", text)) >= 2:
        return "bn"
    if len(re.findall(r"[\u0B80-\u0BFF]", text)) >= 2:
        return "ta"
    if len(re.findall(r"[\u0C00-\u0C7F]", text)) >= 2:
        return "te"
    if len(re.findall(r"[\u0C80-\u0CFF]", text)) >= 2:
        return "kn"
    if len(re.findall(r"[\u0D00-\u0D7F]", text)) >= 2:
        return "ml"
    if len(re.findall(r"[\u0A00-\u0A7F]", text)) >= 2:
        return "pa"
    if len(re.findall(r"[\u0B00-\u0B7F]", text)) >= 2:
        return "or"

    # 2. Check for Devanagari script (U+0900 to U+097F)
    devanagari_chars = len(re.findall(r"[\u0900-\u097F]", text))
    if devanagari_chars >= 2:
        # Check if Konkani-specific marker words appear
        if any(marker in text for marker in KONKANI_DEVANAGARI_MARKERS) or requested_lang == "kok":
            return "kok"
        # Check if Marathi-specific marker words appear
        if any(marker in text for marker in MARATHI_DEVANAGARI_MARKERS) or requested_lang == "mr":
            return "mr"
        return "hi"

    # 3. Check for Roman Hindi / Hinglish in Latin script
    tokens = [t.lower() for t in re.findall(r"\b[a-zA-Z]+\b", text)]
    hinglish_match_count = sum(1 for t in tokens if t in HINGLISH_WORDS)

    # If at least 2 Hinglish words, or 1 Hinglish word in a short query (<= 5 tokens)
    if hinglish_match_count >= 2 or (hinglish_match_count >= 1 and len(tokens) <= 5):
        return "hi-Latn"

    # Check common Hinglish phrase structures like "kya ... hoga", "karna sahi rahega"
    text_lower = text.lower()
    if any(phrase in text_lower for phrase in ["kya", "hogi", "hoga", "sahi rahega", "theek hoga", "kaisa rahega", "baarish hogi"]):
        return "hi-Latn"

    # 4. Fallback to requested language if explicitly provided and valid
    if requested_lang in valid_langs:
        return requested_lang

    # 5. Default to English
    return "en"



def classify_multilingual_query(query: str, history: list[dict] | None = None) -> str:
    """
    Deterministic multilingual keyword matching to classify questions into:
    'alert' | 'agriculture' | 'weather' | 'general'
    Supports English, Devanagari Hindi, Roman Hindi (Hinglish), and Konkani.
    If query is ambiguous or a short follow-up, uses recent conversation history.
    """
    q_lower = query.lower()

    # Priority 1: Alert
    if any(kw in q_lower for kw in ALERT_KEYWORDS):
        return "alert"

    # Priority 2: Agriculture
    if any(kw in q_lower for kw in AGRICULTURE_KEYWORDS):
        return "agriculture"

    # Priority 3: Weather
    if any(kw in q_lower for kw in WEATHER_KEYWORDS):
        return "weather"

    # If short follow-up query and history exists, inherit previous domain
    if history and len(history) > 0:
        # Check last 1-2 messages
        for prev in reversed(history[-2:]):
            prev_content = str(prev.get("content", "") or prev.get("answer", "") or prev.get("query", "")).lower()
            if any(kw in prev_content for kw in AGRICULTURE_KEYWORDS):
                return "agriculture"
            if any(kw in prev_content for kw in WEATHER_KEYWORDS):
                return "weather"

    return "general"


# Multilingual Weather Condition Translations
WEATHER_CONDITIONS_I18N = {
    "clear sky": {
        "hi": "साफ़ आसमान", "mr": "निरभ्र आकाश", "gu": "સ્વચ્છ આકાશ", "bn": "পরিষ্কার আকাশ",
        "ta": "தெளிவான வானம்", "te": "నిర్మలమైన ఆకాశం", "kn": "ಸ್ವಚ್ಛ ಆಕಾಶ", "ml": "തെളിഞ്ഞ ആകാശം",
        "pa": "ਸਾਫ਼ ਅਸਮਾਨ", "or": "ନିର୍ମଳ ଆକାଶ", "kok": "nitol aakash"
    },
    "sunny": {
        "hi": "धूप खिली रहेगी", "mr": "सूर्यप्रकाश / ऊन", "gu": "તડકો", "bn": "রৌদ্রোজ্জ্বল",
        "ta": "வெயில்", "te": "ఎండగా ఉంది", "kn": "ಬಿಸಿಲು", "ml": "വെയിൽ",
        "pa": "ਧੁੱਪ", "or": "ଖରାଟିଆ", "kok": "chodd dhoop"
    },
    "mainly clear": {
        "hi": "मुख्य रूप से साफ़ आसमान", "mr": "बहुतांशी निरभ्र", "gu": "મોટેભાગે સ્વચ્છ", "bn": "বেশিরভাগ পরিষ্কার",
        "ta": "பெரும்பாலும் தெளிவான வானம்", "te": "ఎక్కువగా నిర్మలంగా ఉంది", "kn": "ಹೆಚ್ಚಾಗಿ ಸ್ವಚ್ಛ", "ml": "പ്രധാനമായും തെളിഞ്ഞത്",
        "pa": "ਮੁੱਖ ਤੌਰ ਤੇ ਸਾਫ਼", "or": "ମୁଖ୍ୟତଃ ନିର୍ମଳ", "kok": "sadharon nitol"
    },
    "partly cloudy": {
        "hi": "आंशिक रूप से बादल", "mr": "अंशतः ढगाळ", "gu": "અંશતઃ વાદળછાયું", "bn": "আংশিক মেঘলা",
        "ta": "பகுதி மேகமூட்டம்", "te": "పాక్షికంగా మేఘావృతం", "kn": "ಭಾಗಶಃ ಮೋಡ ಕವಿದ", "ml": "ഭാഗികമായി മേഘാവൃതമായ",
        "pa": "ਅੰਸ਼ਕ ਤੌਰ ਤੇ ਬੱਦਲਵਾਈ", "or": "ଆଂଶିକ ମେଘୁଆ", "kok": "thodde kupam"
    },
    "cloudy": {
        "hi": "बादल छाए हुए हैं", "mr": "ढगाळ वातावरण", "gu": "વાદળછાયું", "bn": "মেঘলা",
        "ta": "மேகமூட்டம்", "te": "మేఘావృతం", "kn": "ಮೋಡ ಕವಿದ", "ml": "മേഘാവൃതമായ",
        "pa": "ਬੱਦਲਵਾਈ", "or": "ମେଘୁଆ", "kok": "kupacho dis"
    },
    "overcast": {
        "hi": "घने बादल", "mr": "पूर्ण ढगाळ वातावरण", "gu": "સંપૂર્ણ વાદળછાયું", "bn": "মেঘাচ্ছন্ন",
        "ta": "முழு மேகமூட்டம்", "te": "పూర్తిగా మేఘావృతం", "kn": "ಸಂಪೂರ್ಣ ಮೋಡ ಕವಿದ", "ml": "പൂർണ്ണമായും മേഘാവൃതമായ",
        "pa": "ਘਣੇ ਬੱਦਲ", "or": "ଘନ ମେଘାଚ୍ଛନ୍ନ", "kok": "chodd kupam"
    },
    "fog": {
        "hi": "कोहरा", "mr": "धुके", "gu": "ધુમ્મસ", "bn": "কুয়াশা",
        "ta": "பனிமூட்டம்", "te": "పొగమంచు", "kn": "ದಟ್ಟ ಮಂಜು", "ml": "മൂടൽമഞ്ഞ്",
        "pa": "ਧੁੰਦ", "or": "କୁହୁଡ଼ି", "kok": "dhuvari"
    },
    "mist": {
        "hi": "हल्का कोहरा या धुंध", "mr": "हलके धुके", "gu": "હળવું ધુમ્મસ", "bn": "হালকা কুয়াশা",
        "ta": "மெல்லிய பனி", "te": "తేలికపాటి పొగమంచు", "kn": "ತೆಳುವಾದ ಮಂಜು", "ml": "നേർത്ത മൂടൽമഞ്ഞ്",
        "pa": "ਹਲਕੀ ਧੁੰਦ", "or": "ହାଲୁକା କୁହୁଡ଼ି", "kok": "dhuvari"
    },
    "light drizzle": {
        "hi": "हल्की बूंदाबांदी", "mr": "हलकी रिमझिम", "gu": "હળવી ઝરમર", "bn": "হালকা গুঁড়ি গুঁড়ি বৃষ্টি",
        "ta": "லேசான தூறல்", "te": "తేలికపాటి చినుకులు", "kn": "ಹಗುರವಾದ ಹನಿ ಮಳೆ", "ml": "നേർത്ത ചാറ്റൽമഴ",
        "pa": "ਹਲਕੀ ਬੂੰਦਾ-ਬਾਂਦੀ", "or": "ହାଲୁକା ଝିପିଝିପି ବର୍ଷା", "kok": "barik paavs"
    },
    "moderate drizzle": {
        "hi": "मध्यम बूंदाबांदी", "mr": "मध्यम रिमझिम", "gu": "મધ્યમ ઝરમર", "bn": "মাঝারি গুঁড়ি গুঁড়ি বৃষ্টি",
        "ta": "மிதமான தூறல்", "te": "మధ్యస్థ చినుకులు", "kn": "ಮಧ್ಯಮ ಹನಿ ಮಳೆ", "ml": "മിതമായ ചാറ്റൽമഴ",
        "pa": "ਦਰਮਿਆਨੀ ਬੂੰਦਾ-ਬਾਂਦੀ", "or": "ମଧ୍ୟମ ଝିପିଝିପି ବର୍ଷା", "kok": "modhyom paavs"
    },
    "dense drizzle": {
        "hi": "तेज बूंदाबांदी", "mr": "दाट रिमझिम पाऊस", "gu": "તીવ્ર ઝરમર વરસાદ", "bn": "ঘন গুঁড়ি গুঁড়ি বৃষ্টি",
        "ta": "அடர்த்தியான தூறல்", "te": "తీవ్రమైన చినుకులు", "kn": "ದಟ್ಟ ಹನಿ ಮಳೆ", "ml": "കനത്ത ചാറ്റൽമഴ",
        "pa": "ਤੇਜ਼ ਬੂੰਦਾ-ਬਾਂਦੀ", "or": "ଘନ ଝିପିଝିପି ବର୍ଷା", "kok": "chodd paavs"
    },
    "slight rain": {
        "hi": "हल्की बारिश", "mr": "हलका पाऊस", "gu": "હળવો વરસાદ", "bn": "হালকা বৃষ্টি",
        "ta": "லேசான மழை", "te": "తేలికపాటి వర్షం", "kn": "ಹಗುರವಾದ ಮಳೆ", "ml": "നേരിയ മഴ",
        "pa": "ਹਲਕੀ ਬਾਰਿਸ਼", "or": "ହାଲୁକା ବର୍ଷା", "kok": "thoddo paavs"
    },
    "light rain": {
        "hi": "हल्की बारिश", "mr": "हलका पाऊस", "gu": "હળવો વરસાદ", "bn": "হালকা বৃষ্টি",
        "ta": "லேசான மழை", "te": "తేలికపాటి వర్షం", "kn": "ಹಗುರವಾದ ಮಳೆ", "ml": "നേരിയ മഴ",
        "pa": "ਹਲਕੀ ਬਾਰਿਸ਼", "or": "ହାଲୁକା ବର୍ଷା", "kok": "thoddo paavs"
    },
    "moderate rain": {
        "hi": "मध्यम बारिश", "mr": "मध्यम पाऊस", "gu": "મધ્યમ વરસાદ", "bn": "মাঝারি বৃষ্টি",
        "ta": "மிதமான மழை", "te": "మధ్యస్థ వర్షం", "kn": "ಮಧ್ಯಮ ಪ್ರಮಾಣದ ಮಳೆ", "ml": "മിതമായ മഴ",
        "pa": "ਦਰਮਿਆਨੀ ਬਾਰਿਸ਼", "or": "ମଧ୍ୟମ ଧରଣର ବର୍ଷା", "kok": "modhyom paavs"
    },
    "heavy rain": {
        "hi": "तेज बारिश", "mr": "मुसळधार पाऊस", "gu": "ભારે વરસાદ", "bn": "ভারী বৃষ্টিপাত",
        "ta": "கனமழை", "te": "భారీ వర్షం", "kn": "ಭಾರಿ ಮಳೆ", "ml": "കനത്ത മഴ",
        "pa": "ਭਾਰੀ ਬਾਰਿਸ਼", "or": "ପ୍ରବଳ ବର୍ଷା", "kok": "vhodd paavs"
    },
    "rain showers": {
        "hi": "रुक-रुक कर बारिश", "mr": "पावसाच्या सरी", "gu": "વરસાદી ઝાપટાં", "bn": "বৃষ্টির দমকা",
        "ta": "மழைச்சாரல்", "te": "వర్షపు జల్లులు", "kn": "ಮಳೆಯ ತುಂತುರು", "ml": "മഴത്തുള്ളികൾ",
        "pa": "ਮੀਂਹ ਦੇ ਛਿੱਟੇ", "or": "ବର୍ଷା ଝଲକ", "kok": "paavsacheo sori"
    },
    "thunderstorm": {
        "hi": "गरज के साथ बारिश", "mr": "वादळी पाऊस / मेघगर्जना", "gu": "ગાજવીજ સાથે વરસાદ", "bn": "বজ্রবিদ্যুৎ সহ ঝড়-বৃষ্টি",
        "ta": "இடியுடன் கூடிய மழை", "te": "ఉరుములతో కూడిన వర్షం", "kn": "ಗುಡುಗು ಸಹಿತ ಮಳೆ", "ml": "ഇടിമിന്നലോടു കൂടിയ മഴ",
        "pa": "ਗਰਜ ਨਾਲ ਮੀਂਹ", "or": "ଘଡ଼ଘଡ଼ି ସହ ବର୍ଷା", "kok": "gaddgadd ani paavs"
    },
    "moderate thunderstorm": {
        "hi": "गरज-चमक के साथ बारिश", "mr": "विजांच्या कडकडाटासह पाऊस", "gu": "ગાજવીજ સાથે મધ્યમ વરસાદ", "bn": "মাঝারি বজ্রঝড়",
        "ta": "மிதமான இடியுடன் கூடிய மழை", "te": "ఉరుములు, మెరుపులతో వర్షం", "kn": "ಗುಡುಗು ಸಿಡಿಲು ಸಹಿತ ಮಳೆ", "ml": "മിതമായ ഇടിമിന്നൽ മഴ",
        "pa": "ਗਰਜ-ਚਮਕ ਨਾਲ ਮੀਂਹ", "or": "ବିଜୁଳି ଘଡ଼ଘଡ଼ି ସହ ବର୍ଷା", "kok": "gaddgadd ani paavs"
    },
    "thunderstorm with hail": {
        "hi": "ओलावृष्टि और तेज आंधी", "mr": "गारांचा पाऊस आणि वादळ", "gu": "કરા સાથે ભારે તોફાન", "bn": "শিলাবৃষ্টি সহ মারাত্মক ঝড়",
        "ta": "ஆலங்கட்டி மழை மற்றும் இடி", "te": "వడగండ్ల వాన మరియు తుఫాను", "kn": "ಆಲಿಕಲ್ಲು ಸಹಿತ ಭಾರಿ ಗುಡುಗು ಮಳೆ", "ml": "ആലിപ്പഴത്തോട് കൂടിയ ഇടിമിന്നൽ",
        "pa": "ਗੜਿਆਂ ਵਾਲਾ ਤੂਫ਼ਾਨ", "or": "କୁଆପଥର ସହ ପ୍ରବଳ ଝଡ଼ବର୍ଷା", "kok": "gareamcho paavs ani toofan"
    },
}

# Facility and Landmark Mappings
LOCATION_FACILITY_MAP = {
    "primary health centre": {"hi": "प्राथमिक स्वास्थ्य केंद्र", "mr": "प्राथमिक आरोग्य केंद्र", "gu": "પ્રાથમિક આરોગ્ય કેન્દ્ર", "bn": "প্রাথমিক স্বাস্থ্য কেন্দ্র"},
    "primary health center": {"hi": "प्राथमिक स्वास्थ्य केंद्र", "mr": "प्राथमिक आरोग्य केंद्र", "gu": "પ્રાથમિક આરોગ્ય કેન્દ્ર", "bn": "প্রাথমিক স্বাস্থ্য কেন্দ্র"},
    "community health centre": {"hi": "सामुदायिक स्वास्थ्य केंद्र", "mr": "सामुदायिक आरोग्य केंद्र", "gu": "સામુદાયિક આરોગ્ય કેન્દ્ર"},
    "community health center": {"hi": "सामुदायिक स्वास्थ्य केंद्र", "mr": "सामुदायिक आरोग्य केंद्र", "gu": "સામુદાયિક આરોગ્ય કેન્દ્ર"},
    "subdistrict hospital": {"hi": "उप-ज़िला अस्पताल", "mr": "उपजिल्हा रुग्णालय", "gu": "પેટા જિલ્લા હોસ્પિટલ"},
    "sub-district hospital": {"hi": "उप-ज़िला अस्पताल", "mr": "उपजिल्हा रुग्णालय", "gu": "પેટા જિલ્લા હોસ્પિટલ"},
    "district hospital": {"hi": "ज़िला अस्पताल", "mr": "जिल्हा रुग्णालय", "gu": "જિલ્લા હોસ્પિટલ"},
    "general hospital": {"hi": "सामान्य अस्पताल", "mr": "सामान्य रुग्णालय"},
    "civil hospital": {"hi": "सिविल अस्पताल", "mr": "सिव्हिल हॉस्पिटल"},
    "government high school": {"hi": "सरकारी हाई स्कूल", "mr": "शासकीय हायस्कूल"},
    "government school": {"hi": "सरकारी स्कूल", "mr": "शासकीय शाळा"},
    "railway station": {"hi": "रेलवे स्टेशन", "mr": "रेल्वे स्टेशन", "gu": "રેલ્વે સ્ટેશન", "bn": "রেলওয়ে স্টেশন"},
    "bus stand": {"hi": "बस स्टैंड", "mr": "बस स्थानक", "gu": "બસ સ્ટેન્ડ"},
    "bus station": {"hi": "बस स्टेशन", "mr": "बस स्थानक", "gu": "બસ સ્ટેશન"},
    "bus stop": {"hi": "बस स्टॉप", "mr": "बस स्टॉप"},
    "post office": {"hi": "डाकघर", "mr": "टपाल कार्यालय", "gu": "પોસ્ટ ઓફિસ"},
    "police station": {"hi": "थाना / पुलिस स्टेशन", "mr": "पोलीस ठाणे", "gu": "પોલીસ સ્ટેશન"},
    "gram panchayat": {"hi": "ग्राम पंचायत", "mr": "ग्रामपंचायत", "gu": "ગ્રામ પંચાયત"},
    "international airport": {"hi": "अंतर्राष्ट्रीय हवाई अड्डा", "mr": "आंतरराष्ट्रीय विमानतळ", "gu": "આંતરરાષ્ટ્રીય એરપોર્ટ"},
    "airport": {"hi": "हवाई अड्डा", "mr": "विमानतळ", "gu": "એરપોર્ટ"},
    "market": {"hi": "बाज़ार", "mr": "बाजार", "gu": "બજાર"},
}

# Administrative Divisions & Regions
LOCATION_ADMIN_MAP = {
    "subdistrict": {"hi": "तहसील", "mr": "तालुका", "gu": "તાલુકો"},
    "sub-district": {"hi": "तहसील", "mr": "तालुका", "gu": "તાલુકો"},
    "tehsil": {"hi": "तहसील", "mr": "तहसील", "gu": "તાલુકો"},
    "taluka": {"hi": "तालुका", "mr": "तालुका", "gu": "તાલુકો"},
    "taluk": {"hi": "तालुका", "mr": "तालुका", "gu": "તાલુકો"},
    "district": {"hi": "ज़िला", "mr": "जिल्हा", "gu": "જિલ્લો", "bn": "জেলা"},
    "state": {"hi": "राज्य", "mr": "राज्य", "gu": "રાજ્ય", "bn": "রাজ্য"},
    "village": {"hi": "गाँव", "mr": "गाव", "gu": "ગામ", "bn": "গ্রাম"},
    "town": {"hi": "कस्बा", "mr": "शहर", "gu": "નગર"},
    "city": {"hi": "शहर", "mr": "शहर", "gu": "શહેર", "bn": "শহর"},
    "north": {"hi": "उत्तर", "mr": "उत्तर", "gu": "ઉત્તર", "bn": "উত্তর"},
    "south": {"hi": "दक्षिण", "mr": "दक्षिण", "gu": "દક્ષિણ", "bn": "দক্ষিণ"},
    "east": {"hi": "पूर्व", "mr": "पूर्व", "gu": "પૂર્વ", "bn": "পূর্ব"},
    "west": {"hi": "पश्चिम", "mr": "पश्चिम", "gu": "પશ્ચિમ", "bn": "পশ্চিম"},
    "central": {"hi": "मध्य", "mr": "मध्य", "gu": "મધ્ય"},
    "india": {"hi": "भारत", "mr": "भारत", "gu": "ભારત", "bn": "ভারত", "ta": "இந்தியா", "te": "భారతదేశం", "kn": "ಭಾರತ", "ml": "ഇന്ത്യ", "pa": "ਭਾਰਤ", "or": "ଭାରତ"},
}

# Indian States, Districts, Talukas & Major Places
LOCATION_PLACES_MAP = {
    # States & Union Territories
    "goa": {"hi": "गोवा", "mr": "गोवा", "gu": "ગોવા", "kok": "Goa"},
    "north goa": {"hi": "उत्तर गोवा", "mr": "उत्तर गोवा", "gu": "ઉત્તર ગોવા"},
    "south goa": {"hi": "दक्षिण गोवा", "mr": "दक्षिण गोवा", "gu": "દક્ષિણ ગોવા"},
    "maharashtra": {"hi": "महाराष्ट्र", "mr": "महाराष्ट्र", "gu": "મહારાષ્ટ્ર"},
    "delhi": {"hi": "दिल्ली", "mr": "दिल्ली", "gu": "દિલ્હી"},
    "new delhi": {"hi": "नई दिल्ली", "mr": "नवी दिल्ली", "gu": "નવી દિલ્હી"},
    "karnataka": {"hi": "कर्नाटक", "mr": "कर्नाटक", "kn": "ಕರ್ನಾಟಕ"},
    "gujarat": {"hi": "गुजरात", "mr": "गुजरात", "gu": "ગુજરાત"},
    "rajasthan": {"hi": "राजस्थान", "mr": "राजस्थान", "gu": "રાજસ્થાન"},
    "punjab": {"hi": "पंजाब", "mr": "पंजाब", "pa": "ਪੰਜਾਬ"},
    "haryana": {"hi": "हरियाणा", "mr": "हरियाणा"},
    "uttar pradesh": {"hi": "उत्तर प्रदेश", "mr": "उत्तर प्रदेश"},
    "madhya pradesh": {"hi": "मध्य प्रदेश", "mr": "मध्य प्रदेश"},
    "bihar": {"hi": "बिहार", "mr": "बिहार"},
    "west bengal": {"hi": "पश्चिम बंगाल", "mr": "पश्चिम बंगाल", "bn": "পশ্চিমবঙ্গ"},
    "tamil nadu": {"hi": "तमिलनाडु", "mr": "तमिळनाडू", "ta": "தமிழ்நாடு"},
    "kerala": {"hi": "केरल", "mr": "केरळ", "ml": "കേരളം"},
    "andhra pradesh": {"hi": "आंध्र प्रदेश", "mr": "आंध्र प्रदेश", "te": "ఆంధ్రప్రదేశ్"},
    "telangana": {"hi": "तेलंगाना", "mr": "तेलंगणा", "te": "తెలంగాణ"},
    "odisha": {"hi": "ओडिशा", "mr": "ओडिशा", "or": "ଓଡ଼ିଶା"},
    "assam": {"hi": "असम", "mr": "आसाम", "bn": "আসাম"},
    "himachal pradesh": {"hi": "हिमाचल प्रदेश", "mr": "हिमाचल प्रदेश"},
    "uttarakhand": {"hi": "उत्तराखंड", "mr": "उत्तराखंड"},
    "jharkhand": {"hi": "झारखंड", "mr": "झारखंड"},
    "chhattisgarh": {"hi": "छत्तीसगढ़", "mr": "छत्तीसगढ"},
    "jammu and kashmir": {"hi": "जम्मू और कश्मीर", "mr": "जम्मू आणि काश्मीर"},
    "ladakh": {"hi": "लद्दाख", "mr": "लडाख"},
    "chandigarh": {"hi": "चंडीगढ़", "mr": "चंदिगढ", "pa": "ਚੰਡੀਗੜ੍ਹ"},

    # Goa Talukas & Places
    "shiroda": {"hi": "शिरोडा", "mr": "शिरोडा", "kok": "Shiroda"},
    "ponda": {"hi": "पोंडा", "mr": "पोंडा", "kok": "Ponda"},
    "panaji": {"hi": "पणजी", "mr": "पणजी", "kok": "Panaji"},
    "panjim": {"hi": "पणजी", "mr": "पणजी", "kok": "Panaji"},
    "margao": {"hi": "मडगांव", "mr": "मडगाव", "kok": "Madgaon"},
    "madgaon": {"hi": "मडगांव", "mr": "मडगाव", "kok": "Madgaon"},
    "vasco da gama": {"hi": "वास्को दा गामा", "mr": "वास्को दा गामा"},
    "vasco": {"hi": "वास्को", "mr": "वास्को"},
    "mapusa": {"hi": "म्हापसा", "mr": "म्हापसा", "kok": "Mapusa"},
    "mapsa": {"hi": "म्हापसा", "mr": "म्हापसा", "kok": "Mapusa"},
    "bardez": {"hi": "बारदेज़", "mr": "बारदेश"},
    "salcete": {"hi": "सालसेट", "mr": "साष्टी"},
    "tiswadi": {"hi": "तिसवाड़ी", "mr": "तिसवाडी"},
    "mormugao": {"hi": "मुरगांव", "mr": "मुरगाव"},
    "bicholim": {"hi": "डिचोली", "mr": "डिचोली"},
    "sanquelim": {"hi": "सांखळी", "mr": "सांखळी"},
    "valpoi": {"hi": "वाळपोई", "mr": "वाळपोई"},
    "sattari": {"hi": "सत्तारी", "mr": "सत्तरी"},
    "pernem": {"hi": "पेडणे", "mr": "पेडणे"},
    "quepem": {"hi": "केपे", "mr": "केपे"},
    "sanguem": {"hi": "सांगे", "mr": "सांगे"},
    "canacona": {"hi": "काणकोण", "mr": "काणकोण"},
    "dharbandora": {"hi": "धारबांदोड़ा", "mr": "धारबांदोडा"},
    "curtorim": {"hi": "कुडतरी", "mr": "कुडतरी"},
    "navelim": {"hi": "नावेली", "mr": "नावेली"},
    "cortalim": {"hi": "कुठ्ठाळी", "mr": "कुठ्ठाळी"},

    # Major Indian Cities & Districts
    "pune": {"hi": "पुणे", "mr": "पुणे", "gu": "પુણે"},
    "mumbai": {"hi": "मुंबई", "mr": "मुंबई", "gu": "મુંબઈ"},
    "nagpur": {"hi": "नागपुर", "mr": "नागपूर"},
    "nashik": {"hi": "नाशिक", "mr": "नाशिक"},
    "thane": {"hi": "ठाणे", "mr": "ठाणे"},
    "solapur": {"hi": "सोलापुर", "mr": "सोलापूर"},
    "aurangabad": {"hi": "औरंगाबाद", "mr": "औरंगाबाद"},
    "chhatrapati sambhajinagar": {"hi": "छत्रपति संभाजीनगर", "mr": "छत्रपती संभाजीनगर"},
    "kolhapur": {"hi": "कोल्हापुर", "mr": "कोल्हापूर"},
    "amravati": {"hi": "अमरावती", "mr": "अमरावती"},
    "nanded": {"hi": "नांदेड़", "mr": "नांदेड"},
    "jalgaon": {"hi": "जलगांव", "mr": "जळगाव"},
    "bengaluru": {"hi": "बेंगलुरु", "mr": "बंगळुरू", "kn": "ಬೆಂಗಳೂರು"},
    "bangalore": {"hi": "बेंगलुरु", "mr": "बंगळुरू", "kn": "ಬೆಂಗಳೂರು"},
    "mysuru": {"hi": "मैसूर", "mr": "म्हैसूर", "kn": "ಮೈಸೂರು"},
    "mysore": {"hi": "मैसूर", "mr": "म्हैसूर", "kn": "ಮೈಸೂರು"},
    "hubballi": {"hi": "हुबली", "kn": "ಹುಬ್ಬಳ್ಳಿ"},
    "dharwad": {"hi": "धारवाड़", "kn": "ಧಾರವಾಡ"},
    "mangaluru": {"hi": "मंगलुरु", "kn": "ಮಂಗಳೂರು"},
    "mangalore": {"hi": "मंगलुरु", "kn": "ಮಂಗಳೂರು"},
    "belagavi": {"hi": "बेलगावी", "kn": "ಬೆಳಗಾವಿ"},
    "belgaum": {"hi": "बेलगाम", "kn": "ಬೆಳಗಾವಿ"},
    "chennai": {"hi": "चेन्नई", "mr": "चेन्नई", "ta": "சென்னை"},
    "madras": {"hi": "चेन्नई", "ta": "சென்னை"},
    "coimbatore": {"hi": "कोयंबटूर", "ta": "கோயம்புத்தூர்"},
    "madurai": {"hi": "मदुरै", "ta": "மதுரை"},
    "hyderabad": {"hi": "हैदराबाद", "mr": "हैदराबाद", "te": "హైదరాబాద్"},
    "secunderabad": {"hi": "सिकंदराबाद", "te": "సికింద్రాబాద్"},
    "warangal": {"hi": "वारंगल", "te": "వరంగల్"},
    "visakhapatnam": {"hi": "विशाखापट्टनम", "te": "విశాఖపట్నం"},
    "vizag": {"hi": "विशाखापट्टनम", "te": "విశాఖపట్నం"},
    "vijayawada": {"hi": "विजयवाड़ा", "te": "విజయవాడ"},
    "guntur": {"hi": "गुंटूर", "te": "గుంటూరు"},
    "tirupati": {"hi": "तिरुपति", "te": "తిరుపతి"},
    "kolkata": {"hi": "कोलकाता", "mr": "कोलकाता", "bn": "কলকাতা"},
    "calcutta": {"hi": "कोलकाता", "bn": "কলকাতা"},
    "howrah": {"hi": "हावड़ा", "bn": "হাওড়া"},
    "asansol": {"hi": "आसनसोल", "bn": "আসানসোল"},
    "siliguri": {"hi": "सिलीगुड़ी", "bn": "শিলিগুড়ি"},
    "ahmedabad": {"hi": "अहमदाबाद", "mr": "अहमदाबाद", "gu": "અમદાવાદ"},
    "surat": {"hi": "सूरत", "gu": "સુરત"},
    "vadodara": {"hi": "वडोदरा", "gu": "વડોદરા"},
    "baroda": {"hi": "वडोदरा", "gu": "વડોદરા"},
    "rajkot": {"hi": "राजकोट", "gu": "રાજકોટ"},
    "jaipur": {"hi": "जयपुर"},
    "jodhpur": {"hi": "जोधपुर"},
    "udaipur": {"hi": "उदयपुर"},
    "kota": {"hi": "कोटा"},
    "lucknow": {"hi": "लखनऊ"},
    "kanpur": {"hi": "कानपुर"},
    "varanasi": {"hi": "वाराणसी"},
    "banaras": {"hi": "बनारस"},
    "prayagraj": {"hi": "प्रयागराज"},
    "allahabad": {"hi": "प्रयागराज"},
    "agra": {"hi": "आगरा"},
    "meerut": {"hi": "मेरठ"},
    "noida": {"hi": "नोएडा"},
    "ghaziabad": {"hi": "गाज़ियाबाद"},
    "patna": {"hi": "पटना"},
    "gaya": {"hi": "गया"},
    "bhopal": {"hi": "भोपाल"},
    "indore": {"hi": "इंदौर"},
    "gwalior": {"hi": "ग्वालियर"},
    "jabalpur": {"hi": "जबलपुर"},
    "ranchi": {"hi": "राँची"},
    "jamshedpur": {"hi": "जमशेदपुर"},
    "raipur": {"hi": "रायपुर"},
    "bhubaneswar": {"hi": "भुवनेश्वर", "or": "ଭୁବନେଶ୍ୱର"},
    "cuttack": {"hi": "कटक", "or": "କଟକ"},
    "ludhiana": {"hi": "लुधियाना", "pa": "ਲੁਧਿਆਣਾ"},
    "amritsar": {"hi": "अमृतसर", "pa": "ਅੰਮ੍ਰਿਤਸਰ"},
    "shimla": {"hi": "शिमला"},
    "dehradun": {"hi": "देहरादून"},
    "srinagar": {"hi": "श्रीनगर"},
    "jammu": {"hi": "जम्मू"},
    "guwahati": {"hi": "गुवाहाटी", "bn": "গুয়াহাটি"},
    "thiruvananthapuram": {"hi": "तिरुवनंतपुरम", "ml": "തിരുവനന്തപുരം"},
    "kochi": {"hi": "कोच्चि", "ml": "കൊച്ചി"},
}

# Precompile a sorted list of terms for multi-word substitution
ALL_SORTED_TERMS = sorted(
    [
        (k, v) for d in [LOCATION_FACILITY_MAP, LOCATION_ADMIN_MAP, LOCATION_PLACES_MAP]
        for k, v in d.items()
    ],
    key=lambda item: len(item[0]),
    reverse=True
)


def localize_condition(condition: str, language: str = "en") -> str:
    """
    Localizes meteorological condition names into Indian languages.
    Example: 'Moderate drizzle' in 'hi' -> 'मध्यम बूंदाबांदी'
    """
    if not condition or not str(condition).strip():
        return str(condition or "")

    if (language or "").lower() in ["hi-latn", "hinglish"]:
        c_clean = str(condition).strip().lower()
        hinglish_map = {
            "clear sky": "saaf aasmaan",
            "sunny": "dhoop",
            "mainly clear": "saaf aasmaan",
            "partly cloudy": "halke badal",
            "cloudy": "badal",
            "overcast": "ghane badal",
            "fog": "kohra",
            "mist": "halka kohra",
            "light drizzle": "halki bundabandi",
            "moderate drizzle": "madhyam bundabandi",
            "dense drizzle": "tez bundabandi",
            "slight rain": "halki baarish",
            "light rain": "halki baarish",
            "moderate rain": "madhyam baarish",
            "heavy rain": "bhaari baarish",
            "rain showers": "baarish ki phuhaar",
            "thunderstorm": "aandhi-toofan",
            "thunderstorm with hail": "ola aur aandhi-toofan",
        }
        for k, v in hinglish_map.items():
            if k in c_clean or c_clean in k:
                return v
        return c_clean

    lang_key = (language or "en").split("-")[0].lower()
    if lang_key == "en":
        return str(condition)

    c_clean = str(condition).strip().lower()

    # Exact match
    if c_clean in WEATHER_CONDITIONS_I18N and lang_key in WEATHER_CONDITIONS_I18N[c_clean]:
        return WEATHER_CONDITIONS_I18N[c_clean][lang_key]

    # Keyword / substring fallback
    if "thunder" in c_clean or "storm" in c_clean:
        return WEATHER_CONDITIONS_I18N["thunderstorm"].get(lang_key, condition)
    if "heavy rain" in c_clean or "violent" in c_clean:
        return WEATHER_CONDITIONS_I18N["heavy rain"].get(lang_key, condition)
    if "shower" in c_clean or "slight rain" in c_clean:
        return WEATHER_CONDITIONS_I18N["rain showers"].get(lang_key, condition)
    if "drizzle" in c_clean:
        return WEATHER_CONDITIONS_I18N["light drizzle"].get(lang_key, condition)
    if "rain" in c_clean:
        return WEATHER_CONDITIONS_I18N["moderate rain"].get(lang_key, condition)
    if "overcast" in c_clean:
        return WEATHER_CONDITIONS_I18N["overcast"].get(lang_key, condition)
    if "cloud" in c_clean:
        return WEATHER_CONDITIONS_I18N["partly cloudy"].get(lang_key, condition)
    if "fog" in c_clean or "mist" in c_clean or "haze" in c_clean:
        return WEATHER_CONDITIONS_I18N["fog"].get(lang_key, condition)
    if "clear" in c_clean or "sun" in c_clean:
        return WEATHER_CONDITIONS_I18N["clear sky"].get(lang_key, condition)

    return str(condition)


def localize_location(name: str, language: str = "en") -> str:
    """
    Localizes raw reverse-geocoded or searched location names into regional scripts.
    Example:
    'Primary Health Centre, Shiroda, Ponda, Goa, India' in 'hi' ->
    'प्राथमिक स्वास्थ्य केंद्र, शिरोडा, पोंडा, गोवा, भारत'
    """
    if not name or not str(name).strip():
        return str(name or "")

    if (language or "").lower() in ["hi-latn", "hinglish", "en"]:
        return str(name)

    lang_key = (language or "en").split("-")[0].lower()
    if lang_key not in ["hi", "mr", "gu", "bn", "ta", "te", "kn", "ml", "pa", "or"]:
        return str(name)

    parts = [p.strip() for p in str(name).split(",") if p.strip()]
    localized_parts = []

    for part in parts:
        part_clean = part.strip()
        part_lower = part_clean.lower()

        # 1. Exact match in places map
        if part_lower in LOCATION_PLACES_MAP and lang_key in LOCATION_PLACES_MAP[part_lower]:
            localized_parts.append(LOCATION_PLACES_MAP[part_lower][lang_key])
            continue

        # 2. Exact match in facility map
        if part_lower in LOCATION_FACILITY_MAP and lang_key in LOCATION_FACILITY_MAP[part_lower]:
            localized_parts.append(LOCATION_FACILITY_MAP[part_lower][lang_key])
            continue

        # 3. Exact match in admin map
        if part_lower in LOCATION_ADMIN_MAP and lang_key in LOCATION_ADMIN_MAP[part_lower]:
            localized_parts.append(LOCATION_ADMIN_MAP[part_lower][lang_key])
            continue

        # 4. Multi-word phrase or compound replacement within the part
        subbed = part_clean
        for en_phrase, translations in ALL_SORTED_TERMS:
            if lang_key in translations:
                pattern = rf"\b{re.escape(en_phrase)}\b"
                subbed = re.sub(pattern, translations[lang_key], subbed, flags=re.IGNORECASE)

        localized_parts.append(subbed.strip())

    return ", ".join(localized_parts)


async def translate_with_bhashini(
    text: str, source_lang: str, target_lang: str = "en"
) -> str | None:
    """
    Translate text using Bhashini if configured, else returns None.
    """
    if bhashini.is_available():
        return await bhashini.translate_text(text, source_lang, target_lang)
    return None


def normalize_for_speech(text: str, language: str = "en") -> str:
    """
    Normalizes text for text-to-speech engines:
    - Expands symbols: °C -> डिग्री सेल्सियस, % -> प्रतिशत, km/h -> किलोमीटर प्रति घंटा
    - Strips markdown formatting, bullets, hashes, bold, italics, emojis
    """
    if not text:
        return ""

    cleaned = text
    # Strip markdown headers, lists, blockquotes, bold/italics
    cleaned = re.sub(r'#{1,6}\s+', ' ', cleaned)
    cleaned = re.sub(r'[*_~]{1,3}', ' ', cleaned)
    cleaned = re.sub(r'^\s*[-*•+]\s+', ' ', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'^\s*>\s+', ' ', cleaned, flags=re.MULTILINE)

    # Phonetic unit expansions
    lang = (language or "en").lower().split("-")[0]
    if lang == "hi":
        cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*°\s*C\b', r'\1 डिग्री सेल्सियस', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*°', r'\1 डिग्री', cleaned)
        cleaned = re.sub(r'°C\b', ' डिग्री सेल्सियस ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*%', r'\1 प्रतिशत', cleaned)
        cleaned = re.sub(r'%', ' प्रतिशत ', cleaned)
        cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*(?:km\/h|kmph|किमी\/घंटा)', r'\1 किलोमीटर प्रति घंटा', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*mm\b', r'\1 मिलीमीटर', cleaned, flags=re.IGNORECASE)
    elif lang == "mr":
        cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*°\s*C\b', r'\1 डिग्री सेल्सिअस', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*°', r'\1 डिग्री', cleaned)
        cleaned = re.sub(r'°C\b', ' डिग्री सेल्सिअस ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*%', r'\1 टक्के', cleaned)
        cleaned = re.sub(r'%', ' टक्के ', cleaned)
        cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*(?:km\/h|kmph|किमी\/तास)', r'\1 किलोमीटर प्रति तास', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*mm\b', r'\1 मिलीमीटर', cleaned, flags=re.IGNORECASE)
    else:  # Default English
        cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*°\s*C\b', r'\1 degrees Celsius', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*°', r'\1 degrees', cleaned)
        cleaned = re.sub(r'°C\b', ' degrees Celsius ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*%', r'\1 percent', cleaned)
        cleaned = re.sub(r'%', ' percent ', cleaned)
        cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*(?:km\/h|kmph)', r'\1 kilometers per hour', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'(\d+(?:\.\d+)?)\s*mm\b', r'\1 millimeters', cleaned, flags=re.IGNORECASE)

    # Collapse whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


prepareTTS = normalize_for_speech



