"use client";

import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { Severity } from "@/lib/api";

const SEVERITY_CONFIG: Record<
  Severity,
  { label: string; className: string; tooltip: string }
> = {
  critical: {
    label: "Critical",
    className: "bg-red-100 text-red-700",
    tooltip:
      "The auditor formally issued a going-concern opinion. This is the strongest signal — the auditor has stated in writing that the company may not be able to continue operating.",
  },
  elevated: {
    label: "Elevated",
    className: "bg-amber-100 text-amber-700",
    tooltip:
      "The auditor noted substantial doubt about the company's ability to continue, but management's plans were sufficient to alleviate the doubt.",
  },
  watch: {
    label: "Watch",
    className: "bg-slate-100 text-slate-700",
    tooltip:
      "Going-concern risk was discussed in management's MD&A or notes, but the auditor did not formally modify their opinion.",
  },
  none: {
    label: "No flag",
    className: "bg-emerald-50 text-emerald-700",
    tooltip:
      "The auditor issued a clean unqualified opinion. No going-concern language present.",
  },
};

interface SeverityBadgeProps {
  severity: Severity;
  size?: "default" | "large";
  className?: string;
}

export function SeverityBadge({ severity, size = "default", className }: SeverityBadgeProps) {
  const config = SEVERITY_CONFIG[severity];

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          className={cn(
            "min-w-[44px] cursor-default",
            size === "large" && "px-3 py-1 text-sm",
            config.className,
            className
          )}
          role="img"
          aria-label={`Severity: ${config.label}`}
        >
          {config.label}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>{config.tooltip}</TooltipContent>
    </Tooltip>
  );
}
