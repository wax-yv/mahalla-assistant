import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Mahalla Assistant — Navbahor mahallasi",
    short_name: "Mahalla Assistant",
    description:
      "Fuqarolar bazasi, murojaatlar, vazifalar nazorati, hisobotlar, qonunchilik va AI agentlar — bitta tizimda.",
    id: "/dashboard",
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    orientation: "portrait-primary",
    background_color: "#F5F6F3",
    theme_color: "#1E5B47",
    lang: "uz",
    dir: "ltr",
    categories: ["government", "productivity"],
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Boshqaruv paneli", short_name: "Panel", url: "/dashboard" },
      { name: "Fuqarolar", short_name: "Fuqarolar", url: "/citizens" },
      { name: "Murojaatlar", short_name: "Murojaatlar", url: "/cases" },
      { name: "Suhbat", short_name: "Suhbat", url: "/chat" },
    ],
  };
}
