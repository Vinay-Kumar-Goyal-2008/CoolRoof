"use client";

import { Shell } from "@/components/Shell";
import { AppDataProvider } from "@/lib/data";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppDataProvider>
      <Shell>{children}</Shell>
    </AppDataProvider>
  );
}
