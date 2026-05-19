"use client";

import { TooltipProvider } from "@/components/ui/tooltip";

export function ClientProviders({ children }: { children: React.ReactNode }) {
  return <TooltipProvider delayDuration={200}>{children}</TooltipProvider>;
}
