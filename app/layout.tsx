import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nazar · Meaningful market change",
  description: "A watchlist that explains what mattered while you were away.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">{children}</body>
    </html>
  );
}
