"use client";

import { useEffect, useState } from "react";

export function applyTheme(theme: "light" | "dark" | "system") {
  const dark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  localStorage.setItem("mahalla-theme", theme);
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark" | "system">("system");
  useEffect(() => {
    setTheme((localStorage.getItem("mahalla-theme") as "light" | "dark" | "system") ?? "system");
  }, []);
  const next = () => {
    const order: Array<"light" | "dark" | "system"> = ["light", "dark", "system"];
    const value = order[(order.indexOf(theme) + 1) % order.length];
    setTheme(value);
    applyTheme(value);
  };
  const icon = theme === "dark" ? "🌙" : theme === "light" ? "☀️" : "🖥️";
  return (
    <button className="btn sm" onClick={next} title="Mavzu: yorug‘ / tungi / tizim" aria-label="Mavzuni almashtirish">
      <span aria-hidden="true">{icon}</span>
      <span className="nowrap">{theme === "system" ? "Tizim" : theme === "dark" ? "Tungi" : "Yorug‘"}</span>
    </button>
  );
}
