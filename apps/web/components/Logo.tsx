export function Logo({ size = 32, withText = true, collapsed = false }: { size?: number; withText?: boolean; collapsed?: boolean }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 10, minWidth: 0 }}>
      <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true" style={{ flexShrink: 0 }}>
        <rect x="2" y="2" width="44" height="44" rx="12" fill="var(--brand-700)" />
        <path d="M24 9 L31 17 H27 V22 H33 V29 H27 V39 H21 V29 H15 V22 H21 V17 H17 Z" fill="#fff" fillOpacity="0.94" />
        <rect x="20.4" y="30.5" width="7.2" height="8.5" rx="1.4" fill="var(--brand-900)" />
      </svg>
      {withText && !collapsed && (
        <span style={{ minWidth: 0 }}>
          <span className="name" style={{ display: "block", fontWeight: 650, fontSize: 15.5, lineHeight: 1.15, letterSpacing: "-0.01em", whiteSpace: "nowrap" }}>
            Mahalla Assistant
          </span>
          <span style={{ display: "block", fontSize: 11, color: "var(--color-text-muted)", fontWeight: 500, whiteSpace: "nowrap" }}>
            Xorazm · Urganch · Navbahor
          </span>
        </span>
      )}
    </span>
  );
}
