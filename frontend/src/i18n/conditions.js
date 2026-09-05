/**
 * Multilingual Weather Condition Translation Layer for WeatherGPT (SIH26068).
 * Supports English, Hindi, Marathi, Gujarati, Bengali, Tamil, Telugu, Kannada, Malayalam, Punjabi, and Odia.
 */

const CONDITIONS = {
  'clear sky': {
    en: 'Clear sky',
    hi: 'साफ आसमान',
    mr: 'निरभ्र आकाश',
    gu: 'સ્વચ્છ આકાશ',
    bn: 'পরিষ্কার আকাশ',
    ta: 'தெளிவான வானம்',
    te: 'నిర్మలమైన ఆకాశం',
    kn: 'ಸ್ವಚ್ಛ ಆಕಾಶ',
    ml: 'തെളിഞ്ഞ ആകാശം',
    pa: 'ਸਾਫ਼ ਅਸਮਾਨ',
    or: 'ନିର୍ମଳ ଆକାଶ',
      kok: 'निर्मळ मळब',
  },
  'sunny': {
    en: 'Sunny',
    hi: 'धूप खिली रहेगी',
    mr: 'सूर्यप्रकाश / ऊन',
    gu: 'તડકો',
    bn: 'রৌদ্রোজ্জ্বল',
    ta: 'வெயில்',
    te: 'ఎండగా ఉంది',
    kn: 'ಬಿಸಿಲು',
    ml: 'വെയിൽ',
    pa: 'ਧੁੱਪ',
    or: 'ଖରାଟିଆ',
      kok: 'उजवाड / ऊन',
  },
  'mainly clear': {
    en: 'Mainly clear',
    hi: 'मुख्यतः साफ आसमान',
    mr: 'बहुतांशी निरभ्र',
    gu: 'મોટેભાગે સ્વચ્છ',
    bn: 'বেশিরভাগ পরিষ্কার',
    ta: 'பெரும்பாலும் தெளிவான வானம்',
    te: 'ఎక్కువగా నిర్మలంగా ఉంది',
    kn: 'ಹೆಚ್ಚಾಗಿ ಸ್ವಚ್ಛ',
    ml: 'പ്രധാനമായും തെളിഞ്ഞത്',
    pa: 'ਮੁੱਖ ਤੌਰ ਤੇ ਸਾਫ਼',
    or: 'ମୁଖ୍ୟତଃ ନିର୍ମଳ',
      kok: 'बहुतांश निर्मळ',
  },
  'partly cloudy': {
    en: 'Partly cloudy',
    hi: 'आंशिक रूप से बादल',
    mr: 'अंशतः ढगाळ',
    gu: 'અંશતઃ વાદળછાયું',
    bn: 'আংশিক মেঘলা',
    ta: 'பகுதி மேகமூட்டம்',
    te: 'పాక్షికంగా మేఘావృతం',
    kn: 'ಭಾಗಶಃ ಮೋಡ ಕವಿದ',
    ml: 'ഭാഗികമായി മേഘാവൃതമായ',
    pa: 'ਅੰਸ਼ਕ ਤੌਰ ਤੇ ਬੱਦਲਵਾਈ',
    or: 'ଆଂଶିକ ମେଘୁଆ',
      kok: 'कांय प्रमाणांत कुपां',
  },
  'overcast': {
    en: 'Overcast',
    hi: 'घने बादल',
    mr: 'पूर्ण ढगाळ वातावरण',
    gu: 'સંપૂર્ણ વાદળછાયું',
    bn: 'মেঘাচ্ছন্ন',
    ta: 'முழு மேகமூட்டம்',
    te: 'పూర్తిగా మేఘావృతం',
    kn: 'ಸಂಪೂರ್ಣ ಮೋಡ ಕವಿದ',
    ml: 'പൂർണ്ണമായും മേഘാവൃതമായ',
    pa: 'ਘਣੇ ਬੱਦਲ',
    or: 'ଘନ ମେଘାଚ୍ଛନ୍ନ',
      kok: 'दट कुपां',
  },
  'fog': {
    en: 'Fog',
    hi: 'कोहरा',
    mr: 'धुके',
    gu: 'ધુમ્મસ',
    bn: 'কুয়াশা',
    ta: 'பனிமூட்டம்',
    te: 'పొగమంచు',
    kn: 'ದಟ್ಟ ಮಂಜು',
    ml: 'മൂടൽമഞ്ഞ്',
    pa: 'ਧੁੰਦ',
    or: 'କୁହୁଡ଼ି',
      kok: 'धुकें',
  },
  'mist': {
    en: 'Mist / Haze',
    hi: 'हल्का कोहरा या धुंध',
    mr: 'हलके धुके / धुरकट',
    gu: 'હળવું ધુમ્મસ',
    bn: 'হালকা কুয়াশা',
    ta: 'மெல்லிய பனி',
    te: 'తేలికపాటి పొగమంచు',
    kn: 'ತೆಳುವಾದ ಮಂಜು',
    ml: 'നേർത്ത മൂടൽമഞ്ഞ്',
    pa: 'ਹਲਕੀ ਧੁੰਦ',
    or: 'ହାଲୁକା କୁହୁଡ଼ି',
      kok: 'पातळ धुकें',
  },
  'light drizzle': {
    en: 'Light drizzle',
    hi: 'हल्की बूंदाबांदी',
    mr: 'हलकी रिमझिम',
    gu: 'હળવી ઝરમર',
    bn: 'হালকা গুঁড়ি গুঁড়ি বৃষ্টি',
    ta: 'லேசான தூறல்',
    te: 'తేలికపాటి చినుకులు',
    kn: 'ಹಗುರವಾದ ಹನಿ ಮಳೆ',
    ml: 'നേർത്ത ചാറ്റൽമഴ',
    pa: 'ਹਲਕੀ ਬੂੰਦਾ-ਬਾਂਦੀ',
    or: 'ହାଲୁକା ଝିପିଝିପି ବର୍ଷା',
      kok: 'हलक्यो शिंपण्यो',
  },
  'moderate drizzle': {
    en: 'Moderate drizzle',
    hi: 'मध्यम बूंदाबांदी',
    mr: 'मध्यम रिमझिम',
    gu: 'મધ્યમ ઝરમર',
    bn: 'মাঝারি গুঁড়ি গুঁড়ি বৃষ্টি',
    ta: 'மிதமான தூறல்',
    te: 'మధ్యస్థ చినుకులు',
    kn: 'ಮಧ್ಯಮ ಹನಿ ಮಳೆ',
    ml: 'മിതമായ ചാറ്റൽമഴ',
    pa: 'ਦਰਮਿਆਨੀ ਬੂੰਦਾ-ਬਾਂਦੀ',
    or: 'ମଧ୍ୟମ ଝିପିଝିପି ବର୍ଷା',
      kok: 'मध्यम शिंपण्यो',
  },
  'dense drizzle': {
    en: 'Dense drizzle',
    hi: 'तेज बूंदाबांदी',
    mr: 'दाट रिमझिम पाऊस',
    gu: 'તીવ્ર ઝરમર વરસાદ',
    bn: 'ঘন গুঁড়ি গুঁড়ি বৃষ্টি',
    ta: 'அடர்த்தியான தூறல்',
    te: 'తీవ్రమైన చినుకులు',
    kn: 'ದಟ್ಟ ಹನಿ ಮಳೆ',
    ml: 'കനത്ത ചാറ്റൽമഴ',
    pa: 'ਤੇਜ਼ ਬੂੰਦਾ-ਬਾਂਦੀ',
    or: 'ଘନ ଝିପିଝିପି ବର୍ଷା',
      kok: 'दाट शिंपण्यो',
  },
  'slight rain': {
    en: 'Slight rain',
    hi: 'हल्की बारिश',
    mr: 'हलका पाऊस',
    gu: 'હળવો વરસાદ',
    bn: 'হালকা বৃষ্টি',
    ta: 'லேசான மழை',
    te: 'తేలికపాటి వర్షం',
    kn: 'ಹಗುರವಾದ ಮಳೆ',
    ml: 'നേരിയ മഴ',
    pa: 'ਹਲਕੀ ਬਾਰਿਸ਼',
    or: 'ହାଲୁକା ବର୍ଷା',
      kok: 'हलको पावस',
  },
  'light rain': {
    en: 'Light rain',
    hi: 'हल्की बारिश',
    mr: 'हलका पाऊस',
    gu: 'હળવો વરસાદ',
    bn: 'হালকা বৃষ্টি',
    ta: 'லேசான மழை',
    te: 'తేలికపాటి వర్షం',
    kn: 'ಹಗುರವಾದ ಮಳೆ',
    ml: 'നേരിയ മഴ',
    pa: 'ਹਲਕੀ ਬਾਰਿਸ਼',
    or: 'ହାଲୁକା ବର୍ଷା',
      kok: 'हलको पावस',
  },
  'moderate rain': {
    en: 'Moderate rain',
    hi: 'मध्यम बारिश',
    mr: 'मध्यम पाऊस',
    gu: 'મધ્યમ વરસાદ',
    bn: 'মাঝারি বৃষ্টি',
    ta: 'மிதமான மழை',
    te: 'మధ్యస్థ వర్షం',
    kn: 'ಮಧ್ಯಮ ಪ್ರಮಾಣದ ಮಳೆ',
    ml: 'മിതമായ മഴ',
    pa: 'ਦਰਮਿਆਨੀ ਬਾਰਿਸ਼',
    or: 'ମଧ୍ୟମ ଧରଣର ବର୍ଷା',
      kok: 'मध्यम पावस',
  },
  'heavy rain': {
    en: 'Heavy rain',
    hi: 'तेज बारिश',
    mr: 'मुसळधार पाऊस',
    gu: 'ભારે વરસાદ',
    bn: 'ভারী বৃষ্টিপাত',
    ta: 'கனமழை',
    te: 'భారీ వర్షం',
    kn: 'ಭಾರಿ ಮಳೆ',
    ml: 'കനത്ത മഴ',
    pa: 'ਭਾਰੀ ਬਾਰਿਸ਼',
    or: 'ପ୍ରବଳ ବର୍ଷା',
      kok: 'व्हड पावस',
  },
  'rain showers': {
    en: 'Rain showers',
    hi: 'रुक-रुक कर बारिश',
    mr: 'पावसाच्या सरी',
    gu: 'વરસાદી ઝાપટાં',
    bn: 'বৃষ্টির দমকা',
    ta: 'மழைச்சாரல்',
    te: 'వర్షపు జల్లులు',
    kn: 'ಮಳೆಯ ತುಂತುರು',
    ml: 'മഴത്തുള്ളികൾ',
    pa: 'ਮੀਂਹ ਦੇ ਛਿੱਟੇ',
    or: 'ବର୍ଷା ଝଲକ',
      kok: 'पावसाचे शिंतोडे',
  },
  'thunderstorm': {
    en: 'Thunderstorm',
    hi: 'गरज के साथ बारिश',
    mr: 'वादळी पाऊस / मेघगर्जना',
    gu: 'ગાજવીજ સાથે વરસાદ',
    bn: 'বজ্রবিদ্যুৎ সহ ঝড়-বৃষ্টি',
    ta: 'இடியுடன் கூடிய மழை',
    te: 'ఉరుములతో కూడిన వర్షం',
    kn: 'ಗುಡುಗು ಸಹಿತ ಮಳೆ',
    ml: 'ഇടിമിന്നലോടു കൂടിയ മഴ',
    pa: 'ਗਰਜ ਨਾਲ ਮੀਂਹ',
    or: 'ଘଡ଼ଘଡ଼ି ସହ ବର୍ଷା',
      kok: 'गडगडाटी पावस',
  },
  'moderate thunderstorm': {
    en: 'Moderate thunderstorm',
    hi: 'गरज-चमक के साथ बारिश',
    mr: 'विजांच्या कडकडाटासह पाऊस',
    gu: 'ગાજવીજ સાથે મધ્યમ વરસાદ',
    bn: 'মাঝারি বজ্রঝড়',
    ta: 'மிதமான இடியுடன் கூடிய மழை',
    te: 'ఉరుములు, మెరుపులతో వర్షం',
    kn: 'ಗುಡುಗು ಸಿಡಿಲು ಸಹಿತ ಮಳೆ',
    ml: 'മിതമായ ഇടിമിന്നൽ മഴ',
    pa: 'ਗਰਜ-ਚਮਕ ਨਾਲ ਮੀਂਹ',
    or: 'ବିଜୁଳି ଘଡ଼ଘଡ଼ି ସହ ବର୍ଷା',
      kok: 'विजां सयत मध्यम पावस',
  },
  'thunderstorm with hail': {
    en: 'Thunderstorm with hail',
    hi: 'ओलावृष्टि और तेज आंधी',
    mr: 'गारांचा पाऊस आणि वादळ',
    gu: 'કરા સાથે ભારે તોફાન',
    bn: 'শিলাবৃষ্টি সহ মারাত্মক ঝড়',
    ta: 'ஆலங்கட்டி மழை மற்றும் இடி',
    te: 'వడగండ్ల వాన మరియు తుఫాను',
    kn: 'ಆಲಿಕಲ್ಲು ಸಹಿತ ಭಾರಿ ಗುಡುಗು ಮಳೆ',
    ml: 'ആലിപ്പഴത്തോട് കൂടിയ ഇടിമിന്നൽ',
    pa: 'ਗੜਿਆਂ ਵਾਲਾ ਤੂਫ਼ਾਨ',
    or: 'କୁଆପଥର ସହ ପ୍ରବଳ ଝଡ଼ବର୍ଷା',
      kok: 'गारो आनी गडगडाटी पावस',
  },
}

/**
 * Format and translate condition string based on the active language code.
 */
export function formatCondition(condition = '', language = 'en') {
  if (!condition) return ''
  const langKey = (language || 'en').split('-')[0].toLowerCase()
  if (langKey === 'en') return condition

  const clean = condition.trim().toLowerCase()

  const getVal = (condObj) => {
    if (!condObj) return null
    if (condObj[langKey]) return condObj[langKey]
    if (langKey === 'kok') return condObj['kok'] || condObj['mr'] || condObj['hi']
    return null
  }

  // Exact match
  const exact = getVal(CONDITIONS[clean])
  if (exact) return exact

  // Substring/Keyword matches
  if (clean.includes('thunder') || clean.includes('storm')) {
    return getVal(CONDITIONS['thunderstorm']) || condition
  }
  if (clean.includes('heavy rain') || clean.includes('violent')) {
    return getVal(CONDITIONS['heavy rain']) || condition
  }
  if (clean.includes('shower') || clean.includes('slight rain')) {
    return getVal(CONDITIONS['rain showers']) || condition
  }
  if (clean.includes('drizzle')) {
    return getVal(CONDITIONS['light drizzle']) || condition
  }
  if (clean.includes('rain')) {
    return getVal(CONDITIONS['moderate rain']) || condition
  }
  if (clean.includes('overcast')) {
    return getVal(CONDITIONS['overcast']) || condition
  }
  if (clean.includes('cloud')) {
    return getVal(CONDITIONS['partly cloudy']) || condition
  }
  if (clean.includes('fog') || clean.includes('haze') || clean.includes('mist')) {
    return getVal(CONDITIONS['fog']) || condition
  }
  if (clean.includes('clear') || clean.includes('sun')) {
    return getVal(CONDITIONS['clear sky']) || condition
  }

  return condition
}

export const translateCondition = formatCondition
export default formatCondition

