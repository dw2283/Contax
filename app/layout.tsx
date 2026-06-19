import type { Metadata } from "next";
import "@copilotkit/react-ui/styles.css";
import "@xyflow/react/dist/style.css";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Contax AI",
  description: "Interactive relationship graph with a CopilotKit matchmaking sidebar, backed by Redis and Weave.",
  icons: {
    icon: "/logo-contax-c-multi-connected.png",
    apple: "/logo-contax-c-multi-connected.png",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
