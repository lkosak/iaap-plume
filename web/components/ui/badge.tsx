import * as React from "react";
import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-[#243e73]/20 bg-[#eef2f8] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-[#243e73]",
        className,
      )}
      {...props}
    />
  );
}
