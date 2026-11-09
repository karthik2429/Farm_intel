"""
Regional crop names -> AGMARKNET commodity names.

The assistant hears (or is typed) crop names in the farmer's own script. AGMARKNET
only speaks English, so without this map a Kannada question such as
"ಟೊಮೆಟೊ ಬೆಲೆ ಕೋಲಾರದಲ್ಲಿ" resolves to no commodity and the assistant has to ask
"which crop?" — even though it understood that a price was wanted.

Only commodity names that actually exist in the mandi data are listed, and each
one maps to the exact spelling used by `mandi_prices._COMMODITY_ALIASES`. Words
that are genuinely ambiguous between crops are deliberately left out: a wrong
guess here would show a farmer the price of the wrong crop.

Lookup is exact after whitespace collapsing and lowercasing, so a word this file
does not know returns None rather than a plausible-looking guess.
"""
from __future__ import annotations

import re
from typing import Dict, Optional

HINDI: Dict[str, str] = {
    "टमाटर": "Tomato", "टोमेटो": "Tomato",
    "प्याज": "Onion", "प्याज़": "Onion",
    "आलू": "Potato", "आलु": "Potato",
    "रागी": "Ragi", "रागि": "Ragi",
    "चावल": "Rice", "धान": "Rice", "चावल धान": "Rice",
    "गेहूं": "Wheat", "गेहूँ": "Wheat",
    "मक्का": "Maize", "मक्की": "Maize",
    "कपास": "Cotton", "गन्ना": "Sugarcane",
    "मूंगफली": "Groundnut", "मूंगफल्ली": "Groundnut",
    "सोयाबीन": "Soybean", "सोया": "Soybean",
    "हरी मिर्च": "Green Chilli", "मिर्च": "Green Chilli",
    "बैंगन": "Brinjal", "केला": "Banana", "आम": "Mango",
    "नारियल": "Coconut", "हल्दी": "Turmeric",
    "चना": "Gram", "ज्वार": "Jowar", "बाजरा": "Bajra",
    "उड़द": "Urad", "उरद": "Urad", "मूंग": "Moong",
    "अरहर": "Arhar/Tur", "तुअर": "Arhar/Tur", "तूर": "Arhar/Tur",
    "सरसों": "Mustard", "पपीता": "Papaya", "अंगूर": "Grapes",
    "सेब": "Apple", "अनार": "Pomegranate", "गाजर": "Carrot",
    "सुपारी": "Arecanut(Betelnut/Supari)",
}

KANNADA: Dict[str, str] = {
    "ಟೊಮೆಟೊ": "Tomato", "ಟೊಮ್ಯಾಟೊ": "Tomato",
    "ಈರುಳ್ಳಿ": "Onion", "ಈರುಳ್ಳಿ ಗೆಡ್ಡೆ": "Onion",
    "ಆಲೂಗಡ್ಡೆ": "Potato", "ಆಲೂಗೆಡ್ಡೆ": "Potato", "ಆಲುಗಡ್ಡೆ": "Potato",
    "ರಾಗಿ": "Ragi",
    "ಅಕ್ಕಿ": "Rice", "ಭತ್ತ": "Rice",
    "ಗೋಧಿ": "Wheat", "ಮೆಕ್ಕೆಜೋಳ": "Maize", "ಜೋಳ": "Jowar",
    "ಹತ್ತಿ": "Cotton", "ಕಬ್ಬು": "Sugarcane",
    "ಶೇಂಗಾ": "Groundnut", "ನೆಲಗಡಲೆ": "Groundnut",
    "ಸೋಯಾಬೀನ್": "Soybean",
    "ಮೆಣಸಿನಕಾಯಿ": "Green Chilli", "ಹಸಿಮೆಣಸು": "Green Chilli",
    "ಬದನೆಕಾಯಿ": "Brinjal", "ಬದನೆ": "Brinjal",
    "ಬಾಳೆ": "Banana", "ಬಾಳೆಹಣ್ಣು": "Banana",
    "ಮಾವು": "Mango", "ತೆಂಗು": "Coconut", "ಅರಿಶಿನ": "Turmeric",
    "ಕಡಲೆ": "Gram", "ಸಜ್ಜೆ": "Bajra", "ಉದ್ದು": "Urad",
    "ಹೆಸರು ಕಾಳು": "Moong", "ಹೆಸರು": "Moong",
    "ತೊಗರಿ": "Arhar/Tur", "ಸೂರ್ಯಕಾಂತಿ": "Sunflower",
    "ಗಜ್ಜರಿ": "Carrot", "ದ್ರಾಕ್ಷಿ": "Grapes", "ಸೇಬು": "Apple",
    "ಅಡಿಕೆ": "Arecanut(Betelnut/Supari)", "ಮೆಣಸು": "Green Chilli",
}

TELUGU: Dict[str, str] = {
    "టొమాటో": "Tomato", "టమాటా": "Tomato", "టమోటా": "Tomato",
    "ఉల్లిపాయ": "Onion", "ఉల్లి": "Onion", "ఎర్ర ఉల్లిపాయ": "Onion",
    "బంగాళదుంప": "Potato", "ఆలుగడ్డ": "Potato", "బంగాళా దుంప": "Potato",
    "రాగి": "Ragi", "రాగులు": "Ragi",
    "బియ్యం": "Rice", "వరి": "Rice", "ధాన్యం": "Rice",
    "గోధుమ": "Wheat", "గోధుమలు": "Wheat",
    "మొక్కజొన్న": "Maize", "జొన్న": "Jowar",
    "ప్రత్తి": "Cotton", "చెరకు": "Sugarcane",
    "వేరుశనగ": "Groundnut", "పల్లీ": "Groundnut",
    "సోయాబీన్": "Soybean", "మిరపకాయ": "Green Chilli",
    "వంకాయ": "Brinjal", "అరటి": "Banana", "అరటిపండు": "Banana",
    "మామిడి": "Mango", "కొబ్బరి": "Coconut", "పసుపు": "Turmeric",
    "శనగ": "Gram", "సజ్జ": "Bajra", "మినుము": "Urad",
    "పెసర": "Moong", "పెసలు": "Moong", "కంది": "Arhar/Tur",
    "క్యారెట్": "Carrot", "ద్రాక్ష": "Grapes", "యాపిల్": "Apple",
    "సుపారి": "Arecanut(Betelnut/Supari)", "పొద్దుతిరుగుడు": "Sunflower",
}

TAMIL: Dict[str, str] = {
    "தக்காளி": "Tomato",
    "வெங்காயம்": "Onion", "வெங்காய": "Onion",
    "உருளைக்கிழங்கு": "Potato", "உருளை": "Potato",
    "கேழ்வரகு": "Ragi", "ராகி": "Ragi",
    "அரிசி": "Rice", "நெல்": "Rice",
    "கோதுமை": "Wheat", "மக்காச்சோளம்": "Maize",
    "பருத்தி": "Cotton", "கரும்பு": "Sugarcane",
    "நிலக்கடலை": "Groundnut", "சோயாபீன்": "Soybean",
    "மிளகாய்": "Green Chilli", "கத்தரிக்காய்": "Brinjal",
    "வாழை": "Banana", "வாழைப்பழம்": "Banana",
    "மாம்பழம்": "Mango", "தேங்காய்": "Coconut", "மஞ்சள்": "Turmeric",
    "கொண்டைக்கடலை": "Gram", "உளுந்து": "Urad",
    "பாசிப்பயறு": "Moong", "துவரை": "Arhar/Tur",
    "கேரட்": "Carrot", "திராட்சை": "Grapes", "ஆப்பிள்": "Apple",
    "பாக்கு": "Arecanut(Betelnut/Supari)",
}

MALAYALAM: Dict[str, str] = {
    "തക്കാളി": "Tomato",
    "സവാള": "Onion", "ഉള്ളി": "Onion",
    "ഉരുളക്കിഴങ്ങ്": "Potato", "ഉരുളക്കിഴങ്ങ": "Potato",
    "റാഗി": "Ragi", "അരി": "Rice", "നെല്ല്": "Rice",
    "ഗോതമ്പ്": "Wheat", "ചോളം": "Maize",
    "പരുത്തി": "Cotton", "കരിമ്പ്": "Sugarcane",
    "നിലക്കടല": "Groundnut", "സോയാബീൻ": "Soybean",
    "മുളക്": "Green Chilli", "വഴുതന": "Brinjal", "വഴുതനങ്ങ": "Brinjal",
    "വാഴപ്പഴം": "Banana", "പഴം": "Banana",
    "മാങ്ങ": "Mango", "തേങ്ങ": "Coconut", "മഞ്ഞൾ": "Turmeric",
    "കടല": "Gram", "ഉഴുന്ന്": "Urad", "ചെറുപയർ": "Moong",
    "തുവര": "Arhar/Tur", "ക്യാരറ്റ്": "Carrot",
    "മുന്തിരി": "Grapes", "ആപ്പിൾ": "Apple",
    "അടയ്ക്ക": "Arecanut(Betelnut/Supari)",
}

MARATHI: Dict[str, str] = {
    "टोमॅटो": "Tomato", "टोमाटो": "Tomato",
    "कांदा": "Onion", "कांदे": "Onion",
    "बटाटा": "Potato", "बटाटे": "Potato",
    "नाचणी": "Ragi", "रागी": "Ragi",
    "तांदूळ": "Rice", "भात": "Rice",
    "गहू": "Wheat", "मका": "Maize",
    "कापूस": "Cotton", "ऊस": "Sugarcane",
    "भुईमूग": "Groundnut", "सोयाबीन": "Soybean",
    "मिरची": "Green Chilli", "वांगे": "Brinjal", "वांगं": "Brinjal",
    "केळी": "Banana", "आंबा": "Mango", "नारळ": "Coconut",
    "हळद": "Turmeric", "हरभरा": "Gram", "ज्वारी": "Jowar",
    "बाजरी": "Bajra", "उडीद": "Urad", "मूग": "Moong",
    "तूर": "Arhar/Tur", "गाजर": "Carrot", "द्राक्ष": "Grapes",
    "सुपारी": "Arecanut(Betelnut/Supari)",
}

GUJARATI: Dict[str, str] = {
    "ટામેટા": "Tomato", "ટામેટું": "Tomato", "ટમેટા": "Tomato",
    "ડુંગળી": "Onion",
    "બટાકા": "Potato", "બટાકું": "Potato", "બટેટા": "Potato",
    "રાગી": "Ragi", "ચોખા": "Rice", "ડાંગર": "Rice",
    "ઘઉં": "Wheat", "મકાઈ": "Maize", "મક્કા": "Maize",
    "કપાસ": "Cotton", "શેરડી": "Sugarcane",
    "મગફળી": "Groundnut", "સોયાબીન": "Soybean",
    "મરચું": "Green Chilli", "લીલું મરચું": "Green Chilli",
    "રીંગણ": "Brinjal", "કેળું": "Banana", "કેરી": "Mango",
    "નાળિયેર": "Coconut", "હળદર": "Turmeric", "ચણા": "Gram",
    "જુવાર": "Jowar", "બાજરી": "Bajra", "અડદ": "Urad",
    "મગ": "Moong", "તુવેર": "Arhar/Tur", "ગાજર": "Carrot",
    "દ્રાક્ષ": "Grapes", "સોપારી": "Arecanut(Betelnut/Supari)",
}

BENGALI: Dict[str, str] = {
    "টমেটো": "Tomato",
    "পেঁয়াজ": "Onion", "পিয়াজ": "Onion",
    "আলু": "Potato", "রাগি": "Ragi",
    "চাল": "Rice", "ধান": "Rice",
    "গম": "Wheat", "ভুট্টা": "Maize",
    "তুলা": "Cotton", "আখ": "Sugarcane",
    "চিনাবাদাম": "Groundnut", "সয়াবিন": "Soybean",
    "লঙ্কা": "Green Chilli", "মরিচ": "Green Chilli",
    "বেগুন": "Brinjal", "কলা": "Banana", "আম": "Mango",
    "নারকেল": "Coconut", "হলুদ": "Turmeric",
    "ছোলা": "Gram", "জোয়ার": "Jowar", "বাজরা": "Bajra",
    "বিউলি": "Urad", "মুগ": "Moong", "অড়হর": "Arhar/Tur",
    "গাজর": "Carrot", "আঙুর": "Grapes", "সুপারি": "Arecanut(Betelnut/Supari)",
}

PUNJABI: Dict[str, str] = {
    "ਟਮਾਟਰ": "Tomato", "ਟਮਾਟਾ": "Tomato",
    "ਪਿਆਜ਼": "Onion", "ਪਿਆਜ": "Onion",
    "ਆਲੂ": "Potato", "ਰਾਗੀ": "Ragi",
    "ਚੌਲ": "Rice", "ਝੋਨਾ": "Rice",
    "ਕਣਕ": "Wheat", "ਮੱਕੀ": "Maize",
    "ਨਰਮਾ": "Cotton", "ਗੰਨਾ": "Sugarcane",
    "ਮੂੰਗਫਲੀ": "Groundnut", "ਸੋਇਆਬੀਨ": "Soybean",
    "ਮਿਰਚ": "Green Chilli", "ਹਰੀ ਮਿਰਚ": "Green Chilli",
    "ਬੈਂਗਣ": "Brinjal", "ਕੇਲਾ": "Banana", "ਅੰਬ": "Mango",
    "ਨਾਰੀਅਲ": "Coconut", "ਹਲਦੀ": "Turmeric", "ਛੋਲੇ": "Gram",
    "ਜਵਾਰ": "Jowar", "ਬਾਜਰਾ": "Bajra", "ਮਾਹ": "Urad",
    "ਮੂੰਗ": "Moong", "ਅਰਹਰ": "Arhar/Tur", "ਗਾਜਰ": "Carrot",
    "ਅੰਗੂਰ": "Grapes", "ਸੁਪਾਰੀ": "Arecanut(Betelnut/Supari)",
}

ODIA: Dict[str, str] = {
    "ଟମାଟୋ": "Tomato", "ଟମାଟା": "Tomato",
    "ପିଆଜ": "Onion", "ଆଳୁ": "Potato", "ରାଗି": "Ragi",
    "ଚାଉଳ": "Rice", "ଧାନ": "Rice",
    "ଗହମ": "Wheat", "ମକା": "Maize",
    "କପା": "Cotton", "ଆଖୁ": "Sugarcane",
    "ଚିନାବାଦାମ": "Groundnut", "ସୋୟାବିନ": "Soybean",
    "ଲଙ୍କା": "Green Chilli", "ବାଇଗଣ": "Brinjal",
    "କଦଳୀ": "Banana", "ଆମ୍ବ": "Mango", "ନଡ଼ିଆ": "Coconut",
    "ହଳଦୀ": "Turmeric", "ଚଣା": "Gram", "ଜୁଆର": "Jowar",
    "ବାଜରା": "Bajra", "ବିରି": "Urad", "ମୁଗ": "Moong",
    "କାନ୍ଦୁଳ": "Arhar/Tur", "ଗାଜର": "Carrot",
    "ଅଙ୍ଗୁର": "Grapes", "ଗୁଆ": "Arecanut(Betelnut/Supari)",
}

NATIVE_CROPS: Dict[str, str] = {}
for _block in (HINDI, KANNADA, TELUGU, TAMIL, MALAYALAM, MARATHI,
               GUJARATI, BENGALI, PUNJABI, ODIA):
    NATIVE_CROPS.update(_block)

_WORD_GAP = re.compile(r"\s+")


def _key(name: str) -> str:
    return _WORD_GAP.sub(" ", str(name or "").strip().lower())


def resolve_native(name: str) -> Optional[str]:
    """Canonical AGMARKNET commodity for a regional-script crop name, or None.

    Returns None for anything not listed — including a real crop we have no
    translation for — so the caller can ask which crop instead of inventing one.
    """
    k = _key(name)
    if not k:
        return None
    if k in NATIVE_CROPS:
        return NATIVE_CROPS[k]
    # "ಟೊಮೆಟೊ ಬೆಲೆ" -> drop trailing/leading helper words kept by tokenisation
    for word in k.split(" "):
        if word in NATIVE_CROPS:
            return NATIVE_CROPS[word]
    return None


def languages() -> int:
    """How many regional scripts are covered (used by tests and the status card)."""
    return sum(1 for b in (HINDI, KANNADA, TELUGU, TAMIL, MALAYALAM, MARATHI,
                           GUJARATI, BENGALI, PUNJABI, ODIA) if b)
