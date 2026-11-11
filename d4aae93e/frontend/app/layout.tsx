import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CampusPulse — Find any place on the TIET campus",
  description:
    "Search verified TIET campus locations by the names students use, explore by category, and follow a safe walking route on the campus map.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
