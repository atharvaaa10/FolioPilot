"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { apiClient, ApiError } from "@/lib/api";
import { APP_NAME, APP_DESCRIPTION } from "@/lib/constants";
import { LocalTime } from "@/components/ui/local-time";

interface SystemReadinessData {
  status: string;
  database: string;
  redis: string;
}

export default function HomePage(): React.JSX.Element {
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
    dataUpdatedAt,
    errorUpdatedAt,
  } = useQuery<SystemReadinessData, ApiError>({
    queryKey: ["health-ready"],
    queryFn: () => apiClient<SystemReadinessData>("/api/v1/health/ready"),
  });

  const lastChecked = isError
    ? errorUpdatedAt || undefined
    : dataUpdatedAt || undefined;

  return (
    <div className="container mx-auto flex flex-col items-center justify-center px-4 py-16 sm:px-8">
      <div className="max-w-2xl text-center space-y-4 mb-12">
        <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl">
          Welcome to <span className="text-primary">{APP_NAME}</span>
        </h1>
        <p className="text-lg text-muted-foreground">
          {APP_DESCRIPTION}. Foundation architecture and Phase 1 authentication active.
        </p>
        <div className="flex items-center justify-center gap-4 pt-2">
          <a href="/register">
            <Button>Create Account</Button>
          </a>
          <a href="/dashboard">
            <Button variant="outline">View Dashboard</Button>
          </a>
        </div>
      </div>

      <div className="w-full max-w-lg">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>System Status</CardTitle>
              {isFetching && !isLoading && (
                <span className="text-xs text-muted-foreground animate-pulse">
                  Refreshing...
                </span>
              )}
            </div>
            <CardDescription>
              Backend readiness probe connected to /api/v1/health/ready
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-4">
            {isLoading ? (
              <div className="space-y-3 py-2">
                <div className="flex items-center justify-between py-2 border-b border-border">
                  <span className="text-sm font-medium">FastAPI Service</span>
                  <Badge variant="secondary">Checking...</Badge>
                </div>
                <div className="flex items-center justify-between py-2 border-b border-border">
                  <span className="text-sm font-medium">PostgreSQL (pgvector)</span>
                  <Badge variant="secondary">Checking...</Badge>
                </div>
                <div className="flex items-center justify-between py-2">
                  <span className="text-sm font-medium">Redis Broker</span>
                  <Badge variant="secondary">Checking...</Badge>
                </div>
              </div>
            ) : isError ? (
              <div className="space-y-4">
                <div className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive border border-destructive/20">
                  <p className="font-semibold">Failed to connect to backend</p>
                  <p className="text-xs mt-1">
                    {error?.code}: {error?.message}
                  </p>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between py-2 border-b border-border">
                    <span className="text-sm font-medium">FastAPI Service</span>
                    <Badge variant="destructive">Unavailable</Badge>
                  </div>
                  <div className="flex items-center justify-between py-2 border-b border-border">
                    <span className="text-sm font-medium">PostgreSQL (pgvector)</span>
                    <Badge variant="destructive">
                      {error?.details && typeof error.details === "object" && "database" in error.details
                        ? String((error.details as Record<string, unknown>).database)
                        : "Unknown"}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between py-2">
                    <span className="text-sm font-medium">Redis Broker</span>
                    <Badge variant="destructive">
                      {error?.details && typeof error.details === "object" && "redis" in error.details
                        ? String((error.details as Record<string, unknown>).redis)
                        : "Unknown"}
                    </Badge>
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center justify-between py-2 border-b border-border">
                  <span className="text-sm font-medium">FastAPI Service</span>
                  <Badge variant="success">Online</Badge>
                </div>
                <div className="flex items-center justify-between py-2 border-b border-border">
                  <span className="text-sm font-medium">PostgreSQL (pgvector)</span>
                  <Badge
                    variant={data?.database === "healthy" ? "success" : "destructive"}
                  >
                    {data?.database || "Unknown"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between py-2">
                  <span className="text-sm font-medium">Redis Broker</span>
                  <Badge
                    variant={data?.redis === "healthy" ? "success" : "destructive"}
                  >
                    {data?.redis || "Unknown"}
                  </Badge>
                </div>
              </div>
            )}
          </CardContent>

          <CardFooter className="flex justify-between border-t border-border pt-4">
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              Last probed: <LocalTime timestamp={lastChecked} />
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={isFetching}
              onClick={() => void refetch()}
            >
              Check Health
            </Button>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}

