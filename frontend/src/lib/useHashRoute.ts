import { useCallback, useEffect, useState } from "react";

function normalize(route: string): string {
  if (route === "workflow/") {
    return "workflow";
  }
  return route.replace(/\/$/, "");
}

export function parseHashRoute(): string {
  const raw = window.location.hash.replace(/^#\/?/, "").trim();
  return normalize(raw);
}

function routeToHash(route: string): string {
  return `#/${normalize(route)}`;
}

export interface MatchResult {
  name: string;
  params: Record<string, string>;
  query: string;
}

export function matchRoute(route: string, pattern: string): MatchResult | null {
  const patternSegments = pattern.split("/").filter(Boolean);
  const routeSegments = route.split("/").filter(Boolean);
  if (patternSegments.length !== routeSegments.length) {
    return null;
  }
  const params: Record<string, string> = {};
  for (let index = 0; index < patternSegments.length; index += 1) {
    const patternSegment = patternSegments[index];
    if (patternSegment.startsWith(":")) {
      params[patternSegment.slice(1)] = routeSegments[index];
    } else if (patternSegment !== routeSegments[index]) {
      return null;
    }
  }
  const queryIndex = route.indexOf("?");
  const query = queryIndex >= 0 ? route.slice(queryIndex) : "";
  return { name: pattern, params, query };
}

/** Minimal hash router: returns the current route and re-renders on #r changes. */
export function useHashRoute(): string {
  const [route, setRoute] = useState<string>(() => parseHashRoute());

  const handleHashChange = useCallback(() => {
    setRoute(parseHashRoute());
  }, []);

  useEffect(() => {
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, [handleHashChange]);

  return route;
}

export function navigate(route: string) {
  if (parseHashRoute() === normalize(route)) {
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  } else {
    window.location.hash = routeToHash(route);
  }
}

export function navigateParam(route: string) {
  window.location.hash = routeToHash(route);
}