import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RetentionOps | Subscriber intelligence",
  description: "Traceable synthetic subscription risk, cohort outcomes and model status.",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
