"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useState,
} from "react";
import { localeCookieName } from "./i18n-shared";
import type { Locale } from "./i18n-shared";

export { localeCookieName } from "./i18n-shared";
export type { Locale } from "./i18n-shared";

type LocaleContextValue = {
  locale: Locale;
  localeTag: "en-US" | "es-US";
  setLocale: (locale: Locale) => void;
};

const storageKey = localeCookieName;
const LocaleContext = createContext<LocaleContextValue | null>(null);

export const defineMessages = <T extends Record<string, string>>(
  en: T,
  es: { [K in keyof T]: string },
) => ({ en, es });

export const formatMessage = (
  template: string,
  values: Record<string, string | number> = {},
) => template.replace(/\{([A-Za-z0-9_]+)\}/g, (match, key: string) => (
  Object.hasOwn(values, key) ? String(values[key]) : match
));

const isLocale = (value: string | null): value is Locale => value === "en" || value === "es";

export function LocaleProvider({
  children,
  initialLocale,
}: Readonly<{ children: React.ReactNode; initialLocale: Locale }>) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  const setLocale = useCallback((nextLocale: Locale) => {
    setLocaleState(nextLocale);
    document.documentElement.lang = nextLocale;
    document.cookie = `${localeCookieName}=${nextLocale}; Path=/; Max-Age=31536000; SameSite=Lax`;
    try {
      window.localStorage.setItem(storageKey, nextLocale);
    } catch {
      // Storage can be unavailable in privacy-restricted browser contexts.
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    const syncLanguage = (event: StorageEvent) => {
      if (event.key === storageKey && isLocale(event.newValue)) {
        setLocaleState(event.newValue);
        document.documentElement.lang = event.newValue;
        document.cookie = `${localeCookieName}=${event.newValue}; Path=/; Max-Age=31536000; SameSite=Lax`;
      }
    };
    window.addEventListener("storage", syncLanguage);
    return () => window.removeEventListener("storage", syncLanguage);
  }, []);

  const value = useMemo<LocaleContextValue>(() => ({
    locale,
    localeTag: locale === "es" ? "es-US" : "en-US",
    setLocale,
  }), [locale, setLocale]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const context = useContext(LocaleContext);
  if (!context) throw new Error("useLocale must be used inside LocaleProvider");
  return context;
}

export function LanguageSwitcher() {
  const { locale, setLocale } = useLocale();
  const selectID = useId();
  const label = locale === "es" ? "Idioma" : "Language";

  return (
    <div className="language-switcher">
      <label htmlFor={selectID}>{label}</label>
      <select
        aria-label={label}
        id={selectID}
        onChange={(event) => setLocale(event.target.value as Locale)}
        value={locale}
      >
        <option value="en">English</option>
        <option value="es">Español</option>
      </select>
    </div>
  );
}
