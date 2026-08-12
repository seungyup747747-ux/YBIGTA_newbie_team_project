import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Data Analysis Agent",
  description: "Next.js agent UI that calls MCP tools for data analysis.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
