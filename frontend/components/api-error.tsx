import { AlertCircle } from "lucide-react";

export function ApiError({ message }: { message: string | null }) {
  if (!message) return null;
  const lower = message.toLowerCase();
  const title =
    lower.includes("login required") || lower.includes("session expired") || lower.includes("invalid token") || lower.includes("invalid username or password")
      ? "Authentication required"
      : lower.includes("could not connect") || lower.includes("network")
        ? "Backend API offline"
        : lower.includes("permission")
          ? "Permission denied"
          : lower.includes("server error")
            ? "Backend error"
            : "Request failed";
  return (
    <div className="flex items-start gap-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
      <div>
        <div className="font-medium text-destructive">{title}</div>
        <div className="mt-1 text-muted-foreground">{message}</div>
      </div>
    </div>
  );
}
