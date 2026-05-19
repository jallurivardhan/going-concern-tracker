import type { Metadata } from "next";
import "./globals.css";
import { Header } from "@/components/site/Header";
import { Footer } from "@/components/site/Footer";
import { ClientProviders } from "@/components/ClientProviders";

const _BASE_URL =
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://going-concern-tracker.vercel.app";

export const metadata: Metadata = {
  title: {
    default: "Going Concern Tracker",
    template: "%s | Going Concern Tracker",
  },
  description:
    "A free public tracker of going-concern opinions in SEC filings. Every flag cited to source.",
  metadataBase: new URL(_BASE_URL),
  openGraph: {
    type: "website",
    siteName: "Going Concern Tracker",
    title: "Going Concern Tracker",
    description:
      "Free public tracker of going-concern audit opinions in SEC 10-K filings. Every flag cited to the exact paragraph.",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "Going Concern Tracker — auditor warnings surfaced from SEC filings",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Going Concern Tracker",
    description:
      "Free public tracker of going-concern audit opinions in SEC 10-K filings. Every flag cited to source.",
    images: ["/og-image.png"],
  },
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col bg-white font-sans text-slate-900 antialiased">
        <ClientProviders>
          <Header />
          <main className="flex-1">{children}</main>
          <Footer />
        </ClientProviders>
      </body>
    </html>
  );
}
