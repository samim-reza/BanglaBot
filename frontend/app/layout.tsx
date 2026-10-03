import type { Metadata } from "next";
import { Noto_Sans_Bengali } from "next/font/google";
import { ThemeProvider } from "next-themes";

import { AppToastProvider } from "@/components/app-toast";
import { BRAND } from "@/lib/brand";
import "./globals.css";

const notoSansBengali = Noto_Sans_Bengali({
  subsets: ["bengali", "latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-noto-bengali",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: `${BRAND.name} | AI receptionist for phone and website chat`,
    template: `%s | ${BRAND.name}`,
  },
  description:
    "Ready-made AI voice and chat agents for clinics, real estate agencies, home services and e-commerce. They answer every call 24/7, book straight into your records and call customers back.",
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
