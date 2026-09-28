"use client";

import { type ReactNode } from "react";
import { type IncidentStatus, type TestResult, type DiffStatus, type DiffSeverity } from "@/lib/api";
import {
  diffSeverityLabels,
  diffStatusLabels,
  incidentStatusLabels,
  testResultLabels,
} from "@/lib/labels";

// ─────────────────────────────────────────────
// StatusBadge
// ─────────────────────────────────────────────

const incidentStatusConfig: Record<IncidentStatus, { className: string }> = {
  OPEN: { className: "bg-blue-500/15 text-blue-400 border border-blue-500/30" },
  INVESTIGATING: { className: "bg-yellow-500/15 text-yellow-400 border border-yellow-500/30" },
  REPRODUCED: { className: "bg-green-500/15 text-green-400 border border-green-500/30" },
  RESOLVED: { className: "bg-gray-500/15 text-gray-400 border border-gray-500/30" },
  ARCHIVED: { className: "bg-gray-600/15 text-gray-500 border border-gray-600/30" },
};

const testResultConfig: Record<TestResult, { className: string; dot: string }> = {
  PASS: { className: "bg-green-500/15 text-green-400 border border-green-500/30", dot: "bg-green-400" },
  FAIL: { className: "bg-red-500/15 text-red-400 border border-red-500/30", dot: "bg-red-400" },
  ERROR: { className: "bg-red-600/15 text-red-500 border border-red-600/30", dot: "bg-red-500" },
  TIMEOUT: { className: "bg-orange-500/15 text-orange-400 border border-orange-500/30", dot: "bg-orange-400" },
  UNKNOWN: { className: "bg-gray-500/15 text-gray-400 border border-gray-500/30", dot: "bg-gray-400" },
};

export function IncidentStatusBadge({ status }: { status: IncidentStatus }) {
  const config = incidentStatusConfig[status];
  return (
    <span className={`badge ${config.className}`}>
      {incidentStatusLabels[status] ?? status}
    </span>
  );
}

export function TestResultBadge({ result }: { result: TestResult }) {
  const config = testResultConfig[result];
  return (
    <span className={`badge ${config.className}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${config.dot}`} />
      {testResultLabels[result] ?? result}
    </span>
  );
}

// ─────────────────────────────────────────────
// DiffStatusBadge
// ─────────────────────────────────────────────

const diffStatusConfig: Record<DiffStatus, { className: string }> = {
  MATCH: { className: "diff-match" },
  CHANGED: { className: "diff-changed" },
  MISSING: { className: "diff-missing" },
  ADDED: { className: "diff-added" },
  UNKNOWN: { className: "diff-unknown" },
};

const diffSeverityConfig: Record<DiffSeverity, { className: string }> = {
  HIGH: { className: "sev-high" },
  MEDIUM: { className: "sev-medium" },
  LOW: { className: "sev-low" },
};

export function DiffStatusBadge({ status }: { status: DiffStatus }) {
  const config = diffStatusConfig[status];
  return (
    <span className={`text-xs font-bold ${config.className}`}>
      {diffStatusLabels[status] ?? status}
    </span>
  );
}

export function DiffSeverityBadge({ severity }: { severity: DiffSeverity }) {
  const config = diffSeverityConfig[severity];
  return (
    <span className={`text-xs ${config.className}`}>
      {diffSeverityLabels[severity] ?? severity}
    </span>
  );
}

// ─────────────────────────────────────────────
// Card
// ─────────────────────────────────────────────

export function Card({
  children,
  className = "",
  hover = false,
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}) {
  return (
    <div
      className={`
        bg-dm-surface border border-dm-border rounded-xl p-5
        ${hover ? "card-hover cursor-pointer" : ""}
        ${className}
      `}
    >
      {children}
    </div>
  );
}

// ─────────────────────────────────────────────
// StatCard
// ─────────────────────────────────────────────

export function StatCard({
  title,
  value,
  subtitle,
  icon,
  color = "blue",
}: {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: ReactNode;
  color?: "blue" | "green" | "red" | "yellow" | "purple";
}) {
  const colorMap = {
    blue: "text-blue-400 bg-blue-500/10",
    green: "text-green-400 bg-green-500/10",
    red: "text-red-400 bg-red-500/10",
    yellow: "text-yellow-400 bg-yellow-500/10",
    purple: "text-purple-400 bg-purple-500/10",
  };

  return (
    <Card hover>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-dm-muted font-medium uppercase tracking-wider mb-1">{title}</p>
          <p className="text-3xl font-bold text-dm-text">{value}</p>
          {subtitle && <p className="text-xs text-dm-muted mt-1">{subtitle}</p>}
        </div>
        <div className={`p-2.5 rounded-lg ${colorMap[color]}`}>
          {icon}
        </div>
      </div>
    </Card>
  );
}

// ─────────────────────────────────────────────
// LoadingSpinner
// ─────────────────────────────────────────────

export function LoadingSpinner({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sizeMap = { sm: "w-4 h-4", md: "w-8 h-8", lg: "w-12 h-12" };
  return (
    <div className={`${sizeMap[size]} animate-spin rounded-full border-2 border-dm-border border-t-blue-400`} />
  );
}

// ─────────────────────────────────────────────
// PageHeader
// ─────────────────────────────────────────────

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between mb-8">
      <div>
        <h1 className="text-2xl font-bold text-dm-text">{title}</h1>
        {subtitle && <p className="text-sm text-dm-muted mt-1">{subtitle}</p>}
      </div>
      {action && <div>{action}</div>}
    </div>
  );
}

// ─────────────────────────────────────────────
// EmptyState
// ─────────────────────────────────────────────

export function EmptyState({
  icon,
  title,
  description,
}: {
  icon: ReactNode;
  title: string;
  description?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="text-dm-muted mb-3">{icon}</div>
      <p className="text-dm-text font-medium">{title}</p>
      {description && <p className="text-dm-muted text-sm mt-1">{description}</p>}
    </div>
  );
}

// ─────────────────────────────────────────────
// Button
// ─────────────────────────────────────────────

export function Button({
  children,
  onClick,
  variant = "primary",
  size = "md",
  disabled = false,
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
  className?: string;
}) {
  const variants = {
    primary: "bg-blue-500 hover:bg-blue-600 text-white",
    secondary: "bg-dm-surface-2 hover:bg-dm-border text-dm-text border border-dm-border",
    danger: "bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30",
    ghost: "hover:bg-dm-surface-2 text-dm-muted hover:text-dm-text",
  };

  const sizes = {
    sm: "px-3 py-1.5 text-xs",
    md: "px-4 py-2 text-sm",
    lg: "px-6 py-3 text-base",
  };

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`
        inline-flex items-center gap-2 rounded-lg font-medium
        transition-all duration-150
        disabled:opacity-50 disabled:cursor-not-allowed
        ${variants[variant]} ${sizes[size]} ${className}
      `}
    >
      {children}
    </button>
  );
}
