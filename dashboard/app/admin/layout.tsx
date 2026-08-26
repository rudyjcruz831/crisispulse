import type { Metadata } from "next";
import { getRequestLocale } from "../i18n-server";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getRequestLocale();
  return {
    title: locale === "es"
      ? "Administración de CrisisPulse — Consola de operaciones"
      : "CrisisPulse Admin — Operations console",
    description: locale === "es"
      ? "Vista local privada de datos, pronósticos, revisiones y preparación de CrisisPulse."
      : "Private local operations view for CrisisPulse data, forecasts, reviews, and readiness.",
    robots: { index: false, follow: false },
  };
}

export default function AdminLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
