import { makeBadge } from "@/features/procurement/StatusBadges";

export const SeverityBadge = makeBadge({
  low: ["secondary", "Low"],
  medium: ["default", "Medium"],
  high: ["warning", "High"],
  critical: ["destructive", "Critical"],
});

export const IssueStatusBadge = makeBadge({
  open: ["warning", "Open"],
  resolved: ["success", "Resolved"],
});

export const WeatherBadge = makeBadge({
  sunny: ["outline", "☀ Sunny"],
  cloudy: ["outline", "☁ Cloudy"],
  rain: ["secondary", "🌧 Rain"],
  storm: ["destructive", "⛈ Storm"],
});
