import "./styles.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Atlas Search · Distributed Web Search",
  description: "An independent, LAN-hosted distributed web search engine.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
