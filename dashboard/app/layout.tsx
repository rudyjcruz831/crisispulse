import type { Metadata } from "next";
import "./globals.css";
import { LocaleProvider } from "./i18n";
import { getRequestLocale } from "./i18n-server";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getRequestLocale();
  return locale === "es"
    ? {
        title: "CrisisPulse — Señales de reportes de inundaciones",
        description: "Detección explicable de anomalías en la cobertura de inundaciones con datos de noticias de GDELT.",
      }
    : {
        title: "CrisisPulse — Flood reporting signals",
        description: "Explainable flood-reporting anomaly detection using GDELT news data.",
      };
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const initialLocale = await getRequestLocale();
  return (
    <html lang={initialLocale} suppressHydrationWarning>
      <body><LocaleProvider initialLocale={initialLocale}>{children}</LocaleProvider></body>
    </html>
  );
}
