import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ItineraryProvider } from "@/context/ItineraryContext";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
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
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} font-sans antialiased`}>
        <ItineraryProvider>
          {children}
        </ItineraryProvider>
      </body>
    </html>
  );
}
