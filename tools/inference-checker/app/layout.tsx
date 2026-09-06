import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Inference Checker — Semantic Segmentation Analysis",
  description:
    "Compare semantic segmentation predictions with overlays, side-by-side views, pixel-level diffs, and per-class metrics.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}

      </body>
    </html>
  );
}
