"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { AuthGate } from "@/components/auth/auth-gate";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

function DashboardContent() {
  const { user, logout, logoutAll } = useAuth();
  const router = useRouter();
  const [actionLoading, setActionLoading] = React.useState<string | null>(null);

  const handleLogout = async () => {
    setActionLoading("logout");
    try {
      await logout();
      router.push("/login");
    } finally {
      setActionLoading(null);
    }
  };

  const handleLogoutAll = async () => {
    setActionLoading("logoutAll");
    try {
      await logoutAll();
      router.push("/login");
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="container mx-auto max-w-5xl space-y-8 p-4 py-8 sm:px-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Investor Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Welcome back, <span className="font-medium text-foreground">{user?.email}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleLogout}
            disabled={actionLoading !== null}
          >
            {actionLoading === "logout" ? "Logging out..." : "Log out"}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={handleLogoutAll}
            disabled={actionLoading !== null}
          >
            {actionLoading === "logoutAll" ? "Revoking..." : "Log out all devices"}
          </Button>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Security & Authentication State</CardTitle>
            <CardDescription>
              Phase 1 cryptographic token family and session guarantees.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2 text-sm">
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">Account Status</span>
                <Badge variant={user?.is_active ? "default" : "destructive"}>
                  {user?.is_active ? "Active" : "Inactive"}
                </Badge>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">User ID</span>
                <span className="font-mono text-xs">{user?.id}</span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">Email</span>
                <span>{user?.email}</span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">Access Token Storage</span>
                <span className="font-medium text-emerald-600 dark:text-emerald-400">
                  In-Memory (XSS Protected)
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Refresh Token Cookie</span>
                <span className="font-medium text-emerald-600 dark:text-emerald-400">
                  HttpOnly / SameSite=Lax
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Mutual Fund Engine Roadmap</CardTitle>
            <CardDescription>
              Subsequent phases connecting to this authenticated session.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex items-center gap-3 rounded-lg border p-3">
              <div className="h-2 w-2 rounded-full bg-emerald-500" />
              <div>
                <p className="font-medium">Phase 1: Authentication</p>
                <p className="text-xs text-muted-foreground">
                  JWT rotation, reuse detection, rate limiting, and session control.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 rounded-lg border p-3 opacity-75">
              <div className="h-2 w-2 rounded-full bg-muted-foreground" />
              <div>
                <p className="font-medium">Phase 2: AMFI Master & NAV Sync</p>
                <p className="text-xs text-muted-foreground">
                  Official NAV downloads, daily cron updates, and fund metadata.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 rounded-lg border p-3 opacity-75">
              <div className="h-2 w-2 rounded-full bg-muted-foreground" />
              <div>
                <p className="font-medium">Phase 3: Portfolios & Ledger</p>
                <p className="text-xs text-muted-foreground">
                  SIP tracking, transaction ledger, and capital allocation models.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <AuthGate>
      <DashboardContent />
    </AuthGate>
  );
}

