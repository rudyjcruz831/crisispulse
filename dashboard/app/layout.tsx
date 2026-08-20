import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CrisisPulse — Flood reporting signals",
  description: "Explainable flood-reporting anomaly detection using GDELT news data.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
