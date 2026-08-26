import type { Metadata } from "next";
import { getRequestLocale } from "../../i18n-server";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getRequestLocale();
  return {
    title: locale === "es"
      ? "Datos de entrenamiento de CrisisPulse — Laboratorio local"
      : "CrisisPulse Training Data — Local lab",
    description: locale === "es"
      ? "Vista privada y auditable de las etiquetas disponibles para entrenar modelos locales de CrisisPulse."
      : "Private, auditable view of labels available for local CrisisPulse model training.",
    robots: { index: false, follow: false },
  };
}

export default function TrainingDataLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
