import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
  LANGUAGES,
  type Language,
  htmlLang,
  isRtl,
  speechLocale,
  t as translate,
} from '@/lib/i18n';
import { env } from '@/lib/env';

const STORAGE_KEY = 'agrosmart.language';

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: (key: string) => string;
  rtl: boolean;
  speechLocale: string;
  languages: Language[];
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

function initialLanguage(): Language {
  // 1. An explicit choice in the app wins.
  const saved = localStorage.getItem(STORAGE_KEY) as Language | null;
  if (saved && LANGUAGES.includes(saved)) return saved;

  // 2. Otherwise follow the language saved in the farmer's profile, so the app
  //    opens in the language they picked during onboarding.
  try {
    const raw = localStorage.getItem('farmintel_profile');
    if (raw) {
      const profileLang = JSON.parse(raw)?.language as Language | undefined;
      if (profileLang && LANGUAGES.includes(profileLang)) return profileLang;
    }
  } catch {
    /* corrupt cache — fall through */
  }

  // 3. Browser language, then the configured default.
  const nav = (navigator.language || '').split('-')[0] as Language;
  if (LANGUAGES.includes(nav)) return nav;
  return env.defaultLanguage;
}

export const LanguageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [language, setLanguageState] = useState<Language>(initialLanguage);

  const setLanguage = useCallback((lang: Language) => {
    setLanguageState(lang);
    localStorage.setItem(STORAGE_KEY, lang);
  }, []);

  useEffect(() => {
    document.documentElement.lang = htmlLang[language];
    document.documentElement.dir = isRtl(language) ? 'rtl' : 'ltr';
  }, [language]);

  const t = useCallback((key: string) => translate(key, language), [language]);

  const value = useMemo(
    () => ({
      language,
      setLanguage,
      t,
      rtl: isRtl(language),
      speechLocale: speechLocale[language],
      languages: LANGUAGES,
    }),
    [language, setLanguage, t],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
};

export const useLanguage = () => {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useLanguage must be used within LanguageProvider');
  return ctx;
};
