import React, { createContext, useContext, useState, useCallback } from 'react';
import { Language, t as translate, isRtl } from '@/lib/i18n';

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: (key: Parameters<typeof translate>[0]) => string;
  rtl: boolean;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export const LanguageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [language, setLanguageState] = useState<Language>('en');

  const setLanguage = useCallback((lang: Language) => {
    setLanguageState(lang);
    document.documentElement.dir = isRtl(lang) ? 'rtl' : 'ltr';
  }, []);

  const t = useCallback((key: Parameters<typeof translate>[0]) => {
    return translate(key, language);
  }, [language]);

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t, rtl: isRtl(language) }}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = () => {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useLanguage must be used within LanguageProvider');
  return ctx;
};
