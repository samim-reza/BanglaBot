import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center rounded-full px-2.5 py-0.5 text-[12.5px] font-semibold", {
  variants: {
    variant: {
      default: "bg-accent text-accent-foreground",
      secondary: "bg-secondary text-muted-foreground",
      outline: "border text-foreground",
      success: "bg-[#d1fae5] text-[#065f46] dark:bg-emerald-500/15 dark:text-emerald-300",
      warning: "bg-[#fef3c7] text-[#92400e] dark:bg-amber-500/15 dark:text-amber-300",
    },
  },
  defaultVariants: { variant: "default" },
});

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
