import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell } from "./components/AppShell";
import "./globals.css";

export const metadata: Metadata = {
  title: "IPRL/CAE Hub",
  description: "Panel operativo para documentacion PRL/CAE y autorizaciones ARM"
};

export default function RootLayout({
  children
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="es" suppressHydrationWarning>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
