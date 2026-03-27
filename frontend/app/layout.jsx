import "./globals.css";

export const metadata = {
  title: "AI Assistant",
  description: "Chat, voice, and avatar orchestration."
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
