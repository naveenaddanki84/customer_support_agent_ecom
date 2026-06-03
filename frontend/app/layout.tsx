import type { Metadata } from "next";
import './globals.css'

export const metadata: Metadata = {
  title: "Multi-Agent Customer Chat",
  description: "A multi-agent system for customer support with modern AI assistance.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full antialiased bg-gradient-to-br from-green-50 via-white to-emerald-50 text-gray-900">
        {children}
      </body>
    </html>
  );
}