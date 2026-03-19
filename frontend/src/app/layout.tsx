import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DCX Pipeline",
  description: "Digital Customer Experience Pipeline",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="font-sans h-screen overflow-hidden antialiased">{children}</body>
    </html>
  );
}
