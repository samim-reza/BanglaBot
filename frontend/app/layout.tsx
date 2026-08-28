import type { Metadata } from "next";
import { Noto_Sans_Bengali } from "next/font/google";
import { ThemeProvider } from "next-themes";

import { AppToastProvider } from "@/components/app-toast";
import "./globals.css";

const notoSansBengali = Noto_Sans_Bengali({
  subsets: ["bengali", "latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-noto-bengali",
  display: "swap",
});

export const metadata: Metadata = {
  title: "BanglaBot | Order confirmation calls",
  description:
    "BanglaBot calls your e-commerce customers in Bangla or English, confirms every order, and records the outcome so you only ship what people actually want.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={notoSansBengali.variable} suppressHydrationWarning>
      <body className="font-sans antialiased">
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
          <AppToastProvider>{children}</AppToastProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
