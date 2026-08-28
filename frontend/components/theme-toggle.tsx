"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const isDark = resolvedTheme === "dark";
  // The theme is only known on the client; keep the server-rendered label stable
  // until mount so React does not report a hydration mismatch.
  const label = !mounted ? "Toggle theme" : isDark ? "Switch to light mode" : "Switch to dark mode";
  return (
    <Button
      variant="outline"
      size="icon"
      className="h-9 w-9 shrink-0"
      aria-label={label}
      title={label}
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      {mounted ? isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4 opacity-0" />}
    </Button>
  );
}
