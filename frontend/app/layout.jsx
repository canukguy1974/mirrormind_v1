import "./globals.css";

export const metadata = {
  title: "MirrorMind v1",
  description: "Low-latency text, voice, and avatar orchestration"
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
