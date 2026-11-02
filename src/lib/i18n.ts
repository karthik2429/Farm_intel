/**
 * Translations — 11 Indian languages, one catalog each.
 *
 * Design:
 *   - `en` is the complete catalog and the fallback for every other language.
 *   - Each other language ships genuine translations for the chrome a farmer
 *     actually reads (navigation, greetings, buttons, market/predict labels,
 *     chat). A missing key falls back to English, never to a raw key name.
 *   - Run `npm run i18n:report` to list keys still untranslated per language.
 *
 * Urdu was removed: it is not one of the 22 scheduled languages requested for
 * this product, and the missing half-translation was worse than none.
 */

export type Language =
  | 'en'
  | 'hi'
  | 'kn'
  | 'te'
  | 'ta'
  | 'ml'
  | 'mr'
  | 'gu'
  | 'bn'
  | 'pa'
  | 'or';

export const LANGUAGES: Language[] = [
  'en', 'hi', 'kn', 'te', 'ta', 'ml', 'mr', 'gu', 'bn', 'pa', 'or',
];

/** Endonym — each language shown in its own script. */
export const languageNames: Record<Language, string> = {
  en: 'English',
  hi: 'हिन्दी',
  kn: 'ಕನ್ನಡ',
  te: 'తెలుగు',
  ta: 'தமிழ்',
  ml: 'മലയാളം',
  mr: 'मराठी',
  gu: 'ગુજરાતી',
  bn: 'বাংলা',
  pa: 'ਪੰਜਾਬੀ',
  or: 'ଓଡ଼ିଆ',
};

/** English name, for screen readers and the language sheet. */
export const languageEnglishNames: Record<Language, string> = {
  en: 'English',
  hi: 'Hindi',
  kn: 'Kannada',
  te: 'Telugu',
  ta: 'Tamil',
  ml: 'Malayalam',
  mr: 'Marathi',
  gu: 'Gujarati',
  bn: 'Bengali',
  pa: 'Punjabi',
  or: 'Odia',
};

/** BCP-47 tags for the Web Speech API and `:lang()` font selection. */
export const speechLocale: Record<Language, string> = {
  en: 'en-IN',
  hi: 'hi-IN',
  kn: 'kn-IN',
  te: 'te-IN',
  ta: 'ta-IN',
  ml: 'ml-IN',
  mr: 'mr-IN',
  gu: 'gu-IN',
  bn: 'bn-IN',
  pa: 'pa-IN',
  or: 'or-IN',
};

export const htmlLang: Record<Language, string> = {
  ...speechLocale,
};

/** Right-to-left: none of the 11 scheduled languages are RTL. */
export function isRtl(_lang: Language): boolean {
  return false;
}

export type Catalog = Record<string, string>;

/* ---------------------------------------------------------------- English -- */

const en: Catalog = {
  appName: 'AgroSmart AI',

  // common
  welcome: 'Welcome, Farmer',
  welcomeBack: 'Welcome back',
  signIn: 'Sign in',
  logIn: 'Log in',
  createAccount: 'Create account',
  createNewAccount: 'Create account',
  sendOtp: 'Send code',
  verifyOtp: 'Verify code',
  resendIn: 'Resend in',
  resend: 'Resend code',
  changeEmail: 'Use a different email',
  orContinueWith: 'or continue with',
  googleAccount: 'Continue with Google',
  appleId: 'Apple ID',
  termsText: 'By continuing you agree to our Terms of Service and Privacy Policy',
  completeSetup: 'Complete setup',
  next: 'Next',
  back: 'Back',
  skip: 'Skip',
  save: 'Save',
  saving: 'Saving…',
  cancel: 'Cancel',
  search: 'Search',
  viewAll: 'View all',
  viewDetails: 'View details',
  getRecommendations: 'Get recommendations',
  downloadGuide: 'Download guide',
  startSaving: 'Start saving',
  logout: 'Log out',
  language: 'Language',
  theme: 'Theme',
  light: 'Light',
  dark: 'Dark',
  auto: 'Auto',
  loading: 'Loading…',
  tryAgain: 'Try again',
  noData: 'No data yet',
  live: 'Live',
  cached: 'Cached',
  unavailable: 'Unavailable',
  today: 'Today',
  updated: 'Updated',
  perQuintal: 'per quintal',
  somethingWrong: 'Something went wrong',
  notConfigured: 'Not configured yet',

  // nav
  'nav.main': 'Main',
  'nav.tools': 'Farm tools',
  'nav.chat': 'Chat',
  home: 'Home',
  marketNav: 'Market',
  profile: 'Profile',
  crops: 'Crops',
  chat: 'Chat',
  rotationShort: 'Rotation',

  // onboarding
  onboardingSubtitle: 'A few details and your farm plan is ready',
  phoneNumber: 'Mobile number (optional)',
  empoweringFarmers: 'Smarter farming, better prices',
  email: 'Email',
  enterEmail: 'you@example.com',
  enterEmailOtp: 'Enter the 6-digit code',
  enterPhoneOtp: 'Enter the code sent to your phone',
  changeDetails: 'Change details',
  createAndSendOtp: 'Send code',
  yourName: 'Your name',
  enterYourName: 'Enter your name',
  namaste: 'Namaste',
  letsSetup: 'Let us set up your farm',
  preferredLanguage: 'Preferred language',
  location: 'Location',
  state: 'State',
  district: 'District',
  village: 'Village',
  whatDoYouGrow: 'What do you grow?',
  cerealsGrains: 'Cereals & grains',
  fruitsVegetables: 'Fruits & vegetables',
  cashCrops: 'Cash crops',
  specificCrops: 'Specific crops',
  agreeAlerts: 'Send me price alerts',
  soilCard: 'Soil Health Card',
  doNotHaveSoilCard: 'I do not have one',
  usingSavedSoilCard: 'Using your saved soil card',
  usingDistrictEstimate: 'Using district soil estimate',

  // home
  weather: 'Weather',
  partlyCloudy: 'Partly cloudy',
  aiSmartActions: 'Quick actions',
  cropRecs: 'Crop recommendations',
  aiBasedSelection: 'Matched to your soil, season and district',
  market: 'Market',
  livePrediction: 'Live prediction',
  rotation: 'Crop rotation',
  soilHealthLoss: 'Soil health',
  predict: 'Predict',
  priceForcast: 'Price forecast',
  topRecommendations: 'Top recommendations',
  askAgroSmartAi: 'Ask in your language',
  askInLanguage: 'Ask about prices, crops or schemes…',
  myCrops: 'My crops',
  bestTimeToSell: 'Best time to sell',
  mandiMovers: 'Today’s mandi movers',

  // crop recommendations
  cropAdvisor: 'Crop advisor',
  currentLocation: 'Current location',
  selectSeason: 'Season',
  kharif: 'Kharif',
  rabi: 'Rabi',
  zaid: 'Zaid',
  soilComposition: 'Soil composition',
  nitrogen: 'Nitrogen (N)',
  phosphorus: 'Phosphorus (P)',
  potassium: 'Potassium (K)',
  phLevel: 'pH',
  rainfall: 'Rainfall',

  // crop detail
  cultivationRequirements: 'Cultivation requirements',
  soilType: 'Soil type',
  temperature: 'Temperature',
  irrigation: 'Irrigation',
  marketPriceTrend: 'Market price trend',
  currentMandiAvg: 'Current mandi average',
  topCropRecommendations: 'Top crop recommendations',
  matchScore: 'Suitability',
  yieldLabel: 'Expected yield',
  durationLabel: 'Duration',
  waterNeeds: 'Water need',
  selectThisCrop: 'Plan this crop',
  profitPerAcre: 'Profit per acre',
  season: 'Season',

  // market
  mandiPrices: 'Mandi prices',
  realTimeRates: 'Real AGMARKNET rates',
  trendingInDistrict: 'Trending in your district',

  // prediction
  pricePrediction: 'Price prediction',
  marketPriceForecast: 'Market price forecast',
  confidence: 'Confidence',
  bestTimeToSellHint: 'Best day to sell in the next 14 days',
  nextBestAction: 'What to do now',
  getMoreAlert: 'Set a price alert',
  factorsInfluencing: 'Factors influencing this price',
  dataCoverage: 'Data coverage',
  coverageExplain: 'How many real mandi days exist for this commodity',

  // rotation
  rotationPlanner: 'Rotation planner',
  whyThisCrop: 'Why this crop',
  fixesNitrogen: 'Fixes nitrogen',
  marketDemand: 'Market demand',
  pestBreak: 'Breaks pest cycle',

  // chat
  aiAssistant: 'Kisan assistant',
  howCanIHelp: 'How can I help?',
  typeMessage: 'Type a message…',
  listening: 'Listening…',
  speakReply: 'Read aloud',
  stopSpeaking: 'Stop',
  notALabDiagnosis: 'AI suggestion — not a lab diagnosis',
  attachPhoto: 'Attach a leaf photo',
  quickReplies: 'Try asking',

  // profile
  farmerProfile: 'Profile',
  cropHistory: 'Crop history',
  accountSettings: 'Account',
  changeLanguage: 'Language',
  priceAlerts: 'Price alerts',
  harvestSchedule: 'Harvest schedule',
  darkMode: 'Dark mode',
  privacySecurity: 'Privacy & security',
  deleteAccount: 'Delete my account and data',
  farmDetails: 'Farm details',
  completeness: 'Profile completeness',

  // location
  chooseLocation: 'Choose location',
  useCurrentLocation: 'Use current location',
  selectDistrict: 'Select district',
  autoDetect: 'Auto-detect',
  detecting: 'Detecting…',
  locationDenied: 'Location permission denied — pick your district below',

  // marketplace (removed from the product, kept for old deep links)
  marketplace: 'Marketplace',
  sellYourProduce: 'Sell your produce',
  addListing: 'Add listing',
  productName: 'Product name',
  quantity: 'Quantity',
  pricePerUnit: 'Price per unit',
  description: 'Description',
  availableListings: 'Available listings',
  contactSeller: 'Contact seller',
  myListings: 'My listings',
  allListings: 'All listings',
  category: 'Category',
  postListing: 'Post listing',
  perKg: 'per kg',
};

/* -------------------------------------------------------------- partials -- */

const hi: Catalog = {
  home: 'होम', marketNav: 'मंडी', predict: 'अनुमान', crops: 'फसलें',
  chat: 'बातचीत', profile: 'प्रोफ़ाइल', 'nav.main': 'मुख्य', 'nav.tools': 'खेती के औज़ार',
  namaste: 'नमस्ते', welcomeBack: 'वापसी पर स्वागत है',
  askInLanguage: 'कीमत, फसल या योजना के बारे में पूछें…',
  askAgroSmartAi: 'अपनी भाषा में पूछें',
  mandiPrices: 'मंडी भाव', pricePrediction: 'भाव अनुमान', bestTimeToSell: 'बेचने का सही समय',
  myCrops: 'मेरी फसलें', topRecommendations: 'सबसे अच्छी सिफ़ारिशें',
  next: 'आगे', back: 'पीछे', save: 'सहेजें', cancel: 'रद्द करें', search: 'खोजें',
  skip: 'छोड़ें', language: 'भाषा', theme: 'थीम', logout: 'लॉग आउट',
  live: 'लाइव', cached: 'सहेजा गया', unavailable: 'उपलब्ध नहीं', today: 'आज',
  loading: 'लोड हो रहा है…', tryAgain: 'फिर कोशिश करें', noData: 'अभी कोई डेटा नहीं',
  dataCoverage: 'डेटा उपलब्धता', perQuintal: 'प्रति क्विंटल',
  quickReplies: 'यह पूछकर देखें', listening: 'सुन रहा हूँ…',
  somethingWrong: 'कुछ गड़बड़ हो गई', notConfigured: 'अभी सेट नहीं है',
};

const kn: Catalog = {
  home: 'ಮುಖಪುಟ', marketNav: 'ಮಾರುಕಟ್ಟೆ', predict: 'ಮುನ್ಸೂಚನೆ', crops: 'ಬೆಳೆಗಳು',
  chat: 'ಸಂಭಾಷಣೆ', profile: 'ಪ್ರೊಫೈಲ್', 'nav.main': 'ಮುಖ್ಯ', 'nav.tools': 'ಕೃಷಿ ಉಪಕರಣ',
  namaste: 'ನಮಸ್ಕಾರ', welcomeBack: 'ಮತ್ತೆ ಸ್ವಾಗತ',
  askInLanguage: 'ಬೆಲೆ, ಬೆಳೆ ಅಥವಾ ಯೋಜನೆ ಬಗ್ಗೆ ಕೇಳಿ…',
  askAgroSmartAi: 'ನಿಮ್ಮ ಭಾಷೆಯಲ್ಲಿ ಕೇಳಿ',
  mandiPrices: 'ಮಂಡಿ ದರಗಳು', pricePrediction: 'ಬೆಲೆ ಮುನ್ಸೂಚನೆ', bestTimeToSell: 'ಮಾರಾಟಕ್ಕೆ ಉತ್ತಮ ಸಮಯ',
  myCrops: 'ನನ್ನ ಬೆಳೆಗಳು', topRecommendations: 'ಉತ್ತಮ ಶಿಫಾರಸುಗಳು',
  next: 'ಮುಂದೆ', back: 'ಹಿಂದೆ', save: 'ಉಳಿಸಿ', cancel: 'ರದ್ದು', search: 'ಹುಡುಕಿ',
  skip: 'ಬಿಟ್ಟುಬಿಡಿ', language: 'ಭಾಷೆ', theme: 'ಥೀಮ್', logout: 'ಲಾಗ್ ಔಟ್',
  live: 'ಲೈವ್', cached: 'ಸಂಗ್ರಹಿಸಲಾಗಿದೆ', unavailable: 'ಲಭ್ಯವಿಲ್ಲ', today: 'ಇಂದು',
  loading: 'ಲೋಡ್ ಆಗುತ್ತಿದೆ…', tryAgain: 'ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ', noData: 'ಇನ್ನೂ ಡೇಟಾ ಇಲ್ಲ',
  dataCoverage: 'ಡೇಟಾ ಲಭ್ಯತೆ', perQuintal: 'ಪ್ರತಿ ಕ್ವಿಂಟಾಲ್',
  quickReplies: 'ಇದನ್ನು ಕೇಳಿ', listening: 'ಕೇಳುತ್ತಿದ್ದೇನೆ…',
  somethingWrong: 'ಏನೋ ತಪ್ಪಾಗಿದೆ', notConfigured: 'ಇನ್ನೂ ಸೆಟ್ ಆಗಿಲ್ಲ',
};

const te: Catalog = {
  home: 'హోమ్', marketNav: 'మార్కెట్', predict: 'అంచనా', crops: 'పంటలు',
  chat: 'సంభాషణ', profile: 'ప్రొఫైల్', 'nav.main': 'ప్రధాన', 'nav.tools': 'వ్యవసాయ సాధనాలు',
  namaste: 'నమస్తే', welcomeBack: 'తిరిగి స్వాగతం',
  askInLanguage: 'ధరలు, పంటలు లేదా పథకాల గురించి అడగండి…',
  askAgroSmartAi: 'మీ భాషలో అడగండి',
  mandiPrices: 'మండి ధరలు', pricePrediction: 'ధర అంచనా', bestTimeToSell: 'అమ్మడానికి మంచి సమయం',
  myCrops: 'నా పంటలు', topRecommendations: 'ఉత్తమ సిఫార్సులు',
  next: 'తదుపరి', back: 'వెనుకకు', save: 'సేవ్ చేయి', cancel: 'రద్దు', search: 'వెతకండి',
  skip: 'దాటవేయి', language: 'భాష', theme: 'థీమ్', logout: 'లాగ్ అవుట్',
  live: 'లైవ్', cached: 'నిల్వ ఉంది', unavailable: 'అందుబాటులో లేదు', today: 'ఈరోజు',
  loading: 'లోడ్ అవుతోంది…', tryAgain: 'మళ్ళీ ప్రయత్నించండి', noData: 'ఇంకా డేటా లేదు',
  dataCoverage: 'డేటా కవరేజ్', perQuintal: 'క్వింటాల్‌కు',
  quickReplies: 'ఇలా అడగండి', listening: 'వింటున్నాను…',
  somethingWrong: 'ఏదో తప్పు జరిగింది', notConfigured: 'ఇంకా సెట్ చేయలేదు',
};

const ta: Catalog = {
  home: 'முகப்பு', marketNav: 'சந்தை', predict: 'முன்னறிவிப்பு', crops: 'பயிர்கள்',
  chat: 'உரையாடல்', profile: 'சுயவிவரம்', 'nav.main': 'முதன்மை', 'nav.tools': 'வேளாண் கருவிகள்',
  namaste: 'வணக்கம்', welcomeBack: 'மீண்டும் வருக',
  askInLanguage: 'விலை, பயிர் அல்லது திட்டம் பற்றி கேளுங்கள்…',
  askAgroSmartAi: 'உங்கள் மொழியில் கேளுங்கள்',
  mandiPrices: 'சந்தை விலைகள்', pricePrediction: 'விலை முன்னறிவிப்பு', bestTimeToSell: 'விற்க சிறந்த நேரம்',
  myCrops: 'என் பயிர்கள்', topRecommendations: 'சிறந்த பரிந்துரைகள்',
  next: 'அடுத்து', back: 'பின்', save: 'சேமி', cancel: 'ரத்து', search: 'தேடு',
  skip: 'தவிர்', language: 'மொழி', theme: 'தோற்றம்', logout: 'வெளியேறு',
  live: 'நேரடி', cached: 'சேமிக்கப்பட்டது', unavailable: 'கிடைக்கவில்லை', today: 'இன்று',
  loading: 'ஏற்றுகிறது…', tryAgain: 'மீண்டும் முயற்சி', noData: 'இன்னும் தரவு இல்லை',
  dataCoverage: 'தரவு அளவு', perQuintal: 'ஒரு குவிண்டாலுக்கு',
  quickReplies: 'இதைக் கேளுங்கள்', listening: 'கேட்கிறேன்…',
  somethingWrong: 'ஏதோ தவறு', notConfigured: 'இன்னும் அமைக்கப்படவில்லை',
};

const ml: Catalog = {
  home: 'ഹോം', marketNav: 'മാർക്കറ്റ്', predict: 'പ്രവചനം', crops: 'വിളകൾ',
  chat: 'സംഭാഷണം', profile: 'പ്രൊഫൈൽ', 'nav.main': 'പ്രധാനം', 'nav.tools': 'കാർഷിക ഉപകരണങ്ങൾ',
  namaste: 'നമസ്കാരം', welcomeBack: 'വീണ്ടും സ്വാഗതം',
  askInLanguage: 'വില, വിള അല്ലെങ്കിൽ പദ്ധതികളെക്കുറിച്ച് ചോദിക്കൂ…',
  askAgroSmartAi: 'നിങ്ങളുടെ ഭാഷയിൽ ചോദിക്കൂ',
  mandiPrices: 'മണ്ഡി വിലകൾ', pricePrediction: 'വില പ്രവചനം', bestTimeToSell: 'വിൽക്കാൻ നല്ല സമയം',
  myCrops: 'എന്റെ വിളകൾ', topRecommendations: 'മികച്ച നിർദ്ദേശങ്ങൾ',
  next: 'അടുത്തത്', back: 'പിന്നോട്ട്', save: 'സൂക്ഷിക്കുക', cancel: 'റദ്ദാക്കുക', search: 'തിരയുക',
  skip: 'ഒഴിവാക്കുക', language: 'ഭാഷ', theme: 'തീം', logout: 'ലോഗ് ഔട്ട്',
  live: 'തത്സമയം', cached: 'സൂക്ഷിച്ചത്', unavailable: 'ലഭ്യമല്ല', today: 'ഇന്ന്',
  loading: 'ലോഡ് ചെയ്യുന്നു…', tryAgain: 'വീണ്ടും ശ്രമിക്കുക', noData: 'ഇതുവരെ ഡാറ്റയില്ല',
  dataCoverage: 'ഡാറ്റ കവറേജ്', perQuintal: 'ഒരു ക്വിന്റലിന്',
  quickReplies: 'ഇത് ചോദിക്കൂ', listening: 'കേൾക്കുന്നു…',
  somethingWrong: 'എന്തോ കുഴപ്പം', notConfigured: 'ഇതുവരെ ക്രമീകരിച്ചിട്ടില്ല',
};

const mr: Catalog = {
  home: 'मुख्यपृष्ठ', marketNav: 'बाजारभाव', predict: 'अंदाज', crops: 'पिके',
  chat: 'संवाद', profile: 'प्रोफाइल', 'nav.main': 'मुख्य', 'nav.tools': 'शेतीची अवजारे',
  namaste: 'नमस्कार', welcomeBack: 'पुन्हा स्वागत',
  askInLanguage: 'भाव, पीक किंवा योजनेबद्दल विचारा…',
  askAgroSmartAi: 'तुमच्या भाषेत विचारा',
  mandiPrices: 'बाजारभाव', pricePrediction: 'भावाचा अंदाज', bestTimeToSell: 'विकण्याची योग्य वेळ',
  myCrops: 'माझी पिके', topRecommendations: 'सर्वोत्तम शिफारसी',
  next: 'पुढे', back: 'मागे', save: 'जतन करा', cancel: 'रद्द', search: 'शोधा',
  skip: 'वगळा', language: 'भाषा', theme: 'थीम', logout: 'बाहेर पडा',
  live: 'थेट', cached: 'साठवलेले', unavailable: 'उपलब्ध नाही', today: 'आज',
  loading: 'लोड होत आहे…', tryAgain: 'पुन्हा प्रयत्न करा', noData: 'अजून माहिती नाही',
  dataCoverage: 'माहितीची उपलब्धता', perQuintal: 'प्रति क्विंटल',
  quickReplies: 'हे विचारा', listening: 'ऐकत आहे…',
  somethingWrong: 'काहीतरी चूक झाली', notConfigured: 'अजून सेट केलेले नाही',
};

const gu: Catalog = {
  home: 'હોમ', marketNav: 'બજાર', predict: 'અનુમાન', crops: 'પાક',
  chat: 'વાતચીત', profile: 'પ્રોફાઇલ', 'nav.main': 'મુખ્ય', 'nav.tools': 'ખેતીના સાધનો',
  namaste: 'નમસ્તે', welcomeBack: 'પાછા સ્વાગત',
  askInLanguage: 'ભાવ, પાક કે યોજના વિશે પૂછો…',
  askAgroSmartAi: 'તમારી ભાષામાં પૂછો',
  mandiPrices: 'મંડી ભાવ', pricePrediction: 'ભાવ અનુમાન', bestTimeToSell: 'વેચવાનો યોગ્ય સમય',
  myCrops: 'મારા પાક', topRecommendations: 'શ્રેષ્ઠ સૂચનો',
  next: 'આગળ', back: 'પાછળ', save: 'સાચવો', cancel: 'રદ કરો', search: 'શોધો',
  skip: 'છોડો', language: 'ભાષા', theme: 'થીમ', logout: 'લૉગ આઉટ',
  live: 'લાઇવ', cached: 'સાચવેલું', unavailable: 'ઉપલબ્ધ નથી', today: 'આજે',
  loading: 'લોડ થઈ રહ્યું છે…', tryAgain: 'ફરી પ્રયાસ કરો', noData: 'હજી ડેટા નથી',
  dataCoverage: 'ડેટા કવરેજ', perQuintal: 'પ્રતિ ક્વિન્ટલ',
  quickReplies: 'આ પૂછો', listening: 'સાંભળી રહ્યો છું…',
  somethingWrong: 'કંઈક ખોટું થયું', notConfigured: 'હજી સેટ કરેલું નથી',
};

const bn: Catalog = {
  home: 'হোম', marketNav: 'বাজার', predict: 'পূর্বাভাস', crops: 'ফসল',
  chat: 'বার্তা', profile: 'প্রোফাইল', 'nav.main': 'প্রধান', 'nav.tools': 'কৃষি সরঞ্জাম',
  namaste: 'নমস্কার', welcomeBack: 'আবার স্বাগতম',
  askInLanguage: 'দাম, ফসল বা প্রকল্প নিয়ে জিজ্ঞাসা করুন…',
  askAgroSmartAi: 'আপনার ভাষায় জিজ্ঞাসা করুন',
  mandiPrices: 'মণ্ডির দাম', pricePrediction: 'দামের পূর্বাভাস', bestTimeToSell: 'বিক্রির সঠিক সময়',
  myCrops: 'আমার ফসল', topRecommendations: 'সেরা সুপারিশ',
  next: 'পরবর্তী', back: 'পিছনে', save: 'সংরক্ষণ', cancel: 'বাতিল', search: 'খুঁজুন',
  skip: 'এড়িয়ে যান', language: 'ভাষা', theme: 'থিম', logout: 'লগ আউট',
  live: 'লাইভ', cached: 'সংরক্ষিত', unavailable: 'উপলব্ধ নয়', today: 'আজ',
  loading: 'লোড হচ্ছে…', tryAgain: 'আবার চেষ্টা করুন', noData: 'এখনও তথ্য নেই',
  dataCoverage: 'তথ্যের পরিধি', perQuintal: 'প্রতি কুইন্টাল',
  quickReplies: 'এটি জিজ্ঞাসা করুন', listening: 'শুনছি…',
  somethingWrong: 'কিছু ভুল হয়েছে', notConfigured: 'এখনও সেট করা হয়নি',
};

const pa: Catalog = {
  home: 'ਘਰ', marketNav: 'ਮੰਡੀ', predict: 'ਅੰਦਾਜ਼ਾ', crops: 'ਫ਼ਸਲਾਂ',
  chat: 'ਗੱਲਬਾਤ', profile: 'ਪ੍ਰੋਫ਼ਾਈਲ', 'nav.main': 'ਮੁੱਖ', 'nav.tools': 'ਖੇਤੀ ਔਜ਼ਾਰ',
  namaste: 'ਸਤ ਸ੍ਰੀ ਅਕਾਲ', welcomeBack: 'ਜੀ ਆਇਆਂ ਨੂੰ',
  askInLanguage: 'ਕੀਮਤ, ਫ਼ਸਲ ਜਾਂ ਯੋਜਨਾ ਬਾਰੇ ਪੁੱਛੋ…',
  askAgroSmartAi: 'ਆਪਣੀ ਭਾਸ਼ਾ ਵਿੱਚ ਪੁੱਛੋ',
  mandiPrices: 'ਮੰਡੀ ਭਾਅ', pricePrediction: 'ਭਾਅ ਦਾ ਅੰਦਾਜ਼ਾ', bestTimeToSell: 'ਵੇਚਣ ਦਾ ਸਹੀ ਸਮਾਂ',
  myCrops: 'ਮੇਰੀਆਂ ਫ਼ਸਲਾਂ', topRecommendations: 'ਸਭ ਤੋਂ ਵਧੀਆ ਸਿਫ਼ਾਰਸ਼ਾਂ',
  next: 'ਅੱਗੇ', back: 'ਪਿੱਛੇ', save: 'ਸੰਭਾਲੋ', cancel: 'ਰੱਦ ਕਰੋ', search: 'ਖੋਜੋ',
  skip: 'ਛੱਡੋ', language: 'ਭਾਸ਼ਾ', theme: 'ਥੀਮ', logout: 'ਲੌਗ ਆਊਟ',
  live: 'ਲਾਈਵ', cached: 'ਸੰਭਾਲਿਆ', unavailable: 'ਉਪਲਬਧ ਨਹੀਂ', today: 'ਅੱਜ',
  loading: 'ਲੋਡ ਹੋ ਰਿਹਾ ਹੈ…', tryAgain: 'ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ', noData: 'ਹਾਲੇ ਡੇਟਾ ਨਹੀਂ',
  dataCoverage: 'ਡੇਟਾ ਕਵਰੇਜ', perQuintal: 'ਪ੍ਰਤੀ ਕੁਇੰਟਲ',
  quickReplies: 'ਇਹ ਪੁੱਛੋ', listening: 'ਸੁਣ ਰਿਹਾ ਹਾਂ…',
  somethingWrong: 'ਕੁਝ ਗੜਬੜ ਹੋ ਗਈ', notConfigured: 'ਹਾਲੇ ਸੈੱਟ ਨਹੀਂ ਹੈ',
};

const or: Catalog = {
  home: 'ହୋମ', marketNav: 'ବଜାର', predict: 'ପୂର୍ବାନୁମାନ', crops: 'ଫସଲ',
  chat: 'କଥାବାର୍ତ୍ତା', profile: 'ପ୍ରୋଫାଇଲ', 'nav.main': 'ମୁଖ୍ୟ', 'nav.tools': 'କୃଷି ଉପକରଣ',
  namaste: 'ନମସ୍କାର', welcomeBack: 'ପୁଣି ସ୍ୱାଗତ',
  askInLanguage: 'ଦର, ଫସଲ କିମ୍ବା ଯୋଜନା ବିଷୟରେ ପଚାରନ୍ତୁ…',
  askAgroSmartAi: 'ଆପଣଙ୍କ ଭାଷାରେ ପଚାରନ୍ତୁ',
  mandiPrices: 'ମଣ୍ଡି ଦର', pricePrediction: 'ଦର ପୂର୍ବାନୁମାନ', bestTimeToSell: 'ବିକ୍ରି କରିବାର ସଠିକ ସମୟ',
  myCrops: 'ମୋର ଫସଲ', topRecommendations: 'ସର୍ବୋତ୍ତମ ସୁପାରିଶ',
  next: 'ପରବର୍ତ୍ତୀ', back: 'ପଛକୁ', save: 'ସଞ୍ଚୟ', cancel: 'ବାତିଲ', search: 'ଖୋଜନ୍ତୁ',
  skip: 'ଛାଡ଼ନ୍ତୁ', language: 'ଭାଷା', theme: 'ଥିମ', logout: 'ଲଗ ଆଉଟ',
  live: 'ଲାଇଭ', cached: 'ସଞ୍ଚିତ', unavailable: 'ଉପଲବ୍ଧ ନାହିଁ', today: 'ଆଜି',
  loading: 'ଲୋଡ ହେଉଛି…', tryAgain: 'ପୁଣି ଚେଷ୍ଟା କରନ୍ତୁ', noData: 'ଏପର୍ଯ୍ୟନ୍ତ ତଥ୍ୟ ନାହିଁ',
  dataCoverage: 'ତଥ୍ୟ ଉପଲବ୍ଧତା', perQuintal: 'ପ୍ରତି କୁଇଣ୍ଟାଲ',
  quickReplies: 'ଏହା ପଚାରନ୍ତୁ', listening: 'ଶୁଣୁଛି…',
  somethingWrong: 'କିଛି ଭୁଲ ହେଲା', notConfigured: 'ଏପର୍ଯ୍ୟନ୍ତ ସେଟ ହୋଇନାହିଁ',
};

const catalogs: Record<Language, Catalog> = {
  en, hi, kn, te, ta, ml, mr, gu, bn, pa, or,
};

/** Translate a key. Falls back to English, then to the key itself. */
export function t(key: string, lang: Language = 'en'): string {
  return catalogs[lang]?.[key] ?? en[key] ?? key;
}

/** All keys the English catalog defines — used by the coverage report script. */
export const ALL_KEYS = Object.keys(en);

/** Keys missing a real translation for a language (falls back to English). */
export function missingKeys(lang: Language): string[] {
  if (lang === 'en') return [];
  return ALL_KEYS.filter((k) => !(k in catalogs[lang]));
}

/** Distance helper for a "how complete is this language" bar. */
export function coverage(lang: Language): number {
  if (lang === 'en') return 100;
  const done = ALL_KEYS.length - missingKeys(lang).length;
  return Math.round((done / ALL_KEYS.length) * 100);
}

export default catalogs;
