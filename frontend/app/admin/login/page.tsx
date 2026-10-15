"use client";

import { Suspense } from "react";
import Link from "next/link";

import { AdminLoginForm } from "@/components/admin/auth/login-form";

export default function AdminLoginPage() {
  return (
    <>
      <Suspense fallback={<div className="py-10 text-sm text-muted-foreground">Loading…</div>}>
        <AdminLoginForm />
      </Suspense>
      <p className="text-center text-xs text-muted-foreground">
        Business owner?{" "}
        <Link href="/login" className="text-primary hover:underline">
          Sign in to your portal
        </Link>
        <span aria-hidden="true"> · </span>
        <Link href="/" className="text-primary hover:underline">
          Back to the website
        </Link>
      </p>
    </>
  );
}
