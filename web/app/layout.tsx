import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "TraceForge | Security Flight Recorder",
  description: "Evidence-led cybersecurity incident reconstruction",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
