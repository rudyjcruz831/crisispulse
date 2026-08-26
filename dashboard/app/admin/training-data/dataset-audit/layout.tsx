import type { Metadata } from "next";
import { getRequestLocale } from "../../../i18n-server";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getRequestLocale();
  return {
    title: locale === "es"
      ? "Auditoría de datos externos — CrisisPulse"
      : "External Dataset Audit — CrisisPulse",
    description: locale === "es"
      ? "Compruebe derechos, contenido y compatibilidad de etiquetas antes de entrenar CrisisPulse con datos externos."
      : "Check rights, content, and label compatibility before training CrisisPulse with external data.",
    robots: { index: false, follow: false },
  };
}

export default function DatasetAuditLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
