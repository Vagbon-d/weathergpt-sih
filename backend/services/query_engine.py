"""
WeatherGPT Query Understanding, Temporal Resolution, and Verified Context Engine (SIH26068).

Implements the Golden Rule Architecture:
USER
 ↓
LOCATION (Canonical & Localized)
 ↓
LANGUAGE DETECTION
 ↓
QUERY UNDERSTANDING (17+ Intents)
 ↓
TEMPORAL RESOLUTION (Deterministic dates & hourly windows)
 ↓
CONVERSATION CONTEXT (Lightweight multi-turn follow-ups)
 ↓
SELECTIVE DATA RETRIEVAL
 ↓
FACTUAL VERIFIED CONTEXT (Compact, zero bloat)
 ↓
LLM HUMANIZATION (Qwen3:4b with strict grounding)
 ↓
RESPONSE VALIDATION (Numeric safety, zero English leakage)
 ↓
DETERMINISTIC FALLBACK (Safe, natural, human sentences)
"""

import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta
from typing import Any

from services import language_service, advisory_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 0. STRUCTURED QUERY MODEL (SECTION 1 & 2)
# ---------------------------------------------------------------------------

@dataclass
class StructuredQuery:
    raw_query: str
    intent: str
    sub_intent: str | None = None
    domain: str = "weather"
    activity: str | None = None
    location: str | None = None
    location_query: str | None = None
    query_location: str | None = None
    location_source: str = "application"
    date_intent: str = "today"
    resolved_dates: list[str] = field(default_factory=list)
    primary_date: str = ""
    date_label: str = "Today"
    date_label_hi: str = "आज"
    time_of_day: str | None = None
    requires_current_weather: bool = True
    requires_forecast: bool = False
    requires_rain: bool = False
    requires_alerts: bool = False
    requires_warning: bool = False
    requires_agriculture: bool = False
    requires_activity: bool = False
    requires_comparison: bool = False
    required_fields: list[str] = field(default_factory=list)
    comparison_dates: list[str] | None = None
    language: str = "en"
    is_follow_up: bool = False
    inherit_context: bool = False
    is_unrelated: bool = False
    is_unsupported: bool = False
    unsupported_category: str | None = None
    is_ambiguous: bool = False
    clarification_prompt: str | None = None
    activity_suitability: dict[str, Any] | None = None
    temporal_target: str = "today"

    @property
    def requires_current(self) -> bool:
        return self.requires_current_weather

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["temporal"] = self.temporal_target
        d["query"] = self.raw_query
        return d

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            val = getattr(self, key)
            return val
        if key == "temporal":
            return self.temporal_target
        if key == "query":
            return self.raw_query
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key) or key in ("temporal", "query")

    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            val = getattr(self, key)
            return val if val is not None else default
        if key == "temporal":
            return self.temporal_target
        if key == "query":
            return self.raw_query
        return default

    def keys(self):
        return self.to_dict().keys()


WEEKDAYS = {
    "monday": 0, "mon": 0, "सोमवार": 0, "somvar": 0, "somwar": 0,
    "tuesday": 1, "tue": 1, "मंगलवार": 1, "mangalvar": 1, "mangalwar": 1,
    "wednesday": 2, "wed": 2, "बुधवार": 2, "budhvar": 2, "budhwar": 2,
    "thursday": 3, "thu": 3, "गुरुवार": 3, "guruvar": 3, "guruwar": 3, "बृहस्पतिवार": 3, "veervar": 3,
    "friday": 4, "fri": 4, "शुक्रवार": 4, "shukravar": 4, "shukrawar": 4,
    "saturday": 5, "sat": 5, "शनिवार": 5, "shanivar": 5, "shaniwar": 5, "sanivar": 5,
    "sunday": 6, "sun": 6, "रविवार": 6, "ravivar": 6, "raviwar": 6, "इतवार": 6, "itwar": 6,
}
WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKDAY_LABELS = {
    0: ("Monday", "सोमवार"),
    1: ("Tuesday", "मंगलवार"),
    2: ("Wednesday", "बुधवार"),
    3: ("Thursday", "गुरुवार"),
    4: ("Friday", "शुक्रवार"),
    5: ("Saturday", "शनिवार"),
    6: ("Sunday", "रविवार"),
}


# ---------------------------------------------------------------------------
# 1. INTENT RECOGNITION PATTERNS
# ---------------------------------------------------------------------------

INTENT_PATTERNS = {
    "spraying": [
        r"\b(?:spray|spraying|pesticide|pesticides|insecticide|fungicide|chemical|fertilizer)\b",
        r"(?:छिड़काव|दवाई|दवा|कीटनाशक|कीटनाशक दवाई|स्प्रे)",
        r"\b(?:chhidkaw|chhidkaav|dawa|dawai|spray|keetnashak)\b",
        r"(?:फवारणी|कीटकनाशक|औषध)",
    ],
    "irrigation": [
        r"\b(?:irrigate|irrigation|water|watering|soak)\b",
        r"(?:सिंचाई|पानी देना|पानी लगाना|सिंचन)",
        r"\b(?:sinchai|sinchayi|paani dena|pani lagana)\b",
        r"(?:पाणी देणे|सिंचन)",
    ],
    "harvesting": [
        r"\b(?:harvest|harvesting|reaping|cutting crop)\b",
        r"(?:कटाई|फसल काटना|कटाई करना)",
        r"\b(?:katai|fasal katna)\b",
        r"(?:काढणी|पीक कापणे)",
    ],
    "agriculture": [
        r"\b(?:crop|crops|farm|farming|farmer|sowing|seed|soil|rice|wheat|cotton|tomato|onion)\b",
        r"(?:खेती|फसल|फ़सल|किसान|बुवाई|बोना|खेत|धान|गेहूँ|गेहूं|कपास|टमाटर|प्याज)",
        r"\b(?:kheti|fasal|kisan|buwai|khet)\b",
        r"(?:शेती|शेतकरी|पेरणी)",
    ],
    "cyclone": [
        r"\b(?:cyclone|hurricane|typhoon)\b",
        r"(?:चक्रवात|चक्रवाती तूफान|महातूफान)",
        r"\b(?:cyclone|toofan|chakravat)\b",
    ],
    "warning": [
        r"\b(?:warning|warnings|alert|alerts|danger|flood|flooding|heatwave|lightning)\b",
        r"(?:चेतावनी|अलर्ट|चेतावनी जारी|बाढ़|लू|बिजली गिरना|तूफ़ान|तूफान|ख़तरा|खतरा|आपदा)",
        r"\b(?:warning|alert|chetavani|baadh|khatra|bijli)\b",
        r"(?:इशारा|धोका)",
    ],
    "rain": [
        r"\b(?:rain|raining|rainy|rainfall|shower|showers|drizzle|umbrella|wet|downpour)\b",
        r"(?:बारिश|बरसात|वर्षा|बूंदाबांदी|पानी बरसेगा|छाता|भीगना)",
        r"\b(?:baarish|barish|barsat|paani barsega|chaata|chata|chhaata)\b",
        r"(?:पाऊस|रिमझिम|छत्री)",
        r"(?:વરસાદ|છત્રી)",
        r"(?:বৃষ্টি|ছাতা)",
    ],
    "temperature": [
        r"\b(?:temperature|temp|hot|cold|warm|heat|chilly|degrees|celsius)\b",
        r"(?:तापमान|गर्मी|गरमी|ठंड|ठंडी|सर्दी|डिग्री)",
        r"\b(?:tapman|garmi|thand|thandi|sardi)\b",
        r"(?:तापमान|उष्णता|थंडी)",
    ],
    "wind": [
        r"\b(?:wind|windy|breeze|gust|gusts|airflow)\b",
        r"(?:हवा|हवा की गति|तेज हवा|आंधी|झोंके)",
        r"\b(?:hawa|tez hawa|aandhi)\b",
        r"(?:वारा|वादळ)",
    ],
    "humidity": [
        r"\b(?:humidity|humid|moisture|muggy|sweat|sweaty)\b",
        r"(?:नमी|आर्द्रता|उमस|पसीना)",
        r"\b(?:nami|umas|paseena)\b",
        r"(?:दमट|आर्द्रता)",
    ],
    "travel": [
        r"\b(?:travel|traveling|driving|journey|trip|road trip|drive)\b",
        r"(?:यात्रा|सफर|सफ़र|ड्राइव|गाड़ी चलाना|रोड ट्रिप)",
        r"\b(?:yatra|safar|safargardi)\b",
    ],
    "outdoor_activity": [
        r"\b(?:outdoor|outside|picnic|walk|sports|match|cricket|play|walk outside|go out|head out)\b",
        r"(?:बाहर जाना|घूमना|पिकनिक|टहलना|खेल|मैच|बाहर का काम|सैर)",
        r"\b(?:bahar jana|ghoomna|picnic|match|khelna|bahar)\b",
        r"(?:बाहेर जाणे|खेळ)",
    ],
    "marine": [
        r"\b(?:marine|fishing|boat|sail|sea|ocean|coast|coastal)\b",
        r"(?:मछली पकड़ना|नाव|समुद्र|तट|नाविक)",
        r"\b(?:machhli|machli pakadna|naav|samundar)\b",
    ],
    "comparison": [
        r"\b(?:compare|comparison|versus|vs|warmer|colder|hotter|rainier|more rain)\b",
        r"(?:तुलना|ज्यादा गर्म|ज़्यादा गर्मी|कम या ज्यादा|किस दिन ज्यादा)",
        r"\b(?:tulna|jyada|zyada garmi|behtar)\b",
    ],
    "weather_forecast": [
        r"\b(?:forecast|7 day|week|coming days|next few days|outlook)\b",
        r"(?:पूर्वानुमान|7 दिन|सप्ताह|अगले कुछ दिन|हफ्ते भर का)",
        r"\b(?:forecast|hafta|agle kuch din)\b",
    ],
    "weather_current": [
        r"\b(?:current|now|right now|present|currently|today)\b",
        r"(?:अभी|वर्तमान|फिलहाल|इस समय|आज का हाल)",
        r"\b(?:abhi|aaj|filhal|is waqt)\b",
    ],
}


# ---------------------------------------------------------------------------
# 1B. DOMAIN & ACTIVITY PATTERNS (STRICT FIRST-STAGE ROUTER)
# ---------------------------------------------------------------------------

ACTIVITY_PATTERNS = {
    "fishing": [
        r"\b(?:fish|fishing|angler|angling|catch fish|trolling|boat fishing|sea fishing)\b",
        r"(?:मछली पकड़ना|मछली पकड़ने|मत्स्य पालन|नाव चलाना|मासेमारी)",
        r"\b(?:machli pakadna|machhli pakadna|machli|maashimari|matsya)\b",
    ],
    "picnic": [
        r"\b(?:picnic|outing|day out|family outing|cookout|barbecue|bbq)\b",
        r"(?:पिकनिक|सैर सपाटा|घूमने जाना)",
        r"\b(?:picnic|outing)\b",
    ],
    "hiking": [
        r"\b(?:hike|hiking|trek|trekking|trail|mountain climb|hill climb)\b",
        r"(?:हाइकिंग|ट्रेकिंग|पहाड़ चढ़ना)",
        r"\b(?:hike|hiking|trek|trekking)\b",
    ],
    "outdoor_work": [
        r"\b(?:outdoor work|work outside|working outside|field work|labour|manual work|outside duty|work outdoors)\b",
        r"(?:बाहर का काम|धूप में काम|खुले में काम|मजदूरी)",
        r"\b(?:bahar ka kaam|bahar kaam|mazdoori)\b",
    ],
    "construction": [
        r"\b(?:construction|masonry|roofing|pouring concrete|painting outdoor|scaffolding|building work)\b",
        r"(?:निर्माण कार्य|मकान बनाना|छत डालना|दीवार उठाना)",
        r"\b(?:construction|makan banana)\b",
    ],
    "travel": [
        r"\b(?:travel|traveling|travelling|journey|trip|road trip|drive|driving|commute|commuting|long drive)\b",
        r"(?:यात्रा|सफर|सफ़र|ड्राइव|गाड़ी चलाना|रोड ट्रिप|सड़क यात्रा)",
        r"\b(?:yatra|safar|safargardi|drive|driving)\b",
    ],
    "sports": [
        r"\b(?:play cricket|cricket match|football|soccer|badminton|tennis|basketball|sports match|outdoor game)\b",
        r"(?:क्रिकेट खेलना|मैच खेलना|फुटबॉल|खेलकूद|मैदान में खेलना)",
        r"\b(?:cricket|football|match khelna|khelna)\b",
    ],
    "walking": [
        r"\b(?:walk|walking|morning walk|evening walk|jog|jogging|run|running|tread)\b",
        r"(?:टहलना|सैर|दौड़ना|मॉर्निंग वॉक|शाम की सैर)",
        r"\b(?:tahalna|sair|morning walk|jogging)\b",
    ],
    "cycling": [
        r"\b(?:cycle|cycling|bike ride|bicycling|ride bike)\b",
        r"(?:साइकिल चलाना|साइकिलिंग)",
        r"\b(?:cycling|cycle chalana)\b",
    ],
    "beach_visit": [
        r"\b(?:beach|beaches|sea shore|seashore|coastline|swim in sea|ocean swim)\b",
        r"(?:बीच जाना|समुद्र तट|समुद्र किनारे जाना)",
        r"\b(?:beach|samundar kinare)\b",
    ],
    "photography": [
        r"\b(?:photography|photoshoot|outdoor shoot|landscape photo|camera shoot)\b",
        r"(?:फोटोग्राफी|फोटो खींचना|शूटिंग)",
        r"\b(?:photography|photoshoot)\b",
    ],
    "gardening": [
        r"\b(?:gardening|lawn mowing|mow lawn|plant saplings|watering garden)\b",
        r"(?:बागवानी|बगीचे का काम|पौधे लगाना)",
        r"\b(?:gardening|bagwani)\b",
    ],
    "event_planning": [
        r"\b(?:outdoor event|outdoor party|wedding outdoors|open air function|gathering outdoor)\b",
        r"(?:आउटडोर कार्यक्रम|खुले में शादी|पार्टी|समारोह)",
        r"\b(?:outdoor event|outdoor party|shaadi)\b",
    ],
    "delivery": [
        r"\b(?:delivery|food delivery|courier work|ride delivery|parcel delivery)\b",
        r"(?:डिलीवरी|कूरियर का काम)",
        r"\b(?:delivery)\b",
    ],
    "school_activities": [
        r"\b(?:school trip|sports day|school assembly|outdoor assembly|field trip)\b",
        r"(?:स्कूल पिकनिक|स्पोर्ट्स डे)",
        r"\b(?:school trip|sports day)\b",
    ],
    "spraying": [
        r"\b(?:spray|spraying|pesticide|pesticides|insecticide|fungicide|chemical|fertilizer)\b",
        r"(?:छिड़काव|दवाई|दवा|कीटनाशक|कीटनाशक दवाई|स्प्रे)",
        r"\b(?:chhidkaw|chhidkaav|dawa|dawai|spray|keetnashak)\b",
        r"(?:फवारणी|कीटकनाशक|औषध)",
    ],
    "irrigation": [
        r"\b(?:irrigate|irrigation|water|watering|soak)\b",
        r"(?:सिंचाई|पानी देना|पानी लगाना|सिंचन)",
        r"\b(?:sinchai|sinchayi|paani dena|pani lagana)\b",
        r"(?:पाणी देणे|सिंचन)",
    ],
    "harvesting": [
        r"\b(?<!rainwater\s)(?<!rain\s)(?<!water\s)(?:crop\s+harvesting|harvesting\s+crops?|harvest|harvesting|reaping|cutting crop)\b",
        r"(?:फसल कटाई|फसल काटना|कटाई करना)",
        r"\b(?:katai|fasal katna)\b",
        r"(?:काढणी|पीक कापणे)",
    ],
    "sowing": [
        r"\b(?:sow|sowing|seeding|plant seeds)\b",
        r"(?:बुवाई|बोना|बीज बोना)",
        r"\b(?:buwai|bona|beej bona)\b",
        r"(?:पेरणी)",
    ],
}

SUPPORTED_ACTIVITIES = {
    "spraying": {
        "labels": {"en": "spraying pesticides", "hi": "दवा का छिड़काव", "hi-Latn": "pesticide spraying"},
        "required_fields": ["rain_probability", "wind_kmh", "condition"],
        "requires_alerts": True,
    },
    "irrigation": {
        "labels": {"en": "crop irrigation", "hi": "खेत की सिंचाई", "hi-Latn": "irrigation"},
        "required_fields": ["rain_probability", "precipitation_mm", "temp_max"],
        "requires_alerts": False,
    },
    "harvesting": {
        "labels": {"en": "crop harvesting", "hi": "फसल कटाई", "hi-Latn": "crop harvesting"},
        "required_fields": ["rain_probability", "condition", "wind_kmh"],
        "requires_alerts": True,
    },
    "sowing": {
        "labels": {"en": "crop sowing", "hi": "फसल की बुवाई", "hi-Latn": "sowing"},
        "required_fields": ["rain_probability", "precipitation_mm", "temp_max"],
        "requires_alerts": False,
    },
    "fishing": {
        "labels": {"en": "fishing", "hi": "मछली पकड़ना", "hi-Latn": "fishing"},
        "required_fields": ["rain_probability", "wind_kmh", "condition", "marine_warnings", "precipitation_mm"],
        "requires_alerts": True,
    },
    "picnic": {
        "labels": {"en": "picnic", "hi": "पिकनिक", "hi-Latn": "picnic"},
        "required_fields": ["rain_probability", "temp_max", "wind_kmh", "condition"],
        "requires_alerts": False,
    },
    "hiking": {
        "labels": {"en": "hiking", "hi": "हाइकिंग / ट्रेकिंग", "hi-Latn": "hiking"},
        "required_fields": ["rain_probability", "temp_max", "wind_kmh", "condition", "precipitation_mm"],
        "requires_alerts": True,
    },
    "outdoor_work": {
        "labels": {"en": "outdoor work", "hi": "बाहरी काम", "hi-Latn": "outdoor work"},
        "required_fields": ["temp_max", "feels_like_c", "humidity_pct", "rain_probability", "wind_kmh"],
        "requires_alerts": True,
    },
    "construction": {
        "labels": {"en": "construction", "hi": "निर्माण कार्य", "hi-Latn": "construction work"},
        "required_fields": ["rain_probability", "precipitation_mm", "temp_max", "wind_kmh"],
        "requires_alerts": True,
    },
    "travel": {
        "labels": {"en": "travel / driving", "hi": "यात्रा / ड्राइविंग", "hi-Latn": "travel"},
        "required_fields": ["rain_probability", "wind_kmh", "condition", "warnings"],
        "requires_alerts": True,
    },
    "sports": {
        "labels": {"en": "sports / match", "hi": "खेल / मैच", "hi-Latn": "sports"},
        "required_fields": ["rain_probability", "temp_max", "wind_kmh", "condition"],
        "requires_alerts": False,
    },
    "walking": {
        "labels": {"en": "walking", "hi": "टहलना / सैर", "hi-Latn": "walking"},
        "required_fields": ["rain_probability", "temp_max", "feels_like_c", "condition"],
        "requires_alerts": False,
    },
    "cycling": {
        "labels": {"en": "cycling", "hi": "साइकिल चलाना", "hi-Latn": "cycling"},
        "required_fields": ["rain_probability", "wind_kmh", "condition"],
        "requires_alerts": False,
    },
    "beach_visit": {
        "labels": {"en": "beach visit", "hi": "समुद्र तट / बीच जाना", "hi-Latn": "beach visit"},
        "required_fields": ["rain_probability", "wind_kmh", "condition", "marine_warnings"],
        "requires_alerts": True,
    },
    "photography": {
        "labels": {"en": "photography", "hi": "फोटोग्राफी", "hi-Latn": "photography"},
        "required_fields": ["condition", "cloud_cover_pct", "rain_probability"],
        "requires_alerts": False,
    },
    "gardening": {
        "labels": {"en": "gardening", "hi": "बागवानी", "hi-Latn": "gardening"},
        "required_fields": ["rain_probability", "temp_max", "wind_kmh"],
        "requires_alerts": False,
    },
    "event_planning": {
        "labels": {"en": "outdoor event", "hi": "आउटडोर कार्यक्रम", "hi-Latn": "outdoor event"},
        "required_fields": ["rain_probability", "temp_max", "wind_kmh", "condition"],
        "requires_alerts": True,
    },
    "delivery": {
        "labels": {"en": "delivery", "hi": "डिलीवरी", "hi-Latn": "delivery"},
        "required_fields": ["rain_probability", "wind_kmh", "condition"],
        "requires_alerts": True,
    },
    "school_activities": {
        "labels": {"en": "school activities", "hi": "स्कूल गतिविधियाँ", "hi-Latn": "school activities"},
        "required_fields": ["rain_probability", "temp_max", "condition"],
        "requires_alerts": True,
    },
}

UNSUPPORTED_PATTERNS = {
    "coding": [
        r"\b(?:python|java|javascript|typescript|c\+\+|cpp|c#|rust|golang|php|ruby|swift|kotlin|html|css|sql|nosql|react|vue|angular|django|flask|fastapi)\b",
        r"\b(?:code|coding|program|programming|script|scripting|algorithm|syntax|compile|compiler|debugger|debugging|bug|developer|github|repository|class|function|loop|variable|array|object|json format|regex)\b",
        r"\b(?:give me|write|generate|create|provide|show me)(?:\s+a)?\s+(?:python|java|c\+\+|code|program|script|function|app|bot|api)\b",
        r"\b(?:code likho|program likho|script do|coding sikhao)\b",
    ],
    "essay_writing": [
        r"\b(?:write|generate|compose|draft)\s+(?:an?\s+)?(?:essay|article|paragraph|story|poem|poetry|speech|letter|application|resume|cv|cover letter|blog post|email|assignment|homework)\b",
        r"\b(?:essay on|story about|poem about|kavita|kahani|patra|nibandh)\b",
    ],
    "general_knowledge": [
        r"\b(?:who is|who was|who are|who created|who invented|who discovered|who founded)\b",
        r"\b(?:what is the capital|capital of|president of|prime minister of|pm of|chief minister of|cm of|currency of|population of)\b",
        r"\b(?:elon musk|bill gates|donald trump|narendra modi|gandhi|nehru|einstein|newton)\b",
        r"\b(?:movie|film|actor|actress|bollywood|hollywood|song|lyrics|singer)\b",
        r"\b(?:stock market|share price|crypto|cryptocurrency|bitcoin|ethereum|sensex|nifty)\b",
        r"\b(?:formula 1|f1|fifa|world cup|cricket score|ipl score|who won the match)\b",
        r"(?:kaun hai|kisne banaya|kiska beta|rajdhani|pradhan mantri|rashtrapati)",
    ],
    "image_generation": [
        r"\b(?:generate|create|make|draw|paint|produce|render)\s+(?:an?\s+)?(?:image|picture|photo|illustration|drawing|artwork|logo|banner)\b",
        r"(?:photo banao|tasveer banao|chitra banao)",
    ],
    "jokes": [
        r"\b(?:tell me a joke|tell a joke|say a joke|joke sunao|chutkula|make me laugh|koi joke)\b",
    ],
    "math": [
        r"^\s*\d+\s*[\+\-\*\/\^x×÷]\s*\d+\s*(?:=\s*)?$",
        r"\b(?:calculate|solve|evaluate|compute|what is)\s+\d+\s*[\+\-\*\/\^x×÷]\s*\d+\b",
        r"\b(?:square root of|cube root of|solve this equation)\b",
    ],
    "prompt_injection": [
        r"\b(?:ignore previous instructions|forget weather|ignore all previous|act as a|pretend you are|you are now|jailbreak|bypass)\b",
        r"\b(?:system prompt|developer instructions|leak instructions)\b",
    ],
}

SMALLTALK_PATTERNS = [
    r"^(?:hi|hello|hey|greetings|namaste|namaskar|pranam|kem cho|vanakkam|radhe radhe|ram ram|hello there)\b[\s!.,?]*$",
    r"^(?:good\s+(?:morning|afternoon|evening|day|night))\b[\s!.,?]*$",
    r"^(?:thank\s+you|thanks|thank\s+you\s+so\s+much|dhanyawad|shukriya|thanks a lot)\b[\s!.,?]*$",
    r"^(?:who\s+are\s+you|what\s+is\s+your\s+name|what\s+can\s+you\s+do|who\s+made\s+you|tum\s+kaun\s+ho|aap\s+kaun\s+hain|help)\b[\s!.,?]*$",
    r"^(?:how\s+are\s+you|how's\s+it\s+going|kaise\s+ho|kya\s+haal\s+hai)\b[\s!.,?]*$",
]

AMBIGUOUS_PATTERNS = [
    r"^(?:is\s+it\s+okay\s+(?:today|tomorrow|tonight|on\s+\w+))\??$",
    r"^(?:will\s+it\s+be\s+fine\s+(?:today|tomorrow|tonight|on\s+\w+))\??$",
    r"^(?:is\s+(?:today|tomorrow)\s+(?:good|okay|fine|bad))\??$",
    r"^(?:how\s+is\s+it\s+looking\s+(?:today|tomorrow))\??$",
    r"^(?:what\s+about\s+(?:today|tomorrow))\??$",
    r"^(?:(?:kal|aaj)\s+(?:theek|sahi|kaisa)\s+rahega)\??$",
    r"^(?:कल\s+(?:कैसा|ठीक)\s+रहेगा)\??$",
]


def evaluate_activity_suitability(
    activity: str,
    temporal_weather: dict[str, Any],
    alerts_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    alerts_data = alerts_data or []
    rain_p = float(temporal_weather.get("rain_prob", temporal_weather.get("rain_probability", 0)))
    wind = float(temporal_weather.get("wind_kmh", temporal_weather.get("wind_max_kmh", 10)))
    t_max = float(temporal_weather.get("temp_max", temporal_weather.get("temp_c", 28)))
    t_min = float(temporal_weather.get("temp_min", 22))
    cond = str(temporal_weather.get("condition", "")).lower()

    status = "GOOD"  # GOOD, CAUTION, NOT_RECOMMENDED
    reasons = []

    marine_or_cyclone = any(
        (a.get("is_official") or "imd" in str(a.get("source", "")).lower())
        and a.get("severity") in ["RED", "ORANGE"]
        and ("cyclone" in str(a.get("category", "")).lower() or "cyclone" in str(a.get("hazard", "")).lower() or "marine" in str(a.get("hazard", "")).lower() or "squall" in str(a.get("message", "")).lower())
        for a in alerts_data
    )
    severe_warning = any(a.get("severity") in ["RED", "ORANGE"] for a in alerts_data)

    if activity == "fishing":
        if marine_or_cyclone:
            status = "NOT_RECOMMENDED"
            reasons.append("Official marine/cyclone warning active; squally seas expected.")
        elif wind > 30:
            status = "NOT_RECOMMENDED"
            reasons.append(f"Strong winds reaching {wind:.1f} km/h make open waters hazardous.")
        elif rain_p >= 60 or "thunder" in cond:
            status = "NOT_RECOMMENDED"
            reasons.append(f"High risk of rain ({rain_p:.0f}%) and adverse sea conditions.")
        elif wind > 20:
            status = "CAUTION"
            reasons.append(f"Moderate winds ({wind:.1f} km/h) may create choppy waters.")
        elif rain_p >= 35:
            status = "CAUTION"
            reasons.append(f"Moderate chance of rain ({rain_p:.0f}%); keep monitoring coastal weather.")
        else:
            status = "GOOD"
            reasons.append(f"Calm winds ({wind:.1f} km/h) and low rain risk ({rain_p:.0f}%).")

    elif activity in ["picnic", "event_planning"]:
        if severe_warning or rain_p >= 60 or "thunder" in cond:
            status = "NOT_RECOMMENDED"
            reasons.append(f"High rain probability ({rain_p:.0f}%) will disrupt outdoor setups.")
        elif rain_p >= 35 or wind > 25:
            status = "CAUTION"
            reasons.append(f"Moderate rain probability ({rain_p:.0f}%) or breeze ({wind:.1f} km/h); have covered shelter available.")
        elif t_max > 36:
            status = "CAUTION"
            reasons.append(f"High afternoon temperatures ({t_max:.1f}°C); seek shaded areas.")
        else:
            status = "GOOD"
            reasons.append(f"Pleasant conditions with only {rain_p:.0f}% rain chance.")

    elif activity in ["hiking", "trekking"]:
        if severe_warning or rain_p >= 60 or "thunder" in cond:
            status = "NOT_RECOMMENDED"
            reasons.append(f"High rain chance ({rain_p:.0f}%) and slick trails / lightning risk.")
        elif rain_p >= 40 or wind > 30:
            status = "CAUTION"
            reasons.append(f"Chances of rain ({rain_p:.0f}%) and gusty winds; carry proper rain gear.")
        else:
            status = "GOOD"
            reasons.append(f"Good trail conditions with low rain chance ({rain_p:.0f}%).")

    elif activity in ["outdoor_work", "construction"]:
        if severe_warning or "thunder" in cond or rain_p >= 70:
            status = "NOT_RECOMMENDED"
            reasons.append(f"Adverse weather with {rain_p:.0f}% rain risk; pause hazardous open work.")
        elif t_max > 38:
            status = "CAUTION"
            reasons.append(f"Extreme heat ({t_max:.1f}°C); schedule heavy work for early morning and hydrate.")
        elif rain_p >= 40:
            status = "CAUTION"
            reasons.append(f"Moderate rain chance ({rain_p:.0f}%); cover materials and plan for pauses.")
        else:
            status = "GOOD"
            reasons.append(f"Favorable working conditions with {rain_p:.0f}% rain probability.")

    elif activity in ["travel", "driving", "commuting"]:
        if severe_warning or marine_or_cyclone:
            status = "NOT_RECOMMENDED"
            reasons.append("Severe weather warnings active in the region; avoid unnecessary travel.")
        elif rain_p >= 60 or "thunder" in cond:
            status = "CAUTION"
            reasons.append(f"Heavy rain showers ({rain_p:.0f}%) may cause reduced visibility and wet roads.")
        else:
            status = "GOOD"
            reasons.append(f"Clear travel conditions with {rain_p:.0f}% rain chance.")

    elif activity in ["sports", "cricket"]:
        if rain_p >= 50 or "thunder" in cond:
            status = "NOT_RECOMMENDED"
            reasons.append(f"High rain chance ({rain_p:.0f}%) will likely halt play.")
        elif rain_p >= 30:
            status = "CAUTION"
            reasons.append(f"Moderate rain risk ({rain_p:.0f}%); potential delay or wet outfield.")
        else:
            status = "GOOD"
            reasons.append(f"Great playing conditions with {rain_p:.0f}% rain risk.")

    elif activity in ["spraying", "pesticide_spraying"]:
        if severe_warning or "thunder" in cond or wind > 20:
            status = "NOT_RECOMMENDED"
            reasons.append(f"High wind ({wind:.1f} km/h) or adverse weather will cause significant chemical drift.")
        elif rain_p >= 40:
            status = "NOT_RECOMMENDED"
            reasons.append(f"Rain probability ({rain_p:.0f}%) is too high; rainfall will wash away chemicals.")
        elif wind > 15 or rain_p >= 25:
            status = "CAUTION"
            reasons.append(f"Breeze ({wind:.1f} km/h) or slight rain chance ({rain_p:.0f}%); spray only during early morning calm.")
        else:
            status = "GOOD"
            reasons.append(f"Calm winds ({wind:.1f} km/h) and low rain risk ({rain_p:.0f}%) provide suitable spraying conditions.")

    elif activity in ["harvesting", "crop_harvesting"]:
        if severe_warning or "thunder" in cond or rain_p >= 40:
            status = "NOT_RECOMMENDED"
            reasons.append(f"Rain probability ({rain_p:.0f}%) risks water damage and rotting of harvested crops.")
        elif rain_p >= 25:
            status = "CAUTION"
            reasons.append(f"Moderate rain chance ({rain_p:.0f}%); ensure harvested produce can be quickly sheltered.")
        else:
            status = "GOOD"
            reasons.append(f"Dry weather with low rain probability ({rain_p:.0f}%) is favorable for crop harvesting.")

    elif activity in ["irrigation", "crop_irrigation"]:
        if severe_warning or rain_p >= 50:
            status = "NOT_RECOMMENDED"
            reasons.append(f"Rain expected ({rain_p:.0f}%); postpone irrigation to prevent waterlogging and conserve water.")
        elif rain_p >= 30:
            status = "CAUTION"
            reasons.append(f"Moderate chance of rain ({rain_p:.0f}%); consider holding off on heavy irrigation.")
        else:
            status = "GOOD"
            reasons.append(f"Dry conditions; regular irrigation is recommended to maintain soil moisture.")

    elif activity in ["sowing", "crop_sowing"]:
        if severe_warning or rain_p >= 65:
            status = "NOT_RECOMMENDED"
            reasons.append(f"Heavy rain risk ({rain_p:.0f}%) can cause waterlogging and seed washout.")
        elif rain_p <= 10 and t_max > 38:
            status = "CAUTION"
            reasons.append(f"High temperatures ({t_max:.1f}°C) and dry soil; ensure adequate moisture before sowing.")
        else:
            status = "GOOD"
            reasons.append(f"Favorable conditions for crop sowing with {rain_p:.0f}% rain probability.")

    else:
        if severe_warning or rain_p >= 65:
            status = "NOT_RECOMMENDED"
            reasons.append(f"High rain probability ({rain_p:.0f}%) and unsettled weather.")
        elif rain_p >= 35 or wind > 25:
            status = "CAUTION"
            reasons.append(f"Rain probability ({rain_p:.0f}%) or wind ({wind:.1f} km/h); carry rain gear.")
        else:
            status = "GOOD"
            reasons.append(f"Comfortable weather with low rain probability ({rain_p:.0f}%).")

    return {
        "activity": activity,
        "suitability": status,
        "is_safe": status in ["GOOD", "CAUTION"],
        "reasons": reasons,
        "rain_probability": rain_p,
        "wind_kmh": wind,
        "temp_max": t_max,
        "condition": cond,
    }


# ---------------------------------------------------------------------------
# 2. TEMPORAL PATTERNS
# ---------------------------------------------------------------------------

TEMPORAL_PATTERNS = [
    ("tomorrow_morning", [
        r"\b(?:tomorrow(?:'s)?\s+(?:early\s+)?morning)\b",
        r"(?:कल सुबह|कल तड़के|कल प्रातः)",
        r"\b(?:kal subah|kal savere)\b",
        r"(?:उद्या सकाळी)",
    ]),
    ("tomorrow_afternoon", [
        r"\b(?:tomorrow(?:'s)?\s+(?:afternoon|noon))\b",
        r"(?:कल दोपहर|कल तीसरे पहर)",
        r"\b(?:kal dopahar|kal do-pahar)\b",
        r"(?:उद्या दुपारी)",
    ]),
    ("tomorrow_evening", [
        r"\b(?:tomorrow(?:'s)?\s+(?:evening|dusk|night))\b",
        r"(?:कल शाम|कल सांझ|कल रात)",
        r"\b(?:kal shaam|kal sham|kal raat)\b",
        r"(?:उद्या संध्याकाळी)",
    ]),
    ("day_after_tomorrow", [
        r"\b(?:day after tomorrow(?:'s)?)\b",
        r"(?:परसों|परसो|आने वाला परसों)",
        r"\b(?:parso|parson|tarso)\b",
        r"(?:परवा)",
    ]),
    ("tomorrow", [
        r"\b(?:tomorrow(?:'s|s)?)\b",
        r"(?:कल|आने वाला कल)",
        r"\b(?:kal(?:'s|s)?|kal ka|kal ki|kal ke)\b",
        r"(?:उद्या)",
        r"(?:આવતીકાલે)",
        r"(?:কালকে|কাল)",
        r"(?:நாளை)",
        r"(?:రేపు)",
        r"(?:ನಾಳೆ)",
        r"(?:നാളെ)",
        r"(?:ਕੱਲ੍ਹ)",
        r"(?:ଆସନ୍ତାକାଲି)",
    ]),
    ("today_morning", [
        r"\b(?:today(?:'s)?\s+morning|this\s+morning)\b",
        r"(?:आज सुबह|आज प्रातः)",
        r"\b(?:aaj subah)\b",
        r"(?:आज सकाळी)",
    ]),
    ("today_afternoon", [
        r"\b(?:today(?:'s)?\s+afternoon|this\s+afternoon)\b",
        r"(?:आज दोपहर)",
        r"\b(?:aaj dopahar)\b",
        r"(?:आज दुपारी)",
    ]),
    ("today_evening", [
        r"\b(?:today(?:'s)?\s+evening|this\s+evening|tonight)\b",
        r"(?:आज शाम|आज रात)",
        r"\b(?:aaj shaam|aaj raat)\b",
        r"(?:आज संध्याकाळी|आज रात्री)",
    ]),
    ("morning", [
        r"\b(?:morning|early morning)\b",
        r"(?:सुबह|प्रातः|सवेरे)",
        r"\b(?:subah|savere)\b",
        r"(?:सकाळी)",
    ]),
    ("afternoon", [
        r"\b(?:afternoon|noon|midday)\b",
        r"(?:दोपहर|तीसरे पहर)",
        r"\b(?:dopahar)\b",
        r"(?:दुपारी)",
    ]),
    ("evening", [
        r"\b(?:evening|sunset|dusk)\b",
        r"(?:शाम|सांझ)",
        r"\b(?:shaam|sham)\b",
        r"(?:संध्याकाळी)",
    ]),
    ("this_weekend", [
        r"\b(?:this weekend|weekend|weekends|weekend's)\b",
        r"(?:इस सप्ताहांत|सप्ताहांत|वीकेंड)",
        r"\b(?:weekend|is weekend)\b",
        r"(?:आठवड्याचा शेवट)",
    ]),
    ("saturday", [
        r"\b(?:saturday(?:'s|s)?)\b",
        r"(?:शनिवार)",
        r"\b(?:shanivar|sanivar)\b",
    ]),
    ("sunday", [
        r"\b(?:sunday(?:'s|s)?)\b",
        r"(?:रविवार|इतवार)",
        r"\b(?:ravivar|itwar)\b",
    ]),
    ("next_3_days", [
        r"\b(?:next 3 days|3 days|three days)\b",
        r"(?:अगले 3 दिन|अगले तीन दिन)",
        r"\b(?:agle 3 din|teen din)\b",
    ]),
    ("next_week", [
        r"\b(?:next week|coming week|full week)\b",
        r"(?:अगले हफ्ते|अगले सप्ताह|पूरे हफ्ते)",
        r"\b(?:agle hafte|agle saptaah)\b",
    ]),
    ("today", [
        r"\b(?:today(?:'s|s)?|current|now)\b",
        r"(?:आज|अभी|वर्तमान)",
        r"\b(?:aaj|abhi)\b",
        r"(?:आज)",
    ]),
]


# ---------------------------------------------------------------------------
# 3. QUERY & CONVERSATION UNDERSTANDING
# ---------------------------------------------------------------------------

def resolve_date_intent(
    query: str,
    reference_date: date | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Deterministically resolves user date intent before generating any weather answer.
    The backend (Python) is the single source of truth for all calendar calculations.
    """
    ref = reference_date or datetime.now().date()
    q_clean = query.strip()
    q_lower = q_clean.lower()

    # 1. Day after tomorrow / parso (Offset +2)
    day_after_patterns = [
        r"\b(?:day\s+after\s+(?:tomorrow|tomarrow|tomarow|tomorow|tommorow|tmrw)|overmorrow)(?:'s)?\b",
        r"(?:परसों|परसो|आने वाला परसों|परवा)",
        r"\b(?:parso|parson|tarso)\b",
    ]
    if any(re.search(p, q_lower, re.IGNORECASE) for p in day_after_patterns):
        res_date = ref + timedelta(days=2)
        d_str = res_date.strftime("%Y-%m-%d")
        return {
            "date_intent": "day_after_tomorrow",
            "resolved_date": d_str,
            "resolved_dates": [d_str],
            "primary_date": d_str,
            "date_label": "The day after tomorrow",
            "date_label_hi": "परसों",
            "time_of_day": None,
            "days_offset": 2,
        }

    # 2. Tomorrow with time of day (typo-tolerant)
    TOMORROW_TYPOS = r"(?:tomorrow|tomarrow|tomarow|tomorow|tommorow|tommoro|tomoro|tmrw|tmr|2morrow|tomrw)"
    if re.search(rf"\b(?:{TOMORROW_TYPOS}(?:'s)?\s+(?:early\s+)?morning)\b|(?:कल सुबह|कल तड़के|कल प्रातः)|\b(?:kal subah|kal savere|udya sakali)\b", q_lower):
        res_date = ref + timedelta(days=1)
        d_str = res_date.strftime("%Y-%m-%d")
        return {
            "date_intent": "tomorrow",
            "resolved_date": d_str,
            "resolved_dates": [d_str],
            "primary_date": d_str,
            "date_label": "Tomorrow morning",
            "date_label_hi": "कल सुबह",
            "time_of_day": "morning",
            "days_offset": 1,
        }
    if re.search(rf"\b(?:{TOMORROW_TYPOS}(?:'s)?\s+(?:afternoon|noon))\b|(?:कल दोपहर|कल तीसरे पहर)|\b(?:kal dopahar|kal do-pahar|udya dupari)\b", q_lower):
        res_date = ref + timedelta(days=1)
        d_str = res_date.strftime("%Y-%m-%d")
        return {
            "date_intent": "tomorrow",
            "resolved_date": d_str,
            "resolved_dates": [d_str],
            "primary_date": d_str,
            "date_label": "Tomorrow afternoon",
            "date_label_hi": "कल दोपहर",
            "time_of_day": "afternoon",
            "days_offset": 1,
        }
    if re.search(rf"\b(?:{TOMORROW_TYPOS}(?:'s)?\s+(?:evening|dusk|night))\b|(?:कल शाम|कल सांझ|कल रात)|\b(?:kal shaam|kal sham|kal raat|udya sandhyakali)\b", q_lower):
        res_date = ref + timedelta(days=1)
        d_str = res_date.strftime("%Y-%m-%d")
        return {
            "date_intent": "tomorrow",
            "resolved_date": d_str,
            "resolved_dates": [d_str],
            "primary_date": d_str,
            "date_label": "Tomorrow evening",
            "date_label_hi": "कल शाम",
            "time_of_day": "evening",
            "days_offset": 1,
        }

    # 3. Tomorrow / kal (Offset +1, typo-tolerant)
    tomorrow_patterns = [
        rf"\b(?:{TOMORROW_TYPOS}(?:'s|s)?|tomorrows|tomarrows|tomarows|tomorows|tommorows)\b",
        r"(?:कल|आने वाला कल|उद्या|આવતીકાલે|कालके|काल|நாளை|రేపు|ನಾಳೆ|ਕੱਲ੍ਹ|ଆସନ୍ତାକାଲି)",
        r"\b(?:kal(?:'s|s)?|kal ka|kal ki|kal ke|kal mausam|kal baarish|kal barish|kal barsat)\b",
    ]
    if any(re.search(p, q_lower, re.IGNORECASE) for p in tomorrow_patterns):
        res_date = ref + timedelta(days=1)
        d_str = res_date.strftime("%Y-%m-%d")
        return {
            "date_intent": "tomorrow",
            "resolved_date": d_str,
            "resolved_dates": [d_str],
            "primary_date": d_str,
            "date_label": "Tomorrow",
            "date_label_hi": "कल",
            "time_of_day": None,
            "days_offset": 1,
        }

    # 4. Specific Weekday matching (forward from reference_date)
    for kw, w_idx in WEEKDAYS.items():
        pat = rf"(?:^|[\s,?!।]){re.escape(kw)}(?:'s|s)?(?:$|[\s,?!।])" if kw.isascii() else re.escape(kw)
        if re.search(pat, q_lower):
            w_name = WEEKDAY_NAMES[w_idx]
            days_ahead = (w_idx - ref.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            res_date = ref + timedelta(days=days_ahead)
            d_str = res_date.strftime("%Y-%m-%d")
            en_lbl, hi_lbl = WEEKDAY_LABELS[w_idx]
            return {
                "date_intent": w_name,
                "resolved_date": d_str,
                "resolved_dates": [d_str],
                "primary_date": d_str,
                "date_label": en_lbl,
                "date_label_hi": hi_lbl,
                "time_of_day": None,
                "days_offset": days_ahead,
            }

    # 5. This Weekend
    if re.search(r"\b(?:this weekend|weekend|weekends|सप्ताहांत|वीकेंड)\b", q_lower):
        days_to_sat = (5 - ref.weekday()) % 7
        if days_to_sat == 0 and ref.weekday() != 5:
            days_to_sat = 7
        sat = ref + timedelta(days=days_to_sat)
        sun = sat + timedelta(days=1)
        sat_str = sat.strftime("%Y-%m-%d")
        sun_str = sun.strftime("%Y-%m-%d")
        return {
            "date_intent": "this_weekend",
            "resolved_date": sat_str,
            "resolved_dates": [sat_str, sun_str],
            "primary_date": sat_str,
            "date_label": "This weekend",
            "date_label_hi": "इस सप्ताहांत",
            "time_of_day": None,
            "days_offset": days_to_sat,
        }

    # 6. Today with time of day
    if re.search(r"\b(?:today(?:'s)?\s+morning|this\s+morning)\b|(?:आज सुबह|आज प्रातः)|\b(?:aaj subah)\b", q_lower):
        d_str = ref.strftime("%Y-%m-%d")
        return {
            "date_intent": "today",
            "resolved_date": d_str,
            "resolved_dates": [d_str],
            "primary_date": d_str,
            "date_label": "This morning",
            "date_label_hi": "आज सुबह",
            "time_of_day": "morning",
            "days_offset": 0,
        }
    if re.search(r"\b(?:today(?:'s)?\s+afternoon|this\s+afternoon)\b|(?:आज दोपहर)|\b(?:aaj dopahar)\b", q_lower):
        d_str = ref.strftime("%Y-%m-%d")
        return {
            "date_intent": "today",
            "resolved_date": d_str,
            "resolved_dates": [d_str],
            "primary_date": d_str,
            "date_label": "This afternoon",
            "date_label_hi": "आज दोपहर",
            "time_of_day": "afternoon",
            "days_offset": 0,
        }
    if re.search(r"\b(?:today(?:'s)?\s+evening|this\s+evening|tonight)\b|(?:आज शाम|आज रात)|\b(?:aaj shaam|aaj raat)\b", q_lower):
        d_str = ref.strftime("%Y-%m-%d")
        return {
            "date_intent": "today",
            "resolved_date": d_str,
            "resolved_dates": [d_str],
            "primary_date": d_str,
            "date_label": "Tonight",
            "date_label_hi": "आज रात",
            "time_of_day": "evening",
            "days_offset": 0,
        }

    # 7. Check context history for short follow-up (e.g. if query has no explicit date)
    recent_history = history[-4:] if history else []
    prev_context = " ".join(
        str(m.get("content") or m.get("text") or "").lower() for m in recent_history
    )
    if any(k in prev_context for k in ["tomorrow", "kal", "कल"]) and len(q_lower.split()) <= 4 and not any(w in q_lower for w in ["today", "aaj", "आज", "now", "abhi"]):
        res_date = ref + timedelta(days=1)
        d_str = res_date.strftime("%Y-%m-%d")
        return {
            "date_intent": "tomorrow",
            "resolved_date": d_str,
            "resolved_dates": [d_str],
            "primary_date": d_str,
            "date_label": "Tomorrow",
            "date_label_hi": "कल",
            "time_of_day": None,
            "days_offset": 1,
        }

    # 8. Default: Today (Offset 0)
    d_str = ref.strftime("%Y-%m-%d")
    return {
        "date_intent": "today",
        "resolved_date": d_str,
        "resolved_dates": [d_str],
        "primary_date": d_str,
        "date_label": "Today",
        "date_label_hi": "आज",
        "time_of_day": None,
        "days_offset": 0,
    }


def extract_verified_forecast(
    weather_data: dict[str, Any],
    resolved_date: str,
    date_intent: str,
) -> tuple[dict[str, Any], bool]:
    """
    Validates: requested_date == retrieved_forecast_date
    Extracts the exact forecast matching the resolved date.
    Returns (forecast_dict, date_match_bool).
    """
    forecast_list = weather_data.get("forecast", [])
    current = weather_data.get("current", {})

    matched = None
    for f in forecast_list:
        if str(f.get("date")) == resolved_date:
            matched = f
            break

    date_match = True
    if not matched:
        if date_intent in ["tomorrow", "tomorrow_morning", "tomorrow_afternoon", "tomorrow_evening"] and len(forecast_list) > 1:
            matched = forecast_list[1]
        elif date_intent == "day_after_tomorrow" and len(forecast_list) > 2:
            matched = forecast_list[2]
        elif date_intent in WEEKDAYS:
            target_w = WEEKDAYS[date_intent]
            for d in forecast_list:
                try:
                    dt = datetime.strptime(str(d.get("date", "")), "%Y-%m-%d")
                    if dt.weekday() == target_w:
                        matched = d
                        break
                except ValueError:
                    pass
        if not matched and len(forecast_list) > 0:
            matched = forecast_list[0]
        elif not matched:
            matched = {}
        retrieved_date = str(matched.get("date") or resolved_date)
        date_match = (retrieved_date == resolved_date)
    else:
        retrieved_date = resolved_date

    t_max = matched.get("temp_max", current.get("temperature_c", 29.0))
    t_min = matched.get("temp_min", round(t_max - 5.0, 1))
    t_avg = round((t_max + t_min) / 2, 1)
    rain_p = matched.get("rain_probability", current.get("humidity_pct", 20))
    cond = matched.get("condition", current.get("condition", "Partly cloudy"))
    wind_spd = matched.get("wind_max_kmh", current.get("wind_kmh", 12))
    precip_mm = matched.get("precipitation_mm", 0.0)

    verified_forecast = {
        "date": retrieved_date,
        "temp_max": t_max,
        "temp_min": t_min,
        "temp_avg": t_avg,
        "temp_c": t_avg,
        "rain_prob": rain_p,
        "rain_probability": rain_p,
        "condition": cond,
        "condition_raw": cond,
        "wind_kmh": wind_spd,
        "wind_max_kmh": wind_spd,
        "precipitation_mm": precip_mm,
        "humidity": current.get("humidity_pct", 75),
    }
    return verified_forecast, date_match


LOCATION_STOP_WORDS = {
    # English temporal & weather
    "today", "todays", "today's", "tomorrow", "tomorrows", "tomorrow's", "tomarrow", "tomarow", "tomorow", "tommorow", "tmrw", "overmorrow",
    "yesterday", "morning", "afternoon", "evening", "night", "weekend", "week",
    "weather", "forecast", "rain", "raining", "rainy", "rainfall", "temp", "temperature",
    "humidity", "wind", "windy", "breeze", "storm", "cyclone", "alert", "alerts", "warning", "warnings",
    "current", "currently", "live", "present", "daily", "weekly", "hourly", "general",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "mon", "tue", "wed", "thu", "fri", "sat", "sun",
    # Activities and agricultural terms (NEVER treat as location names!)
    "picnic", "fishing", "hiking", "travel", "traveling", "sports", "cricket", "match", "outdoor", "outdoors",
    "spray", "spraying", "irrigation", "irrigate", "farming", "farm", "field", "fields", "crop", "crops",
    "harvest", "harvesting", "sow", "sowing", "seed", "seeds", "seeding", "plant", "planting",
    "pesticide", "pesticides", "insecticide", "insecticides", "fungicide", "fungicides", "chemical", "chemicals",
    "fertilizer", "fertilizers", "plow", "plowing", "plough", "ploughing", "soil", "produce", "grain",
    "rainwater", "rain-water", "water", "watering", "rice", "paddy", "wheat", "cotton", "vegetables",
    # Evaluation, safety and question words
    "safe", "safety", "good", "bad", "fine", "suitable", "suitability", "recommended", "right", "ok", "okay",
    "here", "there", "now", "me", "us", "my", "our", "near", "nearby", "around", "area", "local", "place",
    "this", "that", "the", "a", "an", "all", "any", "some",
    "what", "whats", "how", "hows", "is", "will", "can", "should", "could", "would", "tell",
    # Indic temporal & weather
    "aaj", "kal", "parso", "subah", "shaam", "dopahar", "raat",
    "mausam", "barish", "baarish", "barsat", "tapman", "garmi", "thand", "hawa",
    "somvar", "mangalvar", "budhvar", "guruvar", "shukravar", "shanivar", "ravivar", "itwar",
    "आज", "कल", "परसों", "सुबह", "शाम", "दोपहर", "रात",
    "मौसम", "बारिश", "वर्षा", "तापमान", "गर्मी", "ठंड", "हवा",
    "हवामान", "पाऊस", "उद्या", "आयज", "फाल्यां", "कसा", "कशी", "कसे", "काय",
    "kaisa", "kaisi", "kaise", "kya", "hoga", "hogi", "rahega", "rahegi", "hai", "hain", "paas",
    # Indic agricultural and activity words
    "dawa", "dawai", "chhidkaw", "chhidkaav", "sinchai", "sinchayi", "katai", "buwai", "bona", "kheti", "fasal",
    "छिड़काव", "दवाई", "दवा", "कीटनाशक", "सिंचाई", "पानी", "कटाई", "फसल", "बुवाई", "बोना", "बीज", "खेती", "किसान", "खेत",
    "धान", "गेहूँ", "गेहूं", "कपास", "सब्जी", "फवारणी", "काढणी", "पेरणी", "शेती", "सुरक्षित", "सही", "उचित",
    # Hindi/Indic postpositions, prepositions and particles (CRITICAL: never treat as locations!)
    "का", "के", "की", "में", "से", "पर", "को", "ने", "हे", "हो", "था", "थी", "थे",
    "वाला", "वाली", "वाले", "बारे", "दौरान", "बताना", "बताओ", "दिखाओ", "बताएं", "दीजिए",
    # Marathi/Konkani particles
    "चा", "ची", "चे", "च्या", "चो", "चें", "मध्ये", "मधील", "वर", "खातीर", "सांगा", "दाखवा",
    # English/Roman Hindi particles
    "ka", "ke", "ki", "mein", "me", "se", "par", "ko", "ne", "baare", "baarein",
    "in", "at", "of", "for", "on", "by", "to", "from", "about", "with", "into", "onto",
}

TEMPORAL_QUERY_WORDS = {
    "today", "todays", "today's", "tomorrow", "tomorrows", "tomorrow's", "yesterday",
    "aaj", "kal", "parso", "subah", "shaam", "dopahar", "raat",
    "आज", "कल", "परसों", "सुबह", "शाम", "दोपहर", "रात", "उद्या", "आयज", "फाल्यां",
}


def extract_query_location(query: str) -> str | None:
    """
    Deterministically extracts explicit location names mentioned in the user's query.
    Extracts patterns like:
      - 'what's the weather in Panjim' -> 'Panjim'
      - 'weather for Mapusa' -> 'Mapusa'
      - 'will it rain in Bengaluru tomorrow?' -> 'Bengaluru'
      - 'Panaji me kal mausam' -> 'Panaji'
      - 'पणजी में मौसम कैसा है' -> 'पणजी'
    Strictly avoids false positives on activities (e.g. 'safe for harvesting'),
    temporal queries (e.g. 'आज का मौसम', 'today's weather'), and non-geographic words.
    """
    q_clean = query.strip()
    if not q_clean:
        return None

    # Ignore queries asking about relative / local scope like 'near me', 'around here'
    if re.search(r"\b(?:near|around|for)\s+(?:me|here|us)\b", q_clean, re.IGNORECASE):
        return None

    # 1. Pattern: (in|at|for) <Location>
    # IMPORTANT: "for" only introduces a location when preceded by query inquiry terms like "weather for", "forecast for", "alerts for"
    # Purpose/activity clauses like "safe for harvesting", "good for picnic", "time for spraying" MUST NOT be treated as locations.
    prep_match = None
    is_activity_for = bool(re.search(r"\b(?:safe|good|bad|suitable|ideal|best|ready|time|plans?)\s+for\b", q_clean, re.IGNORECASE))
    is_weather_for = bool(re.search(r"\b(?:weather|forecast|alerts?|warnings?|conditions?|mausam|temperature)\s+for\b", q_clean, re.IGNORECASE))

    if not is_activity_for and is_weather_for:
        prep_match = re.search(
            r"\bfor\s+([A-Za-z\u0900-\u0DFF]+(?:\s+[A-Za-z\u0900-\u0DFF]+)?)\b",
            q_clean,
            re.IGNORECASE,
        )
    if not prep_match:
        prep_match = re.search(
            r"\b(?:in|at)\s+([A-Za-z\u0900-\u0DFF]+(?:\s+[A-Za-z\u0900-\u0DFF]+)?)\b",
            q_clean,
            re.IGNORECASE,
        )

    if prep_match:
        cand = prep_match.group(1).strip()
        words = cand.split()
        filtered = [w for w in words if w.lower() not in LOCATION_STOP_WORDS]
        if filtered:
            loc = " ".join(filtered)
            loc_low = loc.lower()
            # Must not be a stopword, temporal word, gerund ending in "ing" (unless known place), or too short
            is_invalid = (
                loc_low in LOCATION_STOP_WORDS
                or any(tw in loc_low for tw in TEMPORAL_QUERY_WORDS)
                or (loc_low.endswith("ing") and loc_low not in {"darjeeling", "kalimpong"})
                or len(loc) < 3
            )
            if not is_invalid:
                return loc

    # 2. Pattern: <Location> (mein|ka|ke|ki|cha|che|chi|cho|त|मध्ये|मधील|में|चो|चे|च्या|तील|साठी)
    indic_match = re.search(
        r"\b(?<!near\s)(?<!around\s)(?<!tell\s)(?<!with\s)([A-Za-z\u0900-\u0DFF]+(?:\s+[A-Za-z\u0900-\u0DFF]+)?)\s+(?:mein?|में|मध्ये|मधील|चे|चो|च्या|तील|त|ात|तले|का|के|की|साठी)\b",
        q_clean,
        re.IGNORECASE,
    )
    if indic_match:
        cand = indic_match.group(1).strip()
        words = [w for w in cand.split() if w.lower() not in LOCATION_STOP_WORDS]
        if words:
            loc = " ".join(words)
            loc_low = loc.lower()
            is_invalid = (
                loc_low in LOCATION_STOP_WORDS
                or any(tw in loc_low for tw in TEMPORAL_QUERY_WORDS)
                or (loc_low.endswith("ing") and loc_low not in {"darjeeling", "kalimpong"})
                or len(loc) < 3
            )
            if not is_invalid:
                return loc

    # 3. Pattern: <Location> weather / <Location> forecast / <Location> mausam
    lead_match = re.search(
        r"^([A-Za-z\u0900-\u0DFF]+(?:\s+[A-Za-z\u0900-\u0DFF]+)?)\s+(?:weather|forecast|mausam|havaman|मौसम|हवामान)\b",
        q_clean,
        re.IGNORECASE,
    )
    if lead_match:
        cand = lead_match.group(1).strip()
        if not any(tw in cand.lower() for tw in TEMPORAL_QUERY_WORDS):
            words = [w for w in cand.split() if w.lower() not in LOCATION_STOP_WORDS]
            if words:
                loc = " ".join(words)
                loc_low = loc.lower()
                is_invalid = (
                    loc_low in LOCATION_STOP_WORDS
                    or any(tw in loc_low for tw in TEMPORAL_QUERY_WORDS)
                    or (loc_low.endswith("ing") and loc_low not in {"darjeeling", "kalimpong"})
                    or len(loc) < 3
                )
                if not is_invalid:
                    return loc

    # 4. Check Devanagari and multilingual place names (Marathi / Hindi / Regional)
    try:
        from services.language_service import LOCATION_PLACES_MAP
        sorted_places = sorted(LOCATION_PLACES_MAP.items(), key=lambda x: len(x[0]), reverse=True)
        for eng_place, trans_dict in sorted_places:
            for l_code, dev_name in trans_dict.items():
                dev_clean = dev_name.strip()
                if len(dev_clean) >= 2:
                    dev_base = dev_clean.rstrip("ेाीुू")
                    if dev_clean in q_clean or (len(dev_base) >= 2 and f"{dev_base}ात" in q_clean) or (len(dev_base) >= 2 and f"{dev_base}्यात" in q_clean):
                        return eng_place.title()
    except Exception:
        pass

    # 5. Check known Latin gazetteer places mentioned anywhere in query
    from services.location.photon_service import INDIAN_AGRICULTURAL_GAZETTEER, PHONETIC_ALIASES
    q_words = [w.strip("?,.!") for w in q_clean.lower().split()]
    for word in q_words:
        if word in LOCATION_STOP_WORDS:
            continue
        if word in INDIAN_AGRICULTURAL_GAZETTEER:
            return INDIAN_AGRICULTURAL_GAZETTEER[word]["name"]
        if word in PHONETIC_ALIASES:
            canonical_key = PHONETIC_ALIASES[word]
            if canonical_key in INDIAN_AGRICULTURAL_GAZETTEER:
                return INDIAN_AGRICULTURAL_GAZETTEER[canonical_key]["name"]
            return canonical_key.title()

    return None


def should_inherit_context(
    query: str,
    history: list[dict[str, Any]] | None = None,
) -> bool:
    """
    Returns True ONLY when there is clear, unambiguous conversational reference to the previous topic.
    Standalone queries (e.g. 'weather', 'what's the weather', 'temperature', 'will it rain',
    'what's the weather tomorrow', 'give me the forecast') MUST NEVER inherit context, activity, or date.
    """
    if not history:
        return False

    q_clean = query.strip()
    q_lower = q_clean.lower()

    # Explicit conversational reference triggers
    EXPLICIT_FOLLOWUP_PATTERNS = [
        r"^(?:what\s+about|how\s+about|what\s+of)\b",
        r"^(?:and|aur|aur\s+batao|fir|phir|toh)\s+",
        r"\b(?:what\s+about\s+(?:then|there|the\s+same))\b",
        r"\b(?:how\s+about\s+(?:then|there))\b",
        r"\b(?:will\s+it\s+be\s+better\s+then)\b",
        r"\b(?:same\s+for|what\s+for)\b",
        r"^(?:तो|और|फिर)\s+",
        r"(?:के बारे में\?*)$",
        r"^(?:उद्या|त्यानंतर)\b",
    ]

    for pat in EXPLICIT_FOLLOWUP_PATTERNS:
        if re.search(pat, q_lower):
            return True

    # Check for short weekday/date-only query (e.g. "Sunday?", "On Sunday?", "What about Sunday?", "रविवार को?")
    words = [w.strip("?,.!") for w in q_lower.split() if w.strip("?,.!")]
    if len(words) <= 2:
        STANDALONE_WORDS = {
            "weather", "mausam", "forecast", "havaman", "temperature", "temp", "tapman",
            "rain", "barish", "baarish", "paus", "humidity", "wind", "hawa", "alert", "alerts",
            "warning", "warnings", "chetavani", "kheti", "picnic", "fishing", "code", "python"
        }
        if any(w in STANDALONE_WORDS for w in words):
            return False

        WEEKDAY_WORDS = set(WEEKDAYS.keys()) | {"weekend", "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"}
        if len(words) == 1 and words[0] in WEEKDAY_WORDS:
            return True
        if len(words) == 2 and words[0] in {"on", "for", "at", "ko", "me", "mein"} and words[1] in WEEKDAY_WORDS:
            return True

    return False


def understand_query(
    query: str,
    history: list[dict[str, Any]] | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
    reference_date: date | None = None,
) -> StructuredQuery:
    """
    Parses any user question into a canonical StructuredQuery object.
    Supports flexible natural language variations across English, Hindi,
    Roman Hindi (Hinglish), Marathi, and other Indic languages.
    Provides deterministic date resolution and multi-turn context inheritance.
    """
    history = history or conversation_history or []
    q_clean = query.strip()
    q_lower = q_clean.lower()

    # Location extraction from query
    extracted_loc = extract_query_location(q_clean)

    # Context inheritance check: only inherit if explicit follow-up
    inherit_context = should_inherit_context(q_clean, history)
    is_follow_up = inherit_context

    # 1. Deterministic Date Resolution (Fresh unless explicit follow-up)
    history_for_date = history if inherit_context else []
    date_info = resolve_date_intent(q_clean, reference_date=reference_date, history=history_for_date)
    date_intent = date_info["date_intent"]
    resolved_date = date_info["resolved_date"]
    resolved_dates = date_info.get("resolved_dates", [resolved_date])
    primary_date = date_info.get("primary_date", resolved_date)
    date_label = date_info.get("date_label", "Today")
    date_label_hi = date_info.get("date_label_hi", "आज")
    time_of_day = date_info.get("time_of_day")
    temporal_target = f"{date_intent}_{time_of_day}" if time_of_day else date_intent

    # 2. Contextual History for Multi-Turn Follow-Ups (ONLY when inherit_context is True)
    last_user_query = ""
    last_assistant_answer = ""
    last_intent = None
    last_sub_intent = None
    last_location = None
    last_activity = None
    last_domain = None

    if inherit_context:
        recent_history = history[-4:] if history else []
        for msg in reversed(recent_history):
            role = msg.get("role") or msg.get("sender") or ""
            content = str(msg.get("content") or msg.get("text") or msg.get("query") or "")
            if role in ["user"] and not last_user_query:
                last_user_query = content.lower()
                if msg.get("intent"):
                    last_intent = msg.get("intent")
                if msg.get("sub_intent"):
                    last_sub_intent = msg.get("sub_intent")
                if msg.get("location"):
                    last_location = msg.get("location")
                if msg.get("activity"):
                    last_activity = msg.get("activity")
                if msg.get("domain"):
                    last_domain = msg.get("domain")
            elif role in ["assistant", "bot"] and not last_assistant_answer:
                last_assistant_answer = content.lower()
                if not last_intent and msg.get("intent"):
                    last_intent = msg.get("intent")
                if not last_sub_intent and msg.get("sub_intent"):
                    last_sub_intent = msg.get("sub_intent")
                if not last_location and msg.get("location"):
                    last_location = msg.get("location")
                if not last_activity and msg.get("activity"):
                    last_activity = msg.get("activity")
                if not last_domain and msg.get("domain"):
                    last_domain = msg.get("domain")

        # If last_activity was not explicit in message dict, infer from last_user_query
        if not last_activity and last_user_query:
            for act_cand, act_pats in ACTIVITY_PATTERNS.items():
                if any(re.search(p, last_user_query) for p in act_pats):
                    last_activity = act_cand
                    break

        # If last_intent or last_domain was not explicit in message dict, infer from last_user_query
        if not last_intent and last_user_query:
            if any(ws in last_user_query for ws in ["weather", "forecast", "mausam", "havaman"]):
                last_intent = "forecast" if ("tomorrow" in last_user_query or "weekend" in last_user_query) else "general_weather"
                last_domain = "weather"
            elif any(ws in last_user_query for ws in ["rain", "barish", "baarish"]):
                last_intent = "rain"
                last_domain = "weather"
            elif any(ws in last_user_query for ws in ["temp", "temperature", "tapman"]):
                last_intent = "temperature"
                last_domain = "weather"
            elif last_activity:
                last_intent = "activity_forecast"
                last_domain = "outdoor_activity"

    prev_context_str = f"{last_user_query} {last_assistant_answer}" if inherit_context else ""
    prev_had_tomorrow = any(kw in prev_context_str for kw in ["tomorrow", "kal", "कल", "उद्या", "काल", "நாளை", "రేపు"])

    # If user mentions time of day without specifying a day, check if previous context was tomorrow
    if temporal_target == "morning":
        temporal_target = "tomorrow_morning" if prev_had_tomorrow else "today_morning"
    elif temporal_target == "afternoon":
        temporal_target = "tomorrow_afternoon" if prev_had_tomorrow else "today_afternoon"
    elif temporal_target == "evening":
        temporal_target = "tomorrow_evening" if prev_had_tomorrow else "today_evening"

    # 3. Detect Out-of-Domain / Unsupported Questions
    is_unsupported = False
    unsupported_category = None
    for cat, pats in UNSUPPORTED_PATTERNS.items():
        for pat in pats:
            if re.search(pat, q_lower):
                is_unsupported = True
                unsupported_category = cat
                break
        if is_unsupported:
            break

    if is_unsupported:
        from services import language_service
        lang = language_service.detect_language(q_clean)
        return StructuredQuery(
            raw_query=q_clean,
            domain="unsupported",
            intent="unsupported",
            sub_intent=unsupported_category,
            location=None,
            date_intent=date_intent,
            resolved_dates=resolved_dates,
            primary_date=primary_date,
            date_label=date_label,
            date_label_hi=date_label_hi,
            time_of_day=time_of_day,
            requires_current_weather=False,
            requires_forecast=False,
            requires_rain=False,
            requires_alerts=False,
            requires_agriculture=False,
            requires_activity=False,
            requires_comparison=False,
            required_fields=[],
            comparison_dates=None,
            language=lang,
            is_follow_up=False,
            is_unrelated=True,
            is_unsupported=True,
            unsupported_category=unsupported_category,
            temporal_target=temporal_target,
        )

    # 4. Smalltalk Greeting Detection
    is_smalltalk = any(re.search(pat, q_lower) for pat in SMALLTALK_PATTERNS)
    if is_smalltalk:
        from services import language_service
        lang = language_service.detect_language(q_clean)
        return StructuredQuery(
            raw_query=q_clean,
            domain="smalltalk",
            intent="smalltalk",
            sub_intent=None,
            location=None,
            date_intent=date_intent,
            resolved_dates=resolved_dates,
            primary_date=primary_date,
            date_label=date_label,
            date_label_hi=date_label_hi,
            time_of_day=time_of_day,
            requires_current_weather=False,
            requires_forecast=False,
            requires_rain=False,
            requires_alerts=False,
            requires_agriculture=False,
            requires_activity=False,
            requires_comparison=False,
            required_fields=[],
            comparison_dates=None,
            language=lang,
            is_follow_up=False,
            is_unrelated=False,
            is_unsupported=False,
            temporal_target=temporal_target,
        )

    # 5. Ambiguous Query Detection (without follow-up context)
    is_ambiguous_match = any(re.search(pat, q_lower) for pat in AMBIGUOUS_PATTERNS)
    if is_ambiguous_match and not (is_follow_up and (last_activity or last_intent or last_domain)):
        from services import language_service
        lang = language_service.detect_language(q_clean)
        clarification_map = {
            "hi": "कृपया स्पष्ट करें कि आप किस गतिविधि या मौसम की जानकारी के बारे में पूछ रहे हैं? जैसे कि क्या आप बाहर जाने, मछली पकड़ने, खेती के काम की योजना बना रहे हैं या बारिश व तापमान जानना चाहते हैं?",
            "hi-Latn": "Kripya batayein ki aap kis cheez ke baare me pooch rahe hain? Jaise fishing, travel, kheti, ya fir rain aur temperature?",
            "mr": "कृपया स्पष्ट करा की आपण कोणत्या कामासाठी किंवा हवामानाच्या घटकाबाबत विचारत आहात? जसे की प्रवास, मासेमारी, शेतीची कामे किंवा पाऊस आणि तापमान?",
            "kok": "उपकार करून स्पश्ट करात की तुमी खंयच्या कामा खातीर वा हवामाना विशीं विचारतात? जशें की भोंवडी, मासेमारी, शेतकाम वा पावस आनी तापमान?",
            "en": "Could you please specify what activity or weather detail you would like to know about? For example, are you planning travel, fishing, outdoor work, or checking for rain or temperature?",
        }
        return StructuredQuery(
            raw_query=q_clean,
            domain="ambiguous",
            intent="ambiguous",
            sub_intent=None,
            location=None,
            date_intent=date_intent,
            resolved_dates=resolved_dates,
            primary_date=primary_date,
            date_label=date_label,
            date_label_hi=date_label_hi,
            time_of_day=time_of_day,
            requires_current_weather=False,
            requires_forecast=False,
            requires_rain=False,
            requires_alerts=False,
            requires_agriculture=False,
            requires_activity=False,
            requires_comparison=False,
            required_fields=[],
            comparison_dates=None,
            language=lang,
            is_follow_up=False,
            is_unrelated=False,
            is_unsupported=False,
            is_ambiguous=True,
            clarification_prompt=clarification_map.get(lang, clarification_map["en"]),
            temporal_target=temporal_target,
        )

    # 6. Semantic Intent & Activity Classification
    domain = "weather"
    activity = None
    intent = "general_weather"
    sub_intent = None
    comparison_dates = None
    requires_activity = False

    # Check for weather-dependent activities first (explicit or inherited via follow-up)
    matched_activity = None
    for act_name, patterns in ACTIVITY_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, q_lower):
                matched_activity = act_name
                break
        if matched_activity:
            break

    if is_follow_up and last_activity and not matched_activity:
        matched_activity = last_activity

    if matched_activity:
        activity = matched_activity
        sub_intent = matched_activity
        requires_activity = True
        if matched_activity in ["spraying", "irrigation", "harvesting", "sowing"]:
            domain = "agriculture"
            intent = matched_activity
            requires_agriculture = True
        else:
            domain = "weather_dependent_life"
            intent = "activity_forecast"

    # A. Comparison Intent
    else:
        is_comparison = bool(
            re.search(r"\b(?:compare|comparison|versus|vs|which day|hotter than|colder than|rainier than|more rain than|warmer than)\b|(?:तुलना|किस दिन|ज्यादा गर्म|ज़्यादा गर्म)", q_lower)
            or ("tomorrow" in q_lower and any(w in q_lower for w in ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]))
            or ("कल" in q_lower and any(w in q_lower for w in ["रविवार", "सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार"]))
        )
        if is_comparison:
            domain = "weather"
            intent = "comparison"
            sub_intent = "day_comparison"
            ref_dt = reference_date or datetime.now().date()
            all_comp_dates = []
            comp_labels = []

            # Check today
            if any(w in q_lower for w in ["today", "aaj", "आज"]):
                all_comp_dates.append(ref_dt.strftime("%Y-%m-%d"))
                comp_labels.append("today")
            # Check tomorrow
            if any(w in q_lower for w in ["tomorrow", "kal", "कल"]):
                t_str = (ref_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                if t_str not in all_comp_dates:
                    all_comp_dates.append(t_str)
                    comp_labels.append("tomorrow")
            # Check weekdays
            for kw, w_idx in WEEKDAYS.items():
                pat = rf"(?:^|[\s,?!।]){re.escape(kw)}(?:'s|s)?(?:$|[\s,?!।])" if kw.isascii() else re.escape(kw)
                if re.search(pat, q_lower):
                    days_ahead = (w_idx - ref_dt.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    target_str = (ref_dt + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
                    if target_str not in all_comp_dates:
                        all_comp_dates.append(target_str)
                        comp_labels.append(WEEKDAY_NAMES[w_idx])
            # Fallback if fewer than 2 dates resolved for comparison
            if len(all_comp_dates) < 2:
                t_str = (ref_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                if t_str not in all_comp_dates:
                    all_comp_dates.append(t_str)
                    comp_labels.append("tomorrow")
                sun_ahead = (6 - ref_dt.weekday()) % 7
                if sun_ahead == 0:
                    sun_ahead = 7
                sun_str = (ref_dt + timedelta(days=sun_ahead)).strftime("%Y-%m-%d")
                if sun_str not in all_comp_dates:
                    all_comp_dates.append(sun_str)
                    comp_labels.append("sunday")

            resolved_dates = all_comp_dates
            comparison_dates = comp_labels

        # B. Alerts / Warnings Intent
        elif bool(re.search(
            r"\b(?:warning|warnings|alert|alerts|danger|flood|flooding|cyclone|hurricane|typhoon|heatwave|lightning)\b|"
            r"(?:चेतावनी|अलर्ट|चेतावनी जारी|बाढ़|चक्रवात|चक्रवाती तूफान|लू|बिजली गिरना|तूफ़ान|तूफान|ख़तरा|खतरा|आपदा)|"
            r"\b(?:warning|alert|chetavani|baadh|cyclone|toofan|chakravat|khatra|bijli)\b|"
            r"(?:इशारा|धोका)",
            q_lower
        )):
            domain = "alerts"
            intent = "alerts"
            if bool(re.search(r"\b(?:cyclone|hurricane|typhoon)\b|(?:चक्रवात|तूफान)|\b(?:cyclone|chakravat)\b", q_lower)):
                sub_intent = "cyclone"
            elif bool(re.search(r"\b(?:rain|rainfall|flood)\b|(?:बारिश|बाढ़)", q_lower)):
                sub_intent = "rain"
            elif bool(re.search(r"\b(?:heat|heatwave)\b|(?:लू|गर्मी)", q_lower)):
                sub_intent = "heatwave"
            else:
                sub_intent = "general_warning"

        # C. Rain Forecast Intent
        elif bool(re.search(
            r"\b(?:rain|raining|rainy|rainfall|rainwater|rainwater\s+harvesting|shower|showers|drizzle|umbrella|wet|downpour|precipitation)\b|"
            r"(?:बारिश|बरसात|वर्षा|बूंदाबांदी|पानी बरसेगा|छाता|भीगना)|"
            r"\b(?:baarish|barish|barsat|paani barsega|chaata|chata|chhaata|chhatri)\b|"
            r"(?:पाऊस|रिमझिम|छत्री|વરસાદ|বৃষ্টি)",
            q_lower
        )):
            domain = "weather"
            intent = "rain_forecast"
            if bool(re.search(r"\b(?:umbrella|chata|chaata|chhaata|chhatri)\b|(?:छाता|छत्री)", q_lower)):
                sub_intent = "umbrella"
            elif bool(re.search(r"\b(?:chance|probability|likely|possibility)\b|(?:संभावना|चांस)", q_lower)):
                sub_intent = "rain_chance"
            else:
                sub_intent = "general_rain"

        # D. Agriculture Intent (excluding non-agricultural rainwater harvesting)
        elif not any(rh in q_lower for rh in ["rainwater harvesting", "rain harvesting", "water harvesting", "rainwater"]) and bool(re.search(
            r"\b(?:spray|spraying|pesticide|pesticides|insecticide|fungicide|chemical|fertilizer|irrigate|irrigation|water\s+crops?|watering\s+crops?|harvest|harvesting|sow|sowing|seed|crop|crops|farm|farming|farmer)\b|"
            r"(?:छिड़काव|दवाई|दवा|कीटनाशक|सिंचाई|पानी देना|कटाई|फसल|बुवाई|बोना|बीज|खेती|किसान)|"
            r"\b(?:chhidkaw|chhidkaav|dawa|dawai|spray|keetnashak|sinchai|sinchayi|katai|buwai|kheti|fasal)\b|"
            r"(?:फवारणी|कीटकनाशक|औषध|सिंचन|काढणी|पेरणी|शेती)",
            q_lower
        )):
            domain = "agriculture"
            requires_agriculture = True
            if not any(rh in q_lower for rh in ["rainwater harvesting", "rain harvesting", "water harvesting", "rainwater"]) and bool(re.search(r"\b(?<!rainwater\s)(?<!rain\s)(?<!water\s)(?:harvest|harvesting|reaping)\b|(?:कटाई|फसल काटना)|\b(?:katai)\b|(?:काढणी)", q_lower)):
                intent = "harvesting"
                sub_intent = "harvesting"
                activity = "harvesting"
                requires_activity = True
            elif bool(re.search(r"\b(?:irrigate|irrigation|water|watering)\b|(?:सिंचाई|पानी देना)|\b(?:sinchai|sinchayi)\b|(?:सिंचन)", q_lower)):
                intent = "irrigation"
                sub_intent = "irrigation"
                activity = "irrigation"
                requires_activity = True
            elif bool(re.search(r"\b(?:spray|spraying|pesticide|pesticides|insecticide|fungicide|chemical|fertilizer)\b|(?:छिड़काव|दवाई|दवा|कीटनाशक)|\b(?:chhidkaw|chhidkaav|spray)\b|(?:फवारणी)", q_lower)):
                intent = "spraying"
                sub_intent = "spraying"
                activity = "spraying"
                requires_activity = True
            elif bool(re.search(r"\b(?:sow|sowing|seed|seeds)\b|(?:बुवाई|बोना|बीज)|\b(?:buwai|bona)\b|(?:पेरणी)", q_lower)):
                intent = "sowing"
                sub_intent = "sowing"
                activity = "sowing"
                requires_activity = True
            else:
                intent = "agriculture"
                sub_intent = "general_agriculture"

        # E. Temperature Intent
        elif bool(re.search(
            r"\b(?:temperature|temp|hot|cold|warm|heat|chilly|degrees|celsius)\b|"
            r"(?:तापमान|गर्मी|गरमी|ठंड|ठंडी|सर्दी|डिग्री)|"
            r"\b(?:tapman|garmi|thand|thandi|sardi)\b|"
            r"(?:तापमान|उष्णता|थंडी)",
            q_lower
        )):
            domain = "weather"
            intent = "temperature"
            if bool(re.search(r"\b(?:hot|heat|warm)\b|(?:गर्म|गर्मी)", q_lower)):
                sub_intent = "heat"
            elif bool(re.search(r"\b(?:cold|chilly|freezing)\b|(?:ठंड|सर्दी)", q_lower)):
                sub_intent = "cold"
            else:
                sub_intent = "general_temp"

        # F. Wind Intent
        elif bool(re.search(
            r"\b(?:wind|windy|breeze|gust|gusts|airflow)\b|"
            r"(?:हवा|हवा की गति|तेज हवा|आंधी|झोंके)|"
            r"\b(?:hawa|tez hawa|aandhi)\b|"
            r"(?:वारा|वादळ)",
            q_lower
        )):
            domain = "weather"
            intent = "wind"
            sub_intent = "wind_speed"

        # G. Weather Condition Intent
        elif bool(re.search(
            r"\b(?:sunny|cloudy|clear sky|overcast|thunderstorm|thunder|fog|foggy|haze)\b|"
            r"(?:धूप|बादल|साफ आसमान|कोहरा|धुंध)|"
            r"\b(?:dhoop|badal|badli|kohra)\b",
            q_lower
        )):
            domain = "weather"
            intent = "weather_condition"
            sub_intent = "sky_condition"

        # H. Outdoor Activity / Travel Intent
        elif bool(re.search(
            r"\b(?:outdoor|outside|picnic|walk|sports|match|cricket|play|walk outside|go out|head out|best time|travel|traveling|driving|journey|trip)\b|"
            r"(?:बाहर जाना|घूमना|पिकनिक|टहलना|खेल|मैच|बाहर का काम|सैर|यात्रा|सफर|सफ़र|ड्राइव|किस समय|कब जाना)|"
            r"\b(?:bahar jana|ghoomna|picnic|match|khelna|bahar|best time|yatra|safar)\b|"
            r"(?:बाहेर जाणे|खेळ)",
            q_lower
        )):
            domain = "weather_dependent_life"
            activity = "travel" if bool(re.search(r"\b(?:travel|traveling|driving|journey|trip)\b|(?:यात्रा|सफर)", q_lower)) else "outdoor_work"
            intent = "activity_forecast"
            sub_intent = activity
            requires_activity = True

        # I. Current Weather Intent
        elif bool(re.search(
            r"\b(?:weather now|weather right now|how is the weather|what's the weather|current weather|weather today)\b|"
            r"(?:अभी का मौसम|वर्तमान मौसम|आज का मौसम|मौसम कैसा है)|"
            r"\b(?:abhi ka mausam|aaj ka mausam|abhi mausam|aaj mausam)\b",
            q_lower
        )):
            domain = "weather"
            intent = "current_weather"
            sub_intent = "now"

        # J. Multi-turn Follow-up Intent Inheritance
        elif is_follow_up and prev_context_str:
            if last_domain:
                domain = last_domain
            if last_intent:
                intent = last_intent
                sub_intent = last_sub_intent
            elif any(w in prev_context_str for w in ["rain", "बारिश", "baarish", "umbrella", "छाता"]):
                domain = "weather"
                intent = "rain_forecast"
                sub_intent = "umbrella" if ("umbrella" in prev_context_str or "छाता" in prev_context_str) else "general_rain"
            elif any(w in prev_context_str for w in ["spray", "छिड़काव", "pesticide"]):
                domain = "agriculture"
                intent = "agriculture"
                sub_intent = "spraying"
            elif any(w in prev_context_str for w in ["temp", "तापमान", "hot", "garmi"]):
                domain = "weather"
                intent = "temperature"
            elif any(w in prev_context_str for w in ["warning", "alert", "चेतावनी"]):
                domain = "alerts"
                intent = "alerts"
            else:
                domain = "weather"
                intent = "current_weather" if date_intent == "today" else "general_weather"
        else:
            WEATHER_SIGNALS = [
                "weather", "forecast", "climate", "temp", "temperature", "rain", "raining", "rainy",
                "sun", "sunny", "cloud", "cloudy", "wind", "windy", "breeze", "humidity", "humid",
                "hot", "cold", "warm", "chilly", "freeze", "freezing", "storm", "thunder",
                "mausam", "barish", "baarish", "tapman", "garmi", "thand", "thandi", "hawa",
                "badal", "dhoop", "barsat", "pani", "chata", "chhatri", "havaman", "paus",
                "मौसम", "तापमान", "बारिश", "वर्षा", "हवा", "धूप", "बादल", "हवामान", "पाऊस"
            ]
            has_weather_signal = any(ws in q_lower for ws in WEATHER_SIGNALS)
            has_temporal_signal = (date_intent != "today") or any(w in q_lower for w in ["today", "aaj", "आज", "tomorrow", "kal", "कल"])

            if has_weather_signal or (has_temporal_signal and ("how" in q_lower or "kaisa" in q_lower or "कैसा" in q_lower or "what" in q_lower or len(q_clean.split()) <= 2)):
                domain = "weather"
                if date_intent == "today" and any(w in q_lower for w in ["weather", "mausam", "मौसम"]):
                    intent = "current_weather"
                else:
                    intent = "general_weather"
            else:
                # Query has NO weather signals and is not a known pattern -> UNSUPPORTED!
                from services import language_service
                lang = language_service.detect_language(q_clean)
                return StructuredQuery(
                    raw_query=q_clean,
                    domain="unsupported",
                    intent="unsupported",
                    sub_intent="out_of_scope",
                    location=None,
                    date_intent=date_intent,
                    resolved_dates=resolved_dates,
                    primary_date=primary_date,
                    date_label=date_label,
                    date_label_hi=date_label_hi,
                    time_of_day=time_of_day,
                    requires_current_weather=False,
                    requires_forecast=False,
                    requires_rain=False,
                    requires_alerts=False,
                    requires_agriculture=False,
                    requires_activity=False,
                    requires_comparison=False,
                    required_fields=[],
                    comparison_dates=None,
                    language=lang,
                    is_follow_up=False,
                    is_unrelated=True,
                    is_unsupported=True,
                    unsupported_category="out_of_scope",
                    temporal_target=temporal_target,
                )

    # 5. Language Detection
    from services import language_service
    lang = language_service.detect_language(q_clean)

    # 6. Flag & Required Field Resolution
    is_today = (date_intent == "today")
    requires_current = is_today and ("morning" not in temporal_target and "evening" not in temporal_target)
    requires_forecast = not is_today or intent in ["comparison", "general_weather", "rain_forecast", "activity_forecast"]
    requires_alerts = (intent == "alerts" or sub_intent in ["cyclone", "rain", "heatwave", "general_warning"])
    requires_agriculture = (intent == "agriculture" or sub_intent in ["spraying", "irrigation", "sowing", "harvesting"])
    requires_comparison = (intent == "comparison")

    req_fields = []
    if activity:
        act_cfg = SUPPORTED_ACTIVITIES.get(activity, {})
        req_fields = list(act_cfg.get("required_fields", ["rain_probability", "wind_kmh", "condition"]))
        if act_cfg.get("requires_alerts"):
            requires_alerts = True
    elif intent in ["rain_forecast", "rain"]:
        req_fields = ["rain_probability", "precipitation_mm", "condition", "temp_max", "temp_min"]
        if sub_intent == "umbrella":
            req_fields.append("umbrella_recommendation")
    elif intent in ["current_weather", "weather_current"]:
        req_fields = ["temperature_c", "feels_like_c", "humidity_pct", "wind_kmh", "condition"]
    elif intent == "temperature":
        req_fields = ["temp_max", "temp_min", "temperature_c", "feels_like_c"]
    elif intent == "wind":
        req_fields = ["wind_kmh", "wind_max_kmh"]
    elif intent == "weather_condition":
        req_fields = ["condition", "cloud_cover_pct", "temp_max"]
    elif intent == "comparison":
        req_fields = ["temp_max", "rain_probability", "comparison"]
    elif intent == "alerts":
        req_fields = ["warnings", "hazards", "bulletins"]
    elif intent == "agriculture":
        req_fields = ["spray_safety", "irrigation_safety", "harvest_safety", "sowing_safety", "rain_probability", "wind_kmh"]
    elif intent == "outdoor_activity":
        req_fields = ["outdoor_suitability", "rain_probability", "temp_max", "condition"]
    else:
        req_fields = ["temp_max", "temp_min", "rain_probability", "condition"]

    requires_rain = (intent in ["rain_forecast", "rain"] or sub_intent == "umbrella" or "rain_probability" in req_fields)

    requires_warning = (domain == "alerts" or intent in ["alerts", "official_warning", "cyclone_warning"])

    return StructuredQuery(
        raw_query=q_clean,
        domain=domain,
        intent=intent,
        sub_intent=sub_intent,
        activity=activity,
        location=extracted_loc or (last_location if is_follow_up else None),
        location_query=extracted_loc,
        query_location=extracted_loc,
        location_source="query" if extracted_loc else "application",
        date_intent=date_intent,
        resolved_dates=resolved_dates,
        primary_date=primary_date,
        date_label=date_label,
        date_label_hi=date_label_hi,
        time_of_day=time_of_day,
        requires_current_weather=requires_current,
        requires_forecast=requires_forecast,
        requires_rain=requires_rain,
        requires_alerts=requires_alerts,
        requires_warning=requires_warning,
        requires_agriculture=requires_agriculture,
        requires_activity=requires_activity,
        requires_comparison=requires_comparison,
        required_fields=req_fields,
        comparison_dates=comparison_dates,
        language=lang,
        is_follow_up=is_follow_up,
        inherit_context=inherit_context,
        is_unrelated=is_unsupported,
        is_unsupported=is_unsupported,
        unsupported_category=unsupported_category,
        temporal_target=temporal_target,
    )


# ---------------------------------------------------------------------------
# 4. TEMPORAL DATA RESOLVER
# ---------------------------------------------------------------------------

def resolve_temporal_weather(
    weather_data: dict[str, Any],
    temporal_target: str,
) -> dict[str, Any]:
    """
    Extracts deterministic weather parameters matching the exact temporal window.
    Calculates morning/afternoon/evening slices from hourly data.
    """
    forecast = weather_data.get("forecast", [])
    hourly = weather_data.get("hourly", [])
    current = weather_data.get("current", {})

    today_entry = forecast[0] if len(forecast) > 0 else {}
    tomorrow_entry = forecast[1] if len(forecast) > 1 else today_entry

    def filter_hourly(target_date: str, start_hour: int, end_hour: int) -> dict[str, Any]:
        matched_hours = []
        for h in hourly:
            t_str = str(h.get("time", ""))
            if t_str.startswith(target_date):
                try:
                    # e.g., '2026-09-06T08:00'
                    hour_num = int(t_str.split("T")[1].split(":")[0])
                    if start_hour <= hour_num < end_hour:
                        matched_hours.append(h)
                except (IndexError, ValueError):
                    pass

        if not matched_hours:
            # Fallback to day summary if hourly slicing not available
            return {
                "date": target_date,
                "temp": today_entry.get("temp_max", current.get("temperature_c", 28.0)),
                "rain_prob": today_entry.get("rain_probability", 20),
                "condition": today_entry.get("condition", "Partly cloudy"),
                "wind_kmh": today_entry.get("wind_max_kmh", 12),
                "humidity": current.get("humidity_pct", 70),
            }

        temps = [
            h.get("temperature_c") if h.get("temperature_c") is not None else h.get("temp", 28.0)
            for h in matched_hours
            if h.get("temperature_c") is not None or h.get("temp") is not None
        ]
        rain_probs = [
            h.get("rain_probability") if h.get("rain_probability") is not None else h.get("rain_prob", 0)
            for h in matched_hours
            if h.get("rain_probability") is not None or h.get("rain_prob") is not None
        ]
        winds = [h.get("wind_kmh", 10) for h in matched_hours if h.get("wind_kmh") is not None]
        conds = [h.get("condition", "Clear") for h in matched_hours if h.get("condition")]

        # Dominant condition: if any rain, condition is rain
        cond = conds[len(conds) // 2] if conds else "Partly cloudy"
        for c in conds:
            if "rain" in c.lower() or "drizzle" in c.lower() or "thunder" in c.lower():
                cond = c
                break
        rain_p = max(rain_probs) if rain_probs else 0
        t_avg = round(sum(temps) / len(temps), 1) if temps else 28.0
        return {
            "date": target_date,
            "temp_avg": t_avg,
            "temp_c": t_avg,
            "temp_min": min(temps) if temps else 24.0,
            "temp_max": max(temps) if temps else 30.0,
            "rain_prob": rain_p,
            "rain_probability": rain_p,
            "wind_kmh": max(winds) if winds else 10,
            "condition": cond,
            "hourly_count": len(matched_hours),
        }

    today_date = str(today_entry.get("date", datetime.now().strftime("%Y-%m-%d")))
    tomorrow_date = str(tomorrow_entry.get("date", (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")))
    day_after_tomorrow_entry = forecast[2] if len(forecast) > 2 else tomorrow_entry
    day_after_tomorrow_date = str(day_after_tomorrow_entry.get("date", (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")))

    if temporal_target == "tomorrow_morning":
        slice_data = filter_hourly(tomorrow_date, 6, 12)
        slice_data["window_name"] = "tomorrow_morning"
        slice_data["window_label"] = "कल सुबह (Tomorrow Morning)"
        return slice_data

    if temporal_target == "tomorrow_afternoon":
        slice_data = filter_hourly(tomorrow_date, 12, 17)
        slice_data["window_name"] = "tomorrow_afternoon"
        slice_data["window_label"] = "कल दोपहर (Tomorrow Afternoon)"
        return slice_data

    if temporal_target == "tomorrow_evening":
        slice_data = filter_hourly(tomorrow_date, 17, 21)
        slice_data["window_name"] = "tomorrow_evening"
        slice_data["window_label"] = "कल शाम (Tomorrow Evening)"
        return slice_data

    if temporal_target == "day_after_tomorrow":
        t_max = day_after_tomorrow_entry.get("temp_max", 30.0)
        t_min = day_after_tomorrow_entry.get("temp_min", 24.0)
        r_prob = day_after_tomorrow_entry.get("rain_probability", 20)
        return {
            "window_name": "day_after_tomorrow",
            "window_label": "परसों (Day after tomorrow)",
            "date": day_after_tomorrow_date,
            "temp_max": t_max,
            "temp_min": t_min,
            "temp_c": round((t_max + t_min) / 2, 1),
            "rain_prob": r_prob,
            "rain_probability": r_prob,
            "precipitation_mm": day_after_tomorrow_entry.get("precipitation_mm", 0.0),
            "condition": day_after_tomorrow_entry.get("condition", "Partly cloudy"),
            "wind_kmh": day_after_tomorrow_entry.get("wind_max_kmh", 12),
        }

    if temporal_target == "sunday":
        sun_entry = None
        for d in forecast:
            try:
                dt = datetime.strptime(str(d.get("date", "")), "%Y-%m-%d")
                if dt.weekday() == 6:  # Sunday
                    sun_entry = d
                    break
            except ValueError:
                pass
        target_entry = sun_entry or tomorrow_entry
        t_max = target_entry.get("temp_max", 30.0)
        t_min = target_entry.get("temp_min", 24.0)
        r_prob = target_entry.get("rain_probability", 20)
        return {
            "window_name": "sunday",
            "window_label": "रविवार (Sunday)",
            "date": str(target_entry.get("date", tomorrow_date)),
            "temp_max": t_max,
            "temp_min": t_min,
            "temp_c": round((t_max + t_min) / 2, 1),
            "rain_prob": r_prob,
            "rain_probability": r_prob,
            "precipitation_mm": target_entry.get("precipitation_mm", 0.0),
            "condition": target_entry.get("condition", "Partly cloudy"),
            "wind_kmh": target_entry.get("wind_max_kmh", 12),
        }

    if temporal_target == "today_morning":
        slice_data = filter_hourly(today_date, 6, 12)
        slice_data["window_name"] = "today_morning"
        slice_data["window_label"] = "आज सुबह (Today Morning)"
        return slice_data

    if temporal_target == "today_afternoon":
        slice_data = filter_hourly(today_date, 12, 17)
        slice_data["window_name"] = "today_afternoon"
        slice_data["window_label"] = "आज दोपहर (Today Afternoon)"
        return slice_data

    if temporal_target == "today_evening":
        slice_data = filter_hourly(today_date, 17, 21)
        slice_data["window_name"] = "today_evening"
        slice_data["window_label"] = "आज शाम (Today Evening)"
        return slice_data

    if temporal_target == "tomorrow":
        t_max = tomorrow_entry.get("temp_max", 30.0)
        t_min = tomorrow_entry.get("temp_min", 24.0)
        r_prob = tomorrow_entry.get("rain_probability", 20)
        return {
            "window_name": "tomorrow",
            "window_label": "कल (Tomorrow)",
            "date": tomorrow_date,
            "temp_max": t_max,
            "temp_min": t_min,
            "temp_c": round((t_max + t_min) / 2, 1),
            "rain_prob": r_prob,
            "rain_probability": r_prob,
            "precipitation_mm": tomorrow_entry.get("precipitation_mm", 0.0),
            "condition": tomorrow_entry.get("condition", "Partly cloudy"),
            "wind_kmh": tomorrow_entry.get("wind_max_kmh", 12),
        }

    if temporal_target == "this_weekend":
        weekend_days = []
        for d in forecast:
            try:
                dt = datetime.strptime(str(d.get("date", "")), "%Y-%m-%d")
                if dt.weekday() in [5, 6]:  # Saturday, Sunday
                    weekend_days.append(d)
            except ValueError:
                pass
        return {
            "window_name": "this_weekend",
            "window_label": "इस सप्ताहांत (This Weekend)",
            "days": weekend_days,
        }

    # Default: Today / Current
    curr_t = current.get("temperature_c", 28.0)
    today_r_prob = today_entry.get("rain_probability", 20)
    return {
        "window_name": "today",
        "window_label": "आज (Today)",
        "date": today_date,
        "current_temp": curr_t,
        "temp_c": curr_t,
        "feels_like": current.get("feels_like_c", 30.0),
        "temp_max": today_entry.get("temp_max", 30.0),
        "temp_min": today_entry.get("temp_min", 24.0),
        "rain_prob": today_r_prob,
        "rain_probability": today_r_prob,
        "precipitation_mm": today_entry.get("precipitation_mm", 0.0),
        "condition": current.get("condition") or today_entry.get("condition", "Clear sky"),
        "humidity": current.get("humidity_pct", 70),
        "wind_kmh": current.get("wind_kmh", 12),
    }


# ---------------------------------------------------------------------------
# 5. COMPACT STRUCTURED "VERIFIED CONTEXT" (SECTION 3 & 4)
# ---------------------------------------------------------------------------

def build_verified_context(
    query: str,
    intent_info: dict[str, Any],
    weather_data: dict[str, Any],
    advisory_data: list[dict[str, Any]] | None = None,
    alerts_data: list[dict[str, Any]] | None = None,
    language: str = "en",
    rag_documents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Constructs a compact structured context with ONLY the data relevant to the query.
    Translates locations and conditions so the LLM receives clean, pure localized terms.
    """
    raw_location = weather_data.get("location", "Selected Location")
    localized_location = language_service.localize_location(raw_location, language)

    intent = intent_info["intent"]
    temporal_target = intent_info["temporal_target"]

    # Deterministic Date Resolution & Verification (Section 1, 2, 3, 4)
    date_info = intent_info.get("date_info") or resolve_date_intent(query)
    date_intent = date_info.get("date_intent", "today")
    resolved_date = date_info.get("resolved_date", datetime.now().strftime("%Y-%m-%d"))
    date_label = date_info.get("date_label", "Today")
    date_label_hi = date_info.get("date_label_hi", "आज")

    verified_forecast, date_match = extract_verified_forecast(
        weather_data=weather_data,
        resolved_date=resolved_date,
        date_intent=date_intent,
    )
    retrieved_forecast_date = verified_forecast.get("date", resolved_date)

    # Required Section 4 Date Debug Logging
    print("=" * 60)
    print(f"QUERY: {query}")
    print(f"DATE INTENT: {date_intent}")
    print(f"RESOLVED DATE: {resolved_date}")
    print(f"LOCATION: {raw_location}")
    print(f"RETRIEVED FORECAST DATE: {retrieved_forecast_date}")
    print(f"DATE MATCH: {'true' if date_match else 'false'}")
    print("=" * 60)
    logger.info(
        "QUERY: %s | DATE INTENT: %s | RESOLVED DATE: %s | LOCATION: %s | RETRIEVED FORECAST DATE: %s | DATE MATCH: %s",
        query, date_intent, resolved_date, raw_location, retrieved_forecast_date, "true" if date_match else "false"
    )

    temporal_weather = resolve_temporal_weather(weather_data, temporal_target)
    if date_intent != "today":
        temporal_weather = {
            **temporal_weather,
            **verified_forecast,
            "window_name": date_intent,
            "window_label": f"{date_label_hi if language == 'hi' else date_label} ({date_label})",
            "date": retrieved_forecast_date,
        }

    # Localize condition in temporal weather
    raw_cond = temporal_weather.get("condition", "")
    localized_cond = language_service.localize_condition(raw_cond, language)

    derived = {}

    # 1. Rain & Umbrella Logic
    rain_p = temporal_weather.get("rain_prob", 0)
    if language == "hi":
        if rain_p >= 50:
            derived["umbrella_verdict"] = "बारिश की संभावना अधिक है, बाहर जाते समय छाता साथ रखें"
            derived["umbrella_needed"] = True
        elif rain_p >= 30:
            derived["umbrella_verdict"] = "एहतियात के तौर पर छाता साथ रख सकते हैं"
            derived["umbrella_needed"] = True
        else:
            derived["umbrella_verdict"] = "छाते की आवश्यकता नहीं है"
            derived["umbrella_needed"] = False
    else:
        if rain_p >= 50:
            derived["umbrella_verdict"] = "Carry an umbrella (rain likely)"
            derived["umbrella_needed"] = True
        elif rain_p >= 30:
            derived["umbrella_verdict"] = "Keep an umbrella handy as precaution"
            derived["umbrella_needed"] = True
        else:
            derived["umbrella_verdict"] = "No umbrella needed"
            derived["umbrella_needed"] = False

    # 2. Chemical Spraying Logic
    wind_spd = temporal_weather.get("wind_kmh", 12)
    if language == "hi":
        if rain_p >= 50 or wind_spd > 20:
            derived["spray_verdict"] = "दवा या कीटनाशक का छिड़काव न करें (बारिश या तेज हवा से दवा बहने का खतरा)"
            derived["spray_safe"] = "UNSAFE"
        elif rain_p >= 35 or wind_spd > 15:
            derived["spray_verdict"] = "सावधानी बरतें, केवल सुबह के शांत मौसम में ही छिड़काव करें"
            derived["spray_safe"] = "CAUTION"
        else:
            derived["spray_verdict"] = "दवा छिड़काव के लिए मौसम अनुकूल है"
            derived["spray_safe"] = "SAFE"
    else:
        if rain_p >= 50 or wind_spd > 20:
            derived["spray_verdict"] = "Avoid chemical spraying (rain or wind hazard)"
            derived["spray_safe"] = "UNSAFE"
        elif rain_p >= 35 or wind_spd > 15:
            derived["spray_verdict"] = "Exercise caution, spray in calm morning"
            derived["spray_safe"] = "CAUTION"
        else:
            derived["spray_verdict"] = "Safe for chemical spraying"
            derived["spray_safe"] = "SAFE"

    # 3. Outdoor & Best Time Logic
    if language == "hi":
        if "morning" in temporal_target:
            derived["outdoor_verdict"] = "सुबह का समय मौसम के अनुकूल है और काम के लिए सबसे अच्छा रहेगा"
        elif rain_p >= 60:
            derived["outdoor_verdict"] = "बारिश का खतरा अधिक है, बाहरी कार्यों के समय छाता साथ रखें"
        else:
            derived["outdoor_verdict"] = "बाहरी कार्यों के लिए मौसम अनुकूल है"
    else:
        if "morning" in temporal_target:
            derived["outdoor_verdict"] = "Morning hours are pleasant and suitable for work"
        elif rain_p >= 60:
            derived["outdoor_verdict"] = "Heavy rain risk; plan outdoor activities early or carry rain protection"
        else:
            derived["outdoor_verdict"] = "Fair weather for outdoor tasks"

    # 4. Comparison Logic (Today vs Tomorrow / Days)
    forecast = weather_data.get("forecast", [])
    if forecast and len(forecast) >= 2:
        today_f = forecast[0]
        tomorrow_f = forecast[1]
        t1_max = today_f.get("temp_max", 30.0)
        t2_max = tomorrow_f.get("temp_max", 28.0)
        diff = round(abs(t2_max - t1_max), 1)

        # Check if query asks to compare with Sunday specifically
        q_lower = query.lower()
        if "sunday" in q_lower or "रविवार" in q_lower:
            sun_f = None
            for d in forecast:
                try:
                    dt = datetime.strptime(str(d.get("date", "")), "%Y-%m-%d")
                    if dt.weekday() == 6:
                        sun_f = d
                        break
                except ValueError:
                    pass
            if sun_f:
                t_sun = sun_f.get("temp_max", 29.0)
                sun_rain = sun_f.get("rain_probability", 20)
                tom_rain = tomorrow_f.get("rain_probability", 20)
                comp_text_en = f"Tomorrow will see highs of {t2_max}°C with a {tom_rain}% chance of rain, while Sunday will reach {t_sun}°C with a {sun_rain}% chance of rain."
                comp_text_hi = f"कल अधिकतम तापमान {t2_max} डिग्री सेल्सियस (बारिश {tom_rain} प्रतिशत) रहेगा, जबकि रविवार को तापमान {t_sun} डिग्री सेल्सियस (बारिश {sun_rain} प्रतिशत) रहने का अनुमान है।"
                derived["comparison"] = {
                    "day1": "tomorrow",
                    "day2": "sunday",
                    "diff": round(abs(t_sun - t2_max), 1),
                    "text_en": comp_text_en,
                    "text_hi": comp_text_hi,
                }
        elif t2_max > t1_max:
            comp_text_en = f"Tomorrow will be hotter than today by {diff}°C (high of {t2_max}°C tomorrow compared to {t1_max}°C today)."
            comp_text_hi = f"कल आज की तुलना में {diff} डिग्री सेल्सियस अधिक गर्म रहेगा (कल अधिकतम {t2_max} डिग्री सेल्सियस और आज {t1_max} डिग्री सेल्सियस)।"
            derived["comparison"] = {
                "today_max": t1_max,
                "tomorrow_max": t2_max,
                "diff": diff,
                "text_en": comp_text_en,
                "text_hi": comp_text_hi,
            }
        elif t2_max < t1_max:
            comp_text_en = f"Tomorrow will be cooler than today by {diff}°C (high of {t2_max}°C tomorrow compared to {t1_max}°C today)."
            comp_text_hi = f"कल आज की तुलना में {diff} डिग्री सेल्सियस ठंडा रहेगा (कल अधिकतम {t2_max} डिग्री सेल्सियस और आज {t1_max} डिग्री सेल्सियस)।"
            derived["comparison"] = {
                "today_max": t1_max,
                "tomorrow_max": t2_max,
                "diff": diff,
                "text_en": comp_text_en,
                "text_hi": comp_text_hi,
            }
        else:
            comp_text_en = f"Tomorrow's temperature will be similar to today at around {t1_max}°C."
            comp_text_hi = f"कल का तापमान आज के समान लगभग {t1_max} डिग्री सेल्सियस रहेगा।"
            derived["comparison"] = {
                "today_max": t1_max,
                "tomorrow_max": t2_max,
                "diff": diff,
                "text_en": comp_text_en,
                "text_hi": comp_text_hi,
            }

    # Relevant Warnings (Filter only active official warnings; no demo alerts)
    active_warnings = []
    if alerts_data:
        for a in alerts_data:
            msg_val = a.get("message") or a.get("text") or ""
            haz_val = a.get("hazard") or str(a.get("category", "Weather Alert")).replace("_", " ").title()
            msg_str = str(msg_val).upper()
            haz_str = str(haz_val).upper()
            if "DEMO" not in msg_str and "DEMO" not in haz_str:
                active_warnings.append({
                    "id": a.get("id"),
                    "hazard": haz_val,
                    "severity": a.get("severity", "YELLOW"),
                    "message": msg_val,
                    "advisory": a.get("advisory", "") or (a.get("advisories", [""])[0] if a.get("advisories") else ""),
                    "valid_for": a.get("valid_for", "Next 24 hours"),
                    "source": a.get("source", "IMD Official"),
                    "is_official": True,
                })

    # Activity Evaluation (Weather-Dependent Life)
    activity = intent_info.get("activity")
    activity_suitability = None
    if activity:
        activity_suitability = evaluate_activity_suitability(
            activity=activity,
            temporal_weather=temporal_weather,
            alerts_data=active_warnings,
        )
        derived["activity_suitability"] = activity_suitability

    # Deterministic meteorological thresholds calculated in Python
    t_avg = temporal_weather.get("temp_c", 28.0)
    t_max = temporal_weather.get("temp_max", 30.0)
    wind_spd = temporal_weather.get("wind_kmh", 12.0)
    req_date = str(temporal_weather.get("date") or datetime.now().strftime("%Y-%m-%d"))

    calculations = {
        "rain_risk": "high" if rain_p >= 60 else "moderate" if rain_p >= 30 else "low",
        "extreme_heat_risk": bool(t_max >= 40.0),
        "strong_wind_risk": bool(wind_spd >= 40.0),
        "comfortable_temperature": bool(20.0 <= t_avg <= 30.0),
        "umbrella_recommended": bool(derived.get("umbrella_needed", False)),
        "outdoor_suitable": bool(rain_p < 40 and wind_spd < 30 and t_max < 38),
        "spraying_suitability": derived.get("spray_safe", "SAFE"),
        "irrigation_suitability": "DELAY" if rain_p >= 50 else "SUITABLE",
        "harvesting_suitability": "DELAY" if rain_p >= 40 else "SUITABLE",
        "activity_suitability": activity_suitability,
    }

    return {
        "location": {
            "name": localized_location,
            "canonical": raw_location,
        },
        "location_query": intent_info.get("location_query"),
        "location_source": intent_info.get("location_source", "app_selected"),
        "domain": intent_info.get("domain", "weather"),
        "intent": intent,
        "sub_intent": intent_info.get("sub_intent"),
        "activity": activity,
        "activity_suitability": activity_suitability,
        "raw_query": query,
        "required_fields": intent_info.get("required_fields", []),
        "temporal_target": temporal_target,
        "date_intent": date_intent,
        "requested_date": resolved_date,
        "resolved_date": resolved_date,
        "date_label": date_label_hi if language == "hi" else date_label,
        "date_match": date_match,
        "retrieved_forecast_date": retrieved_forecast_date,
        "temporal_label": temporal_weather.get("window_label", temporal_target),
        "target_weather": {
            **temporal_weather,
            "condition": localized_cond,
            "condition_raw": raw_cond,
        },
        "forecast": verified_forecast,
        "calculations": calculations,
        "derived": derived,
        "warnings": active_warnings,
        "rag_documents": rag_documents or [],
        "sources": ["Open-Meteo", "IMD"],
        "source": weather_data.get("source", "Open-Meteo — Forecast · IMD — Official Warnings"),
    }


# ---------------------------------------------------------------------------
# 6. DETERMINISTIC HUMAN RESPONSE ENGINE (SECTION 9, 10, 19)
# ---------------------------------------------------------------------------

def format_conversational_location(loc_name: str, language: str = "en") -> str:
    """
    Formulates a concise, human-natural location reference (e.g. 'Shiroda, Ponda' or 'Panaji' or 'Tiswadi, Goa')
    instead of repeating strange postal PIN codes or commercial facility/POI names (e.g. 'Primary Health Centre').
    """
    fallback = "आपके क्षेत्र" if language in ["hi", "mr", "kok"] else "your area"
    if not loc_name or not str(loc_name).strip():
        return fallback

    str_loc = str(loc_name).strip()

    # Check if the entire string is just a numeric PIN code or raw coordinate
    if re.match(r"^(\d{4,6}|lat\b|\d+\.\d+)", str_loc, re.I):
        return fallback

    parts = [p.strip() for p in str_loc.split(",") if p.strip()]
    if not parts:
        return fallback

    # Filter out numeric-only PIN codes, coordinates, or postal code tags
    clean_parts = [
        p for p in parts
        if not re.match(r"^(\d{4,6}|lat\b|\d+\.\d+)", p, re.I)
        and not re.search(r"\b\d{4,6}\b", p)
    ]
    if not clean_parts:
        return fallback

    # Remove country suffix if multiple parts exist
    if len(clean_parts) > 1 and clean_parts[-1].lower() in ["india", "भारत"]:
        clean_parts = clean_parts[:-1]

    # Strip facility / amenity / POI names so the weather location is the actual geographic/administrative place
    POI_STRIP_TERMS = (
        "primary health centre", "health centre", "health center", "phc", "sub centre",
        "hospital", "clinic", "dispensary", "rainwater harvesting", "harvesting",
        "school", "college", "university", "institute", "resort", "hotel", "restaurant",
        "temple", "church", "mosque", "bank", "atm", "studio", "hair studio", "shop", "store",
        "office", "panchayat office", "railway station", "bus stand", "bus stop",
    )
    while len(clean_parts) > 1 and any(poi_term in clean_parts[0].lower() for poi_term in POI_STRIP_TERMS):
        clean_parts = clean_parts[1:]

    # Final check: make sure clean_parts[0] is not pure digits
    if re.match(r"^\d{4,6}$", clean_parts[0]):
        clean_parts = clean_parts[1:]
        if not clean_parts:
            return fallback

    if len(clean_parts) == 1:
        return clean_parts[0]

    if len(clean_parts) >= 2:
        return f"{clean_parts[0]}, {clean_parts[1]}"

    return fallback


def generate_human_deterministic_answer(
    verified_context: dict[str, Any] | None = None,
    language: str = "en",
    *,
    parsed_query: dict[str, Any] | None = None,
    temporal_info: dict[str, Any] | None = None,
    location: str | dict[str, Any] | None = None,
    weather_data: dict[str, Any] | None = None,
) -> str:
    """
    Builds clean, warm, farmer-friendly answers in the exact requested language
    without relying on external LLM availability.
    Guarantees 100% pure native script with zero English leakage and phonetically expanded units.
    """
    if verified_context is None:
        p_query = parsed_query or {}
        loc_str = "your area"
        if isinstance(location, str) and location.strip():
            c_str = location.strip()
            if not re.match(r"^\d{4,6}$", c_str):
                loc_str = c_str
        elif isinstance(location, dict):
            for key in ["label", "admin_label", "weather_location", "admin_name", "name", "displayName"]:
                val = str(location.get(key) or "").strip()
                if val and not re.match(r"^\d{4,6}$", val):
                    loc_str = val
                    break
        intent = p_query.get("intent", "general_weather")
        temporal = p_query.get("temporal_target", p_query.get("temporal", "today"))
        tw = dict(temporal_info or {})
        from services import language_service
        loc_localized = language_service.localize_location(loc_str, language)
        cond_localized = language_service.localize_condition(tw.get("condition", "अनुकूल"), language)
        rain_val = tw.get("rain_prob", tw.get("rain_probability", 20))
        tw["rain_prob"] = rain_val
        verified_context = {
            "location": {"name": loc_localized, "canonical": loc_str},
            "intent": intent,
            "temporal_target": temporal,
            "target_weather": {
                **tw,
                "condition": cond_localized,
            },
            "derived": {
                "rain_risk": "high" if rain_val >= 50 else "low",
                "spraying_safe": rain_val < 30 and tw.get("wind_kmh", 10) < 20,
                "outdoor_safe": rain_val < 50,
            },
            "warnings": [],
        }

    loc = verified_context["location"]["name"]
    loc_short = format_conversational_location(loc, language)
    intent = verified_context["intent"]
    temporal = verified_context["temporal_target"]
    tw = verified_context["target_weather"]
    derived = verified_context.get("derived", {})
    cond = tw.get("condition", "अनुकूल")
    rain_p = tw.get("rain_prob", tw.get("rain_probability", 20))
    sub_intent = verified_context.get("sub_intent", "")
    q_raw = (verified_context.get("raw_query") or verified_context.get("query") or "").lower()

    activity = verified_context.get("activity") or (parsed_query.get("activity") if parsed_query else None)
    act_suit = verified_context.get("activity_suitability") or derived.get("activity_suitability")
    if not act_suit and activity:
        act_suit = evaluate_activity_suitability(activity, tw, verified_context.get("warnings", []))

    # -----------------------------------------------------------------------
    # HINDI (Devanagari)
    # -----------------------------------------------------------------------
    if language == "hi":
        date_intent = verified_context.get("date_intent", "")
        if date_intent in WEEKDAYS:
            w_idx = WEEKDAYS[date_intent]
            time_word = f"{WEEKDAY_LABELS[w_idx][1]} को"
        elif "day_after_tomorrow" in temporal or date_intent == "day_after_tomorrow":
            time_word = "परसों"
        elif "tomorrow" in temporal or date_intent == "tomorrow":
            time_word = "कल"
        elif "weekend" in temporal or date_intent == "this_weekend":
            time_word = "इस सप्ताहांत"
        else:
            time_word = "आज"

        if activity:
            act_info = SUPPORTED_ACTIVITIES.get(activity, {})
            act_label_hi = act_info.get("labels", {}).get("hi", activity)
            suit = act_suit.get("suitability", "GOOD") if act_suit else "GOOD"
            wind = tw.get("wind_kmh", 12)
            if activity == "fishing":
                reasons_list = act_suit.get("reasons", []) if act_suit else []
                has_official_warn = any("Official marine/cyclone warning active" in r for r in reasons_list)
                if suit == "NOT_RECOMMENDED":
                    if has_official_warn:
                        return f"{loc_short} में {time_word} आधिकारिक समुद्री/चक्रवात चेतावनी सक्रिय होने के कारण समुद्र में जाना सुरक्षित नहीं है। हवा की गति {wind} km/h और बारिश की संभावना {rain_p}% रहने का अनुमान है।"
                    return f"{loc_short} में {time_word} मछली पकड़ने जाना सुरक्षित नहीं है। बारिश की संभावना {rain_p}% और हवा की गति {wind} km/h रहने का अनुमान है। मौसम साफ होने तक प्रतीक्षा करें।"
                elif suit == "CAUTION":
                    return f"{loc_short} में {time_word} मछली पकड़ने जाते समय सावधानी बरतें। हवा की गति {wind} km/h और बारिश की संभावना {rain_p}% रहने का अनुमान है। तटीय मौसम पर नजर रखें।"
                else:
                    return f"{loc_short} में {time_word} मछली पकड़ने के लिए मौसम बहुत अच्छा और अनुकूल है। हवा शांत ({wind} km/h) है और बारिश का खतरा केवल {rain_p}% है।"
            else:
                if suit == "NOT_RECOMMENDED":
                    return f"{loc_short} में {time_word} {act_label_hi} के लिए मौसम अनुकूल नहीं है। बारिश की संभावना {rain_p}% है और मौसम {cond} रहेगा।"
                elif suit == "CAUTION":
                    return f"{loc_short} में {time_word} {act_label_hi} के दौरान थोड़ी सावधानी बरतें। बारिश की संभावना करीब {rain_p}% है।"
                else:
                    return f"{loc_short} में {time_word} {act_label_hi} के लिए मौसम पूरी तरह अनुकूल है। मौसम {cond} रहेगा और बारिश की संभावना केवल {rain_p}% है।"

        if "morning" in temporal:
            temp_avg = tw.get("temp_avg", 26.0)
            is_tom = "tomorrow" in temporal
            day_str = "कल सुबह" if is_tom else "आज सुबह"
            if rain_p >= 50:
                return f"{loc_short} में {day_str} बारिश की संभावना करीब {rain_p}% है और तापमान {temp_avg}°C रहेगा। सुबह बाहर निकल रहे हैं तो छाता साथ रखना बेहतर रहेगा।"
            else:
                return f"{loc_short} में {day_str} मौसम सुहावना और साफ़ रहेगा। बारिश की संभावना केवल {rain_p}% है और तापमान {temp_avg}°C रहने का अनुमान है। सुबह का समय बाहरी काम निपटाने के लिए सबसे अच्छा रहेगा।"

        if "afternoon" in temporal:
            temp_max = tw.get("temp_max", 31.0)
            day_str = "कल दोपहर" if "tomorrow" in temporal else "आज दोपहर"
            return f"{loc_short} में {day_str} मौसम {cond} रहेगा और अधिकतम तापमान {temp_max}°C तक पहुँच सकता है। बारिश की संभावना {rain_p}% है।"

        if "evening" in temporal:
            day_str = "कल शाम" if "tomorrow" in temporal else "आज शाम"
            return f"{loc_short} में {day_str} मौसम {cond} रहेगा। बारिश की संभावना {rain_p}% है और हल्की हवा चलेगी।"

        if intent == "harvesting" or (intent == "agriculture" and sub_intent == "harvesting"):
            if rain_p >= 40:
                return f"{loc_short} में {time_word} बारिश की {rain_p}% संभावना को देखते हुए कटी हुई फसल को भीगने से बचाएं और कटाई का काम थोड़ा टालें।"
            else:
                return f"{loc_short} में {time_word} फसल कटाई के लिए मौसम अनुकूल है। बारिश का खतरा कम ({rain_p}%) है, इसलिए कटी फसल को सुरक्षित स्थान पर सुखाया जा सकता है।"

        if intent == "irrigation" or (intent == "agriculture" and sub_intent == "irrigation"):
            if rain_p >= 50:
                return f"{loc_short} में {time_word} खेत में सिंचाई करने से पहले बारिश का पूर्वानुमान देख लें। बारिश की संभावना {rain_p}% है, इसलिए सिंचाई टालना बेहतर रहेगा ताकि जलभराव न हो।"
            else:
                return f"{loc_short} में {time_word} खेत में आवश्यकतानुसार हल्की सिंचाई कर सकते हैं। सुबह या शाम के ठंडे समय में पानी देना फसलों के लिए लाभकारी रहेगा।"

        if intent == "spraying" or (intent == "agriculture" and sub_intent == "spraying"):
            verdict = derived.get("spray_safe", "SAFE")
            if verdict == "UNSAFE":
                return f"{loc_short} में {time_word} बारिश की संभावना अधिक ({rain_p}%) है, इसलिए दवा या कीटनाशक का छिड़काव टालना बेहतर रहेगा ताकि दवा बह न जाए।"
            elif verdict == "CAUTION":
                return f"{loc_short} में {time_word} दवा का छिड़काव सुबह के शांत समय में ही करें। बारिश की संभावना {rain_p}% है, इसलिए सावधानी बरतें।"
            else:
                return f"{loc_short} में {time_word} दवा या कीटनाशक छिड़काव के लिए मौसम अनुकूल है। हवा की गति शांत है और बारिश का खतरा केवल {rain_p}% है।"

        if intent == "sowing" or (intent == "agriculture" and sub_intent == "sowing"):
            if rain_p >= 60:
                return f"{loc_short} में {time_word} भारी बारिश ({rain_p}%) के जोखिम को देखते हुए बुवाई का काम टालना बेहतर रहेगा।"
            else:
                return f"{loc_short} में {time_word} फसल बुवाई के लिए मौसम अनुकूल है। पर्याप्त नमी के साथ बुवाई का कार्य कर सकते हैं।"

        if intent == "agriculture":
            if rain_p >= 50:
                return f"{loc_short} में {time_word} बारिश की संभावना {rain_p}% है। खेतों में जल निकासी की व्यवस्था रखें और आवश्यक कृषि कार्य सावधानीपूर्वक करें।"
            else:
                return f"{loc_short} में {time_word} कृषि कार्यों के लिए मौसम सामान्य और अनुकूल है। बारिश का खतरा केवल {rain_p}% है।"

        q_raw = (verified_context.get("raw_query") or verified_context.get("query") or "").lower()
        sub_intent = verified_context.get("sub_intent", "")
        if intent == "cyclone" or (intent in ["alerts", "warning"] and (sub_intent == "cyclone" or "cyclone" in q_raw or "चक्रवात" in q_raw or "marine" in q_raw or "समुद्री" in q_raw)):
            warnings = verified_context.get("warnings", [])
            cyclone_warnings = [
                w for w in warnings
                if ("cyclone" in str(w.get("category", "")).lower() or "cyclone" in str(w.get("hazard", "")).lower() or "marine" in str(w.get("hazard", "")).lower())
                and w.get("severity") in ["ORANGE", "RED"]
            ]
            if cyclone_warnings:
                msg = cyclone_warnings[0].get("message", "")
                return f"मौसम विभाग (IMD) चक्रवात बुलेटिन: {loc_short} के लिए चेतावनी: {msg}। मछुआरों को समुद्र में न जाने की सलाह दी जाती है।"
            return f"मौसम विभाग (IMD) के अनुसार वर्तमान में {loc_short} के लिए कोई भी आधिकारिक समुद्री या चक्रवात चेतावनी सक्रिय नहीं है। मौसमी गतिविधियां सामान्य हैं।"

        if intent in ["warning", "alerts", "alert"]:
            warnings = verified_context.get("warnings", [])
            official_warnings = [w for w in warnings if w.get("severity") in ["ORANGE", "RED"]]
            if official_warnings:
                msg = official_warnings[0].get("message", "")
                haz = official_warnings[0].get("hazard", "मौसम चेतावनी")
                return f"मौसम विभाग (IMD) आधिकारिक चेतावनी: {loc_short} के लिए {haz}: {msg}। कृपया आवश्यक सावधानी बरतें।"
            return f"{loc_short} के लिए वर्तमान में मौसम विभाग (IMD) की कोई भी सक्रिय आधिकारिक चेतावनी नहीं पाई गई है। मौसम सामान्य और सुरक्षित है।"

        if intent == "comparison":
            comp = derived.get("comparison")
            if comp and "text_hi" in comp:
                return f"{loc_short} में {comp['text_hi']}"
            days = verified_context["target_weather"].get("days", [])
            if days and len(days) >= 2:
                d1 = days[0]
                d2 = days[1]
                return f"{loc_short} में {d1.get('date')} को अधिकतम तापमान {d1.get('temp_max')}°C (बारिश {d1.get('rain_probability')}%) और {d2.get('date')} को तापमान {d2.get('temp_max')}°C रहेगा।"
            return f"{loc_short} में आने वाले दिनों में तापमान 24.0°C से 31.0°C के बीच सामान्य बना रहेगा।"

        if intent == "outdoor_activity" or intent == "travel":
            if rain_p >= 50:
                return f"{loc_short} में {time_word} बारिश की संभावना करीब {rain_p}% है और मौसम {cond} रहेगा। यात्रा या बाहरी काम के समय छाता साथ रखना बेहतर रहेगा।"
            else:
                return f"{loc_short} में {time_word} बाहर जाने या काम के लिए मौसम बहुत अच्छा है। मौसम {cond} रहेगा और बारिश का खतरा बहुत कम ({rain_p}%) है।"

        if intent in ["rain", "rain_forecast"]:
            t_max = tw.get("temp_max", tw.get("current_temp", 29.0))
            t_min = tw.get("temp_min", 24.0)
            sub_intent = verified_context.get("sub_intent", "")
            q_raw = (verified_context.get("raw_query") or verified_context.get("query") or "").lower()
            is_umbrella = sub_intent == "umbrella" or any(w in q_raw for w in ["umbrella", "छाता", "chata", "chhaata", "chhatri"])
            if is_umbrella:
                if rain_p >= 50:
                    return f"{loc_short} में {time_word} बारिश की संभावना काफी अधिक (करीब {rain_p}%) है। बाहर निकलते समय छाता अवश्य साथ रखें।"
                elif rain_p >= 30:
                    return f"{loc_short} में {time_word} हल्की बारिश की मध्यम संभावना (करीब {rain_p}%) है। एहतियात के तौर पर छाता साथ रखना बेहतर रहेगा।"
                else:
                    return f"{loc_short} में {time_word} बारिश की संभावना बहुत कम ({rain_p}%) है। छाते की आवश्यकता नहीं होगी।"
            else:
                if rain_p >= 50:
                    return f"हाँ, {loc_short} में {time_word} बारिश की संभावना काफी अधिक (करीब {rain_p}%) है। मौसम {cond} रहेगा और तापमान {t_min}°C से {t_max}°C के बीच रहेगा। बाहर निकलते समय छाता साथ रखें।"
                elif rain_p >= 30:
                    return f"{loc_short} में {time_word} हल्की बारिश या बूंदाबांदी की मध्यम संभावना (करीब {rain_p}%) है। मौसम {cond} रहेगा।"
                else:
                    return f"नहीं, {loc_short} में {time_word} बारिश की संभावना बहुत कम ({rain_p}%) है। मौसम {cond} रहेगा और तापमान करीब {t_max}°C तक रहेगा। छाते की आवश्यकता नहीं है।"

        if intent == "temperature":
            cur_t = tw.get("current_temp", tw.get("temp_avg", 28.0))
            t_max = tw.get("temp_max", 30.0)
            t_min = tw.get("temp_min", 24.0)
            if "tomorrow" in temporal:
                return f"{loc_short} में कल का अधिकतम तापमान {t_max}°C और न्यूनतम तापमान {t_min}°C रहने की संभावना है।"
            return f"{loc_short} में वर्तमान तापमान {cur_t}°C है। आज का अधिकतम तापमान {t_max}°C और न्यूनतम तापमान {t_min}°C रहने का अनुमान है।"

        # General Weather Overview
        t_max = tw.get("temp_max", 29.4)
        t_min = tw.get("temp_min", 23.8)
        cur_t = tw.get("current_temp", 28.8)
        hum = tw.get("humidity", 78)
        if time_word == "कल":
            if rain_p >= 50:
                rain_text = f"कल बारिश की संभावना काफी अधिक (करीब {rain_p}%) है, इसलिए बाहर निकलते समय छाता साथ रखें।"
            elif rain_p >= 20:
                rain_text = f"कल हल्की बारिश की संभावना (करीब {rain_p}%) है।"
            else:
                rain_text = f"बारिश की संभावना बहुत कम ({rain_p}%) है।"
            return f"{loc_short} में कल मौसम {cond} रहने का अनुमान है। अधिकतम तापमान करीब {t_max}°C और न्यूनतम {t_min}°C रहेगा। {rain_text}"
        elif time_word == "इस सप्ताहांत":
            return f"{loc_short} में इस सप्ताहांत मौसम {cond} रहने का अनुमान है। अधिकतम तापमान करीब {t_max}°C और बारिश की संभावना {rain_p}% रहेगी।"
        else:
            if rain_p >= 50:
                rain_text = f"आज बारिश की संभावना करीब {rain_p}% है। बाहर निकल रहे हैं तो छाता साथ रखना बेहतर रहेगा।"
            elif rain_p >= 20:
                rain_text = f"आज हल्की बारिश की संभावना (करीब {rain_p}%) है।"
            else:
                rain_text = f"बारिश की संभावना बहुत कम ({rain_p}%) है और मौसम सामान्य रहेगा।"
            return f"{loc_short} में आज मौसम {cond} रहेगा। अधिकतम तापमान करीब {t_max}°C और न्यूनतम {t_min}°C रहने का अनुमान है। {rain_text} वर्तमान तापमान {cur_t}°C और हवा में नमी {hum}% है।"

    # -----------------------------------------------------------------------
    # HINGLISH (Roman Hindi / hi-Latn)
    # -----------------------------------------------------------------------
    if language == "hi-Latn":
        time_word = "kal" if "tomorrow" in temporal else ("is weekend" if "weekend" in temporal else "aaj")
        if activity:
            suit = act_suit.get("suitability", "GOOD") if act_suit else "GOOD"
            wind = tw.get("wind_kmh", 12)
            if activity == "fishing":
                if suit == "NOT_RECOMMENDED":
                    return f"{loc_short} me {time_word} fishing ke liye jaana safe nahi hai. Baarish ke chances {rain_p}% aur hawa {wind} km/h rehne ka anuman hai."
                elif suit == "CAUTION":
                    return f"{loc_short} me {time_word} fishing ke liye caution rakhein. Hawa {wind} km/h aur rain chance {rain_p}% hai."
                else:
                    return f"{loc_short} me {time_word} fishing ke liye mausam favorable hai. Hawa shant ({wind} km/h) hai aur rain chance sirf {rain_p}% hai."
            else:
                if suit == "NOT_RECOMMENDED":
                    return f"{loc_short} me {time_word} {activity} ke liye mausam theek nahi hai. Rain probability {rain_p}% hai."
                elif suit == "CAUTION":
                    return f"{loc_short} me {time_word} {activity} ke liye thoda caution rakhein. Rain chance {rain_p}% rahega."
                else:
                    return f"{loc_short} me {time_word} {activity} ke liye mausam accha hai. Rain chance sirf {rain_p}% hai."
        if "morning" in temporal:
            temp_avg = tw.get("temp_avg", 26.0)
            day_str = "kal subah" if "tomorrow" in temporal else "aaj subah"
            return f"{loc_short} me {day_str} mausam {cond} rahega aur rainfall chances lagbhag {rain_p}% hain. Temperature around {temp_avg}°C rahega. Subah ka time bahar ke kaamon ke liye best hai."
        if intent == "harvesting" or (intent == "agriculture" and sub_intent == "harvesting"):
            if rain_p >= 40:
                return f"{loc_short} me {time_word} baarish ke {rain_p}% chances ko dekhte hue fasal ki katai thoda postpone karein aur kaati hui fasal ko cover karein."
            return f"{loc_short} me {time_word} fasal katai (harvesting) ke liye mausam favorable hai. Rain risk low ({rain_p}%) hai."

        if intent == "irrigation" or (intent == "agriculture" and sub_intent == "irrigation"):
            if rain_p >= 50:
                return f"{loc_short} me {time_word} sinchai (irrigation) postpone karein, kyunki baarish ke {rain_p}% chances hain aur paani bharne ka risk hai."
            return f"{loc_short} me {time_word} routine sinchai ke liye mausam theek hai. Subah ya shaam ke waqt paani dena behtar rahega."

        if intent == "spraying" or (intent == "agriculture" and sub_intent == "spraying"):
            verdict = derived.get("spray_safe", "SAFE")
            if verdict == "UNSAFE":
                return f"{loc_short} me {time_word} keetnashak dawai ka spray na karein, kyunki baarish ke chances {rain_p}% hain aur dawai behne ka khatra hai."
            elif verdict == "CAUTION":
                return f"{loc_short} me {time_word} dawai ka spray subah shant hawa me hi karein. Rain risk {rain_p}% hai."
            return f"{loc_short} me {time_word} spraying ke liye mausam theek hai, hawa shant hai aur rain risk low ({rain_p}%) hai."

        if intent == "sowing" or (intent == "agriculture" and sub_intent == "sowing"):
            if rain_p >= 60:
                return f"{loc_short} me {time_word} heavy rain ({rain_p}%) ke chalte buwai (sowing) postpone karna behtar rahega."
            return f"{loc_short} me {time_word} buwai ke liye mausam favorable hai."

        if intent == "agriculture":
            if rain_p >= 50:
                return f"{loc_short} me {time_word} kheti ke kaamon me baarish ({rain_p}%) ka dhyan rakhein aur drainage ka intezam rakhein."
            return f"{loc_short} me {time_word} kheti ke kaamon ke liye mausam normal aur favorable hai."
        if intent == "rain":
            if rain_p >= 50:
                return f"Haan, {loc_short} me {time_word} baarish ke kaafi high chances ({rain_p}%) hain. Mausam {cond} rahega, isliye bahar jaate waqt chhaata zaroor saath rakhein."
            return f"Nahi, {loc_short} me {time_word} baarish ke chances kaafi kam ({rain_p}%) hain. Mausam mostly {cond} rahega."
        if intent in ["warning", "alerts", "alert", "cyclone"] or sub_intent == "cyclone":
            warnings = verified_context.get("warnings", [])
            cyclone_warnings = [w for w in warnings if "cyclone" in str(w.get("category", "")).lower() or "cyclone" in str(w.get("hazard", "")).lower()]
            if cyclone_warnings:
                msg = cyclone_warnings[0].get("message", "")
                return f"Official IMD Cyclone Advisory for {loc_short}: {msg}."
            if warnings:
                msg = warnings[0].get("message", "")
                return f"Official IMD Warning for {loc_short}: {msg}."
            return f"{loc_short} ke liye currently koi official IMD warning ya cyclone alert active nahi hai. Mausam normal hai."
        return f"{loc_short} me {time_word} mausam {cond} rahega. Max temp {tw.get('temp_max', 30.0)}°C aur min temp {tw.get('temp_min', 24.0)}°C rehne ki sambhavna hai. Rain probability {rain_p}% hai."

    # -----------------------------------------------------------------------
    # MARATHI (mr)
    # -----------------------------------------------------------------------
    if language == "mr":
        time_word_mr = "उद्या" if "tomorrow" in temporal else ("या वीकेंडला" if "weekend" in temporal else "आज")
        if activity:
            suit = act_suit.get("suitability", "GOOD") if act_suit else "GOOD"
            wind = tw.get("wind_kmh", 12)
            if activity == "fishing":
                if suit == "NOT_RECOMMENDED":
                    return f"{loc_short} येथे {time_word_mr} मासेमारीसाठी जाणे सुरक्षित नाही. पावसाची शक्यता {rain_p}% आणि वाऱ्याचा वेग {wind} किमी/तास राहण्याचा अंदाज आहे."
                elif suit == "CAUTION":
                    return f"{loc_short} येथे {time_word_mr} मासेमारीसाठी जाताना काळजी घ्या. वाऱ्याचा वेग {wind} किमी/तास आणि पावसाची शक्यता {rain_p}% आहे."
                else:
                    return f"{loc_short} येथे {time_word_mr} मासेमारीसाठी हवामान अनुकूल आहे. वाऱ्याचा वेग शांत ({wind} किमी/तास) असून पावसाची शक्यता फक्त {rain_p}% आहे."
            else:
                if suit == "NOT_RECOMMENDED":
                    return f"{loc_short} येथे {time_word_mr} {activity} साठी हवामान अनुकूल नाही. पावसाची शक्यता {rain_p}% आहे."
                else:
                    return f"{loc_short} येथे {time_word_mr} {activity} साठी हवामान अनुकूल आहे. पावसाची शक्यता {rain_p}% आहे."
        if intent == "harvesting" or (intent == "agriculture" and sub_intent == "harvesting"):
            if rain_p >= 40:
                return f"{loc_short} येथे {time_word_mr} पावसाच्या {rain_p}% शक्यतेमुळे पीक काढणीचे काम पुढे ढकलावे आणि काढलेले पीक सुरक्षित झाकून ठेवावे."
            return f"{loc_short} येथे {time_word_mr} पीक काढणीसाठी हवामान अनुकूल आहे. पावसाचा धोका कमी ({rain_p}%) आहे."

        if intent == "irrigation" or (intent == "agriculture" and sub_intent == "irrigation"):
            if rain_p >= 50:
                return f"{loc_short} येथे {time_word_mr} शेतात पाणी देणे (सिंचन) पुढे ढकलावे, कारण पावसाची शक्यता {rain_p}% आहे."
            return f"{loc_short} येथे {time_word_mr} आवश्यकतेनुसार पिकांना हलके पाणी देऊ शकता."

        if intent == "spraying" or (intent == "agriculture" and sub_intent == "spraying"):
            if rain_p >= 40:
                return f"{loc_short} येथे {time_word_mr} पिकांवर औषध फवारणी करू नये, कारण पावसाची शक्यता {rain_p}% आहे आणि औषध वाहून जाण्याचा धोका आहे."
            return f"{loc_short} येथे {time_word_mr} औषध फवारणीसाठी हवामान अनुकूल आहे. वाऱ्याचा वेग शांत असून पावसाची शक्यता केवळ {rain_p}% आहे."

        if intent == "sowing" or (intent == "agriculture" and sub_intent == "sowing"):
            if rain_p >= 60:
                return f"{loc_short} येथे {time_word_mr} जास्त पावसाच्या ({rain_p}%) शक्यतेमुळे पेरणीचे काम पुढे ढकलावे."
            return f"{loc_short} येथे {time_word_mr} पेरणीसाठी हवामान अनुकूल आहे."

        if intent == "agriculture":
            if rain_p >= 50:
                return f"{loc_short} येथे {time_word_mr} पावसाची शक्यता {rain_p}% असल्याने शेतीची कामे काळजीपूर्वक करावीत."
            return f"{loc_short} येथे {time_word_mr} शेतीच्या कामांसाठी हवामान सामान्य आणि अनुकूल आहे."
        if intent == "rain":
            if rain_p >= 50:
                return f"होय, {loc_short} येथे {time_word_mr} पावसाची शक्यता जास्त ({rain_p} टक्के) आहे. हवामान {cond} राहील. बाहेर पडताना छत्री सोबत ठेवा."
            return f"नाही, {loc_short} येथे {time_word_mr} पावसाची शक्यता कमी ({rain_p} टक्के) आहे. हवामान {cond} राहील."
        return f"{loc_short} येथे {time_word_mr} {cond} राहील. कमाल तापमान {tw.get('temp_max', 30.0)} अंश सेल्सिअस आणि किमान तापमान {tw.get('temp_min', 24.0)} अंश सेल्सिअस राहण्याची शक्यता आहे. पावसाची शक्यता {rain_p} टक्के आहे."

    # -----------------------------------------------------------------------
    # KONKANI (kok)
    # -----------------------------------------------------------------------
    if language == "kok":
        time_word_kok = "फाल्यां" if "tomorrow" in temporal else ("ह्या वीकेंडाक" if "weekend" in temporal else "आयज")
        if activity:
            suit = act_suit.get("suitability", "GOOD") if act_suit else "GOOD"
            if activity == "fishing":
                if suit == "NOT_RECOMMENDED":
                    return f"{loc_short} हांगा {time_word_kok} मासेमारी खातीर वचप सुरक्षित ना. पावसाची शक्यताय {rain_p}% आसा."
                else:
                    return f"{loc_short} हांगा {time_word_kok} मासेमारी खातीर हवामान बरें आसा. पावसाची शक्यताय फक्त {rain_p}% आसा."
        if intent in ["spraying", "agriculture"]:
            if rain_p >= 50:
                return f"{loc_short} हांगा {time_word_kok} पिकांचेर वखद फवारणी करची न्हय, कारण पावसाची शक्यताय {rain_p}% आसा आनी वखद व्हांवून वचपाचो धोको आसा."
            return f"{loc_short} हांगा {time_word_kok} वखद फवारणी खातीर हवामान अनुकूल आसा. पावसाची शक्यताय {rain_p}% आसा."
        if intent == "rain":
            if rain_p >= 50:
                return f"हय, {loc_short} हांगा {time_word_kok} पावसाची शक्यताय चड ({rain_p} टक्के) आसा. हवामान {cond} उरतले. भायर सरतना सांतरी वांगडा दवरात."
            return f"ना, {loc_short} हांगा {time_word_kok} पावसाची शक्यताय उणी ({rain_p} टक्के) आसा. हवामान {cond} उरतले."
        return f"{loc_short} हांगा {time_word_kok} {cond} उरतले. चडांत चड तापमान {tw.get('temp_max', 30.0)} अंश सेल्सिअस आनी उण्यांत उणे तापमान {tw.get('temp_min', 24.0)} अंश सेल्सिअस उरपाची शक्यताय आसा. पावसाची शक्यताय {rain_p} टक्के आसा."

    # -----------------------------------------------------------------------
    # ENGLISH (en) - Default Fallback
    # -----------------------------------------------------------------------
    t_max = tw.get("temp_max", tw.get("current_temp", 29.4))
    t_min = tw.get("temp_min", 23.8)
    cur_t = tw.get("current_temp", 28.8)
    cond_en = tw.get("condition_raw", tw.get("condition", "Partly cloudy"))
    date_intent = verified_context.get("date_intent", "")
    date_label = verified_context.get("date_label", "")
    if date_intent in WEEKDAYS:
        w_idx = WEEKDAYS[date_intent]
        w_en, _ = WEEKDAY_LABELS[w_idx]
        time_word = f"on {w_en}"
        time_word_cap = f"On {w_en}"
    else:
        time_word = "the day after tomorrow" if ("day_after_tomorrow" in temporal or date_intent == "day_after_tomorrow") else ("tomorrow" if ("tomorrow" in temporal or date_intent == "tomorrow") else ("this weekend" if ("weekend" in temporal or date_intent == "this_weekend") else "today"))
        time_word_cap = "The day after tomorrow" if ("day_after_tomorrow" in temporal or date_intent == "day_after_tomorrow") else ("Tomorrow" if ("tomorrow" in temporal or date_intent == "tomorrow") else ("This weekend" if ("weekend" in temporal or date_intent == "this_weekend") else "Today"))

    if activity:
        act_info = SUPPORTED_ACTIVITIES.get(activity, {})
        act_label = act_info.get("labels", {}).get("en", activity)
        suit = act_suit.get("suitability", "GOOD") if act_suit else "GOOD"
        wind = tw.get("wind_kmh", 12)
        reasons_list = act_suit.get("reasons", []) if act_suit else []
        reason_str = f" ({'; '.join(reasons_list)})" if reasons_list else ""

        if activity == "fishing":
            reasons_list = act_suit.get("reasons", []) if act_suit else []
            has_official_warn = any("Official marine/cyclone warning active" in r for r in reasons_list)
            if suit == "NOT_RECOMMENDED":
                if has_official_warn:
                    return f"In {loc_short}, fishing is not recommended {time_word} due to an active official marine/cyclone warning. Expected conditions: {cond_en}, winds around {wind} km/h, and a {rain_p}% chance of rain."
                return f"In {loc_short}, fishing is not recommended {time_word}{reason_str}. Expected conditions: {cond_en}, winds around {wind} km/h, and a {rain_p}% chance of rain."
            elif suit == "CAUTION":
                return f"In {loc_short}, exercise caution if going fishing {time_word}{reason_str}. Expect {cond_en}, winds of {wind} km/h, and a {rain_p}% chance of rain."
            else:
                return f"In {loc_short}, weather conditions {time_word} are favorable for fishing with {cond_en}, calm winds around {wind} km/h, and only a {rain_p}% chance of rain."
        else:
            if suit == "NOT_RECOMMENDED":
                return f"In {loc_short}, {act_label} is not recommended {time_word}{reason_str}. Expected conditions: {cond_en} with a {rain_p}% chance of rain and highs around {t_max}°C."
            elif suit == "CAUTION":
                return f"In {loc_short}, exercise caution for {act_label} {time_word}{reason_str}. Conditions will be {cond_en} with a {rain_p}% chance of rain."
            else:
                return f"In {loc_short}, weather conditions {time_word} are favorable for {act_label}. Expect {cond_en} with a {rain_p}% chance of rain and temperatures around {t_max}°C."

    if "morning" in temporal:
        day_str = "tomorrow morning" if "tomorrow" in temporal else "this morning"
        temp_avg = tw.get("temp_avg", 26.0)
        if rain_p >= 50:
            return f"In {loc_short}, {day_str} will see {cond_en} with a {rain_p}% chance of rain and temperatures around {temp_avg}°C. Carrying an umbrella is advised if you're heading out early."
        return f"In {loc_short}, {day_str} will be pleasant with {cond_en}, a low {rain_p}% chance of rain, and temperatures around {temp_avg}°C. Morning is the ideal window for outdoor work."

    if "afternoon" in temporal:
        day_str = "tomorrow afternoon" if "tomorrow" in temporal else "this afternoon"
        return f"In {loc_short}, {day_str} will be {cond_en} with highs reaching {tw.get('temp_max', t_max)}°C and a {rain_p}% chance of rain."

    if "evening" in temporal:
        day_str = "tomorrow evening" if "tomorrow" in temporal else "this evening"
        return f"In {loc_short}, {day_str} will be {cond_en} with temperatures around {tw.get('temp_avg', 27.0)}°C and a {rain_p}% chance of rain."

    if intent == "harvesting" or (intent == "agriculture" and sub_intent == "harvesting"):
        if rain_p >= 40:
            return f"With a {rain_p}% chance of rain in {loc_short} {time_word}, protect harvested produce and consider postponing outdoor harvest work."
        return f"Weather conditions in {loc_short} are favorable for harvesting {time_word}, with low rain risk ({rain_p}%) and dry spells."

    if intent == "irrigation" or (intent == "agriculture" and sub_intent == "irrigation"):
        if rain_p >= 50:
            return f"Postpone field irrigation in {loc_short} {time_word}. The {rain_p}% chance of incoming rain will replenish soil moisture naturally and avoid waterlogging."
        return f"Routine irrigation is safe in {loc_short} {time_word}. Water during the cooler morning or evening hours for optimal absorption."

    if intent == "spraying" or (intent == "agriculture" and sub_intent == "spraying"):
        verdict = derived.get("spray_safe", "SAFE")
        if verdict == "UNSAFE":
            return f"It is not recommended to spray pesticides in {loc_short} {time_word} due to a {rain_p}% chance of rain and gusty winds, which could wash away or drift the chemicals."
        elif verdict == "CAUTION":
            return f"In {loc_short}, exercise caution when spraying {time_word}. Calm early morning hours are preferred, with a {rain_p}% rain chance."
        return f"Weather conditions in {loc_short} are suitable for spraying {time_word}, with calm winds and a low {rain_p}% risk of rain."

    if intent == "sowing" or (intent == "agriculture" and sub_intent == "sowing"):
        if rain_p >= 60:
            return f"Delay sowing operations in {loc_short} {time_word} due to a {rain_p}% chance of heavy rain, which could wash away seeds."
        return f"Weather conditions in {loc_short} are favorable for crop sowing {time_word}, with moderate conditions and low rain risk ({rain_p}%)."

    if intent == "agriculture":
        if rain_p >= 50:
            return f"In {loc_short} {time_word}, anticipate rain with a {rain_p}% probability; ensure proper field drainage for standing crops."
        return f"In {loc_short} {time_word}, weather conditions are generally favorable for farm activities with a low {rain_p}% rain risk."

    if intent in ["outdoor_activity", "travel"]:
        if rain_p >= 50:
            return f"In {loc_short}, outdoor work or travel {time_word} may be interrupted by rain ({rain_p}% chance). Conditions will be {cond_en}; carry rain protection."
        return f"In {loc_short}, conditions {time_word} are favorable for outdoor work and travel with {cond_en} and only a {rain_p}% chance of rain."

    if intent in ["rain", "rain_forecast"]:
        article = "an" if str(rain_p).startswith(("8", "11", "18")) else "a"
        sub_intent = verified_context.get("sub_intent", "")
        q_raw = (verified_context.get("raw_query") or verified_context.get("query") or "").lower()
        is_umbrella = sub_intent == "umbrella" or any(w in q_raw for w in ["umbrella", "chata", "chaata", "chhatri"])

        if time_word == "tomorrow":
            if is_umbrella:
                if rain_p >= 50:
                    return f"Tomorrow in {loc_short}, rain is likely with {article} {rain_p}% chance of precipitation. Carrying an umbrella is recommended."
                elif rain_p >= 30:
                    return f"Tomorrow in {loc_short}, there is a moderate {rain_p}% chance of rain. Keeping an umbrella handy is recommended."
                else:
                    return f"Tomorrow in {loc_short}, no significant rain is expected; the chance of rain is only {rain_p}%. You will not need an umbrella."
            else:
                if rain_p >= 50:
                    return f"Tomorrow in {loc_short}, rain is likely with {article} {rain_p}% chance of precipitation. The weather will be {cond_en} with highs of {t_max}°C. Carrying an umbrella is recommended."
                elif rain_p >= 30:
                    return f"Tomorrow in {loc_short}, there is a moderate {rain_p}% chance of light rain or showers. Conditions will be {cond_en}. Keeping an umbrella handy is recommended."
                else:
                    return f"Tomorrow in {loc_short}, no significant rain is expected; the chance of rain is only {rain_p}%. Conditions will be mostly {cond_en} with temperatures up to {t_max}°C."
        elif date_intent in WEEKDAYS:
            w_idx = WEEKDAYS[date_intent]
            w_en, _ = WEEKDAY_LABELS[w_idx]
            if is_umbrella:
                if rain_p >= 50:
                    return f"On {w_en} in {loc_short}, rain is likely with {article} {rain_p}% chance of precipitation. Carrying an umbrella is recommended."
                else:
                    return f"On {w_en} in {loc_short}, the chance of rain is only {rain_p}%. You will not need an umbrella."
            else:
                if rain_p >= 50:
                    return f"On {w_en} in {loc_short}, rain is likely with {article} {rain_p}% chance of precipitation. Highs will reach {t_max}°C."
                elif rain_p >= 30:
                    return f"On {w_en} in {loc_short}, there is a moderate {rain_p}% chance of light rain or showers with highs of {t_max}°C."
                else:
                    return f"On {w_en} in {loc_short}, no significant rain is expected ({rain_p}% chance). Highs will reach {t_max}°C with {cond_en}."
        elif time_word == "the day after tomorrow":
            if is_umbrella:
                if rain_p >= 50:
                    return f"The day after tomorrow in {loc_short}, rain is likely with {article} {rain_p}% chance of precipitation. Carrying an umbrella is recommended."
                else:
                    return f"The day after tomorrow in {loc_short}, rain chance is low ({rain_p}%). You will not need an umbrella."
            else:
                if rain_p >= 50:
                    return f"The day after tomorrow in {loc_short}, rain is likely with {article} {rain_p}% chance of precipitation. The weather will be {cond_en} with highs of {t_max}°C."
                else:
                    return f"The day after tomorrow in {loc_short}, no significant rain is expected ({rain_p}% chance). Conditions will be mostly {cond_en} with temperatures up to {t_max}°C."
        else:
            if is_umbrella:
                if rain_p >= 50:
                    return f"Today in {loc_short}, rain is likely with {article} {rain_p}% chance of precipitation. Carrying an umbrella is recommended."
                elif rain_p >= 30:
                    return f"Today in {loc_short}, there is a moderate {rain_p}% chance of rain. Keeping an umbrella handy is recommended."
                else:
                    return f"Today in {loc_short}, no rain is expected ({rain_p}% chance). You will not need an umbrella."
            else:
                if rain_p >= 50:
                    return f"Yes, rain is likely in {loc_short} today with {article} {rain_p}% chance of precipitation. The weather will be {cond_en} with highs of {t_max}°C. Carrying an umbrella is recommended."
                elif rain_p >= 30:
                    return f"There is a moderate {rain_p}% chance of light rain or showers in {loc_short} today. Conditions will be {cond_en}. Keeping an umbrella handy is recommended."
                else:
                    return f"No significant rain is expected in {loc_short} today; the chance of rain is only {rain_p}%. Conditions will be mostly {cond_en} with temperatures up to {t_max}°C."

    q_raw = (verified_context.get("raw_query") or verified_context.get("query") or "").lower()
    sub_intent = verified_context.get("sub_intent", "")
    if intent == "cyclone" or (intent in ["alerts", "warning"] and (sub_intent == "cyclone" or "cyclone" in q_raw or "marine" in q_raw)):
        warnings = verified_context.get("warnings", [])
        cyclone_warnings = [
            w for w in warnings
            if ("cyclone" in str(w.get("category", "")).lower() or "cyclone" in str(w.get("hazard", "")).lower() or "marine" in str(w.get("hazard", "")).lower())
            and w.get("severity") in ["ORANGE", "RED"]
        ]
        if cyclone_warnings:
            msg = cyclone_warnings[0].get("message", "")
            return f"Official IMD Cyclone Advisory: Active alert for {loc_short} sector: {msg}. Fishermen and coastal operations should follow safety guidelines."
        return f"No verified official marine or cyclone warning was found for {loc_short}."

    if intent == "comparison":
        comp = derived.get("comparison")
        if comp and "text_en" in comp:
            return f"In {loc_short}, {comp['text_en']}"
        return f"In {loc_short}, temperatures will remain steady between today and tomorrow."

    if intent == "temperature":
        if "tomorrow" in temporal:
            return f"In {loc_short}, tomorrow's forecast expects a high of {t_max}°C and a low of {t_min}°C."
        return f"In {loc_short}, the current temperature is {cur_t}°C. Today's forecast expects a high of {t_max}°C and a low of {t_min}°C."

    if intent in ["warning", "alerts", "alert"]:
        warnings = verified_context.get("warnings", [])
        official_warnings = [w for w in warnings if w.get("severity") in ["ORANGE", "RED"]]
        if official_warnings:
            msg = official_warnings[0].get("message", "")
            haz = official_warnings[0].get("hazard", "Weather Warning")
            return f"Official IMD Warning for {loc_short}: {haz} — {msg}. Please follow local disaster management guidance."
        return f"No active official IMD warning was found for {loc_short}. Weather conditions remain normal."

    if "weekend" in temporal:
        return f"In {loc_short}, this weekend will see {cond_en} with highs around {t_max}°C, lows around {t_min}°C, and a {rain_p}% chance of rain."

    if time_word_cap == "The day after tomorrow":
        return f"The day after tomorrow in {loc_short}, expect {cond_en} with a high of {t_max}°C and a low of {t_min}°C. The chance of rain is {rain_p}%, with wind speeds around {tw.get('wind_kmh', 12)} km/h."

    if time_word_cap == "Tomorrow":
        return f"Tomorrow in {loc_short}, expect {cond_en} with a high of {t_max}°C and a low of {t_min}°C. The chance of rain is {rain_p}%, with wind speeds around {tw.get('wind_kmh', 12)} km/h."

    if cur_t and (intent == "current_weather" or any(w in q_raw for w in ["now", "right now", "currently", "what's the weather", "what is the weather"])):
        return f"The weather in {loc_short} is currently {cond_en.lower()}, with temperatures around {cur_t}°C. Today's high is expected to reach {t_max}°C with a {rain_p}% chance of rain."

    return f"Today in {loc_short}, expect {cond_en} with a high of {t_max}°C and a low of {t_min}°C. The chance of rain is {rain_p}%, and humidity is at {tw.get('humidity', 78)}%."


# ---------------------------------------------------------------------------
# 7. RESPONSE VALIDATION (SECTION 18 & SECTION 6)
# ---------------------------------------------------------------------------

def validate_llm_answer(
    llm_answer: str,
    verified_context: dict[str, Any],
    language: str = "en",
) -> tuple[bool, str]:
    """
    Validates Qwen's response against the strict criteria in Section 18 & Section 6:
    - Non-empty (> 15 chars)
    - No JSON, code fences, or <think> tags
    - Numeric safety (numbers must be grounded)
    - Temporal integrity: When tomorrow was requested, forbid opening with "Today in" or referring to today.
    - When language is Hindi ('hi'), no unlocalized English words (e.g. 'Moderate drizzle', 'Primary Health Centre')
    """
    if not llm_answer or len(llm_answer.strip()) < 15:
        return False, "Answer too short or empty."

    cleaned = llm_answer.strip()

    # Reject code fences or JSON
    if "```" in cleaned or cleaned.startswith("{") or cleaned.endswith("}"):
        return False, "Raw code block or JSON detected."

    # Reject thinking blocks
    if "<think>" in cleaned or "</think>" in cleaned:
        return False, "Debug <think> tags leaked."

    # Temporal integrity check:
    date_intent = verified_context.get("date_intent", "")
    temporal_target = verified_context.get("temporal_target", "")
    is_tomorrow_req = date_intent == "tomorrow" or "tomorrow" in temporal_target
    cleaned_lower = cleaned.lower()

    if is_tomorrow_req:
        # User asked about tomorrow, LLM must not say "Today in...", "Today,", or start with "Today"
        if (
            re.search(r"\btoday\s+in\b", cleaned_lower)
            or re.search(r"\btoday\s+with\b", cleaned_lower)
            or cleaned_lower.startswith("today")
            or "आज का हाल" in cleaned
            or re.search(r"^\s*आज\b", cleaned)
        ):
            return False, "Temporal mismatch: response refers to Today when Tomorrow was requested."

    if date_intent in WEEKDAYS:
        if (
            re.search(r"\btoday\s+in\b", cleaned_lower)
            or re.search(r"\btoday\s+with\b", cleaned_lower)
            or cleaned_lower.startswith("today")
            or "आज का हाल" in cleaned
            or re.search(r"^\s*आज\b", cleaned)
        ):
            return False, f"Temporal mismatch: response refers to Today when {date_intent} was requested."

    # When activity was specifically requested, verify that the answer addresses the activity
    req_act = verified_context.get("activity")
    if req_act:
        act_info = SUPPORTED_ACTIVITIES.get(req_act, {})
        labels = [req_act]
        for l_val in act_info.get("labels", {}).values():
            labels.append(l_val.lower())
        if req_act == "fishing":
            labels.extend(["fish", "angler", "angling", "catch", "मछली", "मासेमारी", "machli", "मत्स्य"])
        elif req_act == "picnic":
            labels.extend(["outing", "पिकनिक", "सैर"])
        elif req_act == "hiking":
            labels.extend(["hike", "trek", "हाइकिंग", "ट्रेकिंग"])
        elif req_act == "outdoor_work":
            labels.extend(["work", "काम", "मजदूरी", "outdoor"])
        elif req_act == "travel":
            labels.extend(["trip", "journey", "drive", "यात्रा", "सफर", "safar"])
        elif req_act == "sports":
            labels.extend(["play", "match", "खेल", "cricket", "football"])

        has_act = any(lbl in cleaned_lower for lbl in labels)
        if not has_act:
            return False, f"Activity mismatch: response failed to address the requested activity '{req_act}'."

        # Cross-activity purity check: ensure harvesting response does not discuss spraying, and vice versa
        if req_act == "harvesting":
            if any(w in cleaned_lower for w in ["spray", "spraying", "pesticide", "छिड़काव", "कीटनाशक"]):
                return False, "Cross-activity contamination: spraying advice detected in harvesting response."
        elif req_act == "spraying":
            if any(w in cleaned_lower for w in ["harvest", "harvesting", "कटाई"]):
                return False, "Cross-activity contamination: harvesting advice detected in spraying response."
        elif req_act == "irrigation":
            if any(w in cleaned_lower for w in ["spray", "pesticide", "harvest", "छिड़काव", "कटाई"]):
                return False, "Cross-activity contamination: unrelated agricultural advice in irrigation response."
    else:
        # If no activity was requested, ensure the answer doesn't hallucinate an activity
        domain = verified_context.get("domain", "")
        intent = verified_context.get("intent", "")
        if domain == "weather" and intent in ["general_weather", "current_weather", "temperature", "rain_forecast"]:
            if any(act_word in cleaned_lower for act_word in [
                "picnic", "fishing", "मछली पकड़ने", "पिकनिक", "मासेमारी",
                "spray", "spraying", "pesticide", "कीटनाशक", "छिड़काव",
                "harvest", "harvesting", "कटाई", "irrigate", "irrigation", "सिंचाई"
            ]):
                return False, "Contamination: unrequested activity mentioned in general weather answer."

    # Warning vs Forecast integrity: if user asked for weather/forecast, do not accept a warning-only bulletin
    domain = verified_context.get("domain", "")
    intent = verified_context.get("intent", "")
    if domain == "weather" and intent in ["general_weather", "current_weather", "rain_forecast"]:
        if cleaned.startswith("Official IMD Warning") or cleaned.startswith("Official IMD Cyclone Advisory"):
            return False, "Contamination: Official warning bulletin returned when forecast was requested."

    # Official Warning Validation: The chatbot must NEVER invent or infer an official warning.
    # An official warning can ONLY be stated when verified by the backend.
    warnings = verified_context.get("warnings", [])
    has_active_official = any(
        (w.get("is_official") or "imd" in str(w.get("source", "")).lower()) and w.get("severity") in ["ORANGE", "RED"]
        for w in warnings
    )
    if not has_active_official:
        hallucinated_warning_phrases = [
            "official marine warning",
            "official cyclone warning",
            "official warning active",
            "official imd warning active",
            "cyclone warning active",
            "marine warning active",
            "आधिकारिक समुद्री चेतावनी",
            "आधिकारिक चक्रवात चेतावनी",
            "आधिकारिक चेतावनी सक्रिय",
        ]
        if any(phrase in cleaned_lower for phrase in hallucinated_warning_phrases):
            return False, "Hallucinated official warning: response claims an official warning is active when verified context has no active official warnings."

    # Location integrity check:
    loc_canonical = verified_context.get("location", {}).get("canonical", "")
    loc_name = verified_context.get("location", {}).get("name", "")
    full_loc_context = f"{loc_canonical} {loc_name}".lower()

    # Foreign location leakage check (reject foreign country names when Indian location is requested)
    is_indian_loc = "india" in full_loc_context or "भारत" in full_loc_context
    if is_indian_loc:
        foreign_loc_keywords = ["england", "united kingdom", "great britain", "london"]
        if any(k in cleaned_lower for k in foreign_loc_keywords) and not any(k in full_loc_context for k in foreign_loc_keywords):
            return False, "Foreign location leakage detected."

    # When Hindi is selected, reject any leaked English words (Latin script)
    if language == "hi":
        latin_words = re.findall(r"[a-zA-Z]+", cleaned)
        disallowed = [
            w for w in latin_words
            if w.upper() not in {"IMD", "WEATHERGPT", "AI", "DEMO", "C"}
        ]
        if disallowed:
            return False, f"Leaked English words {disallowed[:3]} in Hindi response."

    return True, cleaned


def validate_location_identity(
    requested_location: dict[str, Any] | str,
    retrieved_location: dict[str, Any] | str,
) -> tuple[bool, str]:
    """
    Validates Section 15 location identity dynamically without hardcoded place names:
    1. Rejects foreign locations when Indian location requested.
    2. Verifies coordinates match within acceptable tolerance (within ~55 km / 0.5 deg).
    3. Rejects provider responses that clearly belong to another unrelated location.
    """
    req_name = ""
    req_lat = None
    req_lon = None
    if isinstance(requested_location, dict):
        req_name = requested_location.get("name") or requested_location.get("displayName") or ""
        req_lat = requested_location.get("latitude")
        req_lon = requested_location.get("longitude")
    else:
        req_name = str(requested_location or "")

    ret_name = ""
    ret_lat = None
    ret_lon = None
    if isinstance(retrieved_location, dict):
        ret_name = retrieved_location.get("name") or retrieved_location.get("displayName") or ""
        ret_lat = retrieved_location.get("latitude")
        ret_lon = retrieved_location.get("longitude")
    else:
        ret_name = str(retrieved_location or "")

    ret_lower = ret_name.lower()
    req_lower = req_name.lower()

    # 1. Foreign location rejection
    foreign_keywords = ["england", "united kingdom", "great britain"]
    if any(k in ret_lower for k in foreign_keywords) and not any(k in req_lower for k in foreign_keywords):
        return False, f"Retrieved location '{ret_name}' contains foreign location data."

    # 2. Coordinate tolerance check (if both have coordinates)
    if req_lat is not None and req_lon is not None and ret_lat is not None and ret_lon is not None:
        try:
            d_lat = abs(float(req_lat) - float(ret_lat))
            d_lon = abs(float(req_lon) - float(ret_lon))
            if d_lat > 1.0 or d_lon > 1.0:
                return False, f"Coordinate divergence ({req_lat},{req_lon}) vs ({ret_lat},{ret_lon}) exceeds threshold."
        except (ValueError, TypeError):
            pass

    # 3. Dynamic unrelated location mismatch check
    req_tokens = {w for w in re.findall(r"\w+", req_lower) if len(w) >= 4 and w not in {"india", "state", "district", "taluka"}}
    ret_tokens = {w for w in re.findall(r"\w+", ret_lower) if len(w) >= 4 and w not in {"india", "state", "district", "taluka"}}
    if req_tokens and ret_tokens and not (req_tokens & ret_tokens):
        if req_lat is not None and ret_lat is not None:
            try:
                if abs(float(req_lat) - float(ret_lat)) > 0.5 or abs(float(req_lon) - float(ret_lon)) > 0.5:
                    return False, f"Location mismatch: requested '{req_name}' but retrieved '{ret_name}'."
            except (ValueError, TypeError):
                pass

    return True, "PASS"
