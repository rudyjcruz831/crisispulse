import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "CrisisPulse Admin — Operations console",
  description: "Private local operations view for CrisisPulse data, forecasts, reviews, and readiness.",
  robots: { index: false, follow: false },
};

export default function AdminLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
