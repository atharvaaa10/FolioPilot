"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { APP_NAME } from "@/lib/constants";

export function NavHeader() {
  const { status, user, logout } = useAuth();
  const router = useRouter();

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto flex h-14 items-center justify-between px-4 sm:px-8">
        <div className="flex items-center space-x-2">
          <Link href="/" className="text-xl font-bold tracking-tight text-primary">
            {APP_NAME}
          </Link>
          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground uppercase">
            Phase 2
          </span>
        </div>

        <nav className="flex items-center space-x-3">
          {status === "loading" ? (
            <div className="h-8 w-20 animate-pulse rounded bg-muted" />
          ) : status === "authenticated" && user ? (
            <div className="flex items-center space-x-3">
              <Link
                href="/dashboard"
                className="text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
              >
                Dashboard
              </Link>
              <Link
                href="/funds"
                className="text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
              >
                Funds
              </Link>
              <span className="hidden text-xs text-muted-foreground sm:inline-block">
                {user.email}
              </span>
              <Button variant="outline" size="sm" onClick={handleLogout}>
                Log out
              </Button>
            </div>
          ) : (
            <div className="flex items-center space-x-2">
              <Link href="/login">
                <Button variant="ghost" size="sm">
                  Log in
                </Button>
              </Link>
              <Link href="/register">
                <Button size="sm">Get Started</Button>
              </Link>
            </div>
          )}
        </nav>
      </div>
    </header>
  );
}
