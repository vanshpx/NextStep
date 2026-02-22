import type { Metadata } from "next";
import { Roboto } from "next/font/google";
import "./globals.css";
import { ItineraryProvider } from "@/context/ItineraryContext";

const roboto = Roboto({
  subsets: ["latin"],
  display: "swap",
  weight: ["300", "400", "500", "700", "900"],
});

export const metadata: Metadata = {
  title: "Voyage - AI Co-Pilot for Travel Agents",
  description: "Plan, monitor, and adapt trips in real-time with AI-powered tools.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={roboto.className} suppressHydrationWarning>
      <body className="antialiased">
        <ItineraryProvider>
          {children}
        </ItineraryProvider>
      </body>
    </html>
  );
}
