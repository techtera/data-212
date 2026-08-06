import type { Metadata } from "next";
import "./globals.css";
import { MswStarter } from "@/components/MswStarter";

export const metadata: Metadata = {
  title: "TERAFAC — Cloud Training UI",
  description: "Single-user agentic auto-training pipeline.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <MswStarter>{children}</MswStarter>
      </body>
    </html>
  );
}
