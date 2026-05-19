import { cn } from "@/lib/utils";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary";
  size?: "default" | "sm";
  asChild?: boolean;
}

function Button({ className, variant = "primary", size = "default", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex min-h-[44px] items-center justify-center rounded-md font-sans text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
        variant === "primary" && "bg-slate-900 text-white hover:bg-slate-800",
        variant === "secondary" &&
          "border border-slate-300 bg-white text-slate-900 hover:border-slate-400 hover:bg-slate-50",
        size === "default" && "px-5 py-2.5",
        size === "sm" && "px-3 py-1.5 text-xs",
        className
      )}
      {...props}
    />
  );
}

export { Button };
