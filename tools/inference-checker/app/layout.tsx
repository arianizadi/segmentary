import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Inference Checker — Segmentation Analysis",
  description:
    "Inspect semantic, instance, and panoptic segmentation with overlays, synchronized comparisons, object identities, and error review.",
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
