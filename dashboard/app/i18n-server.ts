import { cookies } from "next/headers";
import { localeCookieName } from "./i18n-shared";
import type { Locale } from "./i18n-shared";

export async function getRequestLocale(): Promise<Locale> {
  const cookieStore = await cookies();
  return cookieStore.get(localeCookieName)?.value === "es" ? "es" : "en";
}
