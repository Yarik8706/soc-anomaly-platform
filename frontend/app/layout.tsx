import type { Metadata } from "next";
import { ToastProvider } from "@/components/ui/toast";
import { SessionProvider } from "@/features/auth/session-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "SOC Lens", template: "%s · SOC Lens" },
  description: "Рабочее место SOC-аналитика для поиска и расследования аномалий",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body>
        <SessionProvider>
          <ToastProvider>{children}</ToastProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
