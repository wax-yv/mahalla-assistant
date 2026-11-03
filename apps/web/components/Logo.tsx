export function Logo({ size = 34, withText = true }: { size?: number; withText?: boolean }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
      <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true">
        <rect x="2" y="2" width="44" height="44" rx="12" fill="var(--brand)" />
        <path
          d="M24 9 L31 17 H27 V22 H33 V29 H27 V39 H21 V29 H15 V22 H21 V17 H17 Z"
          fill="#fff"
          fillOpacity="0.94"
        />
        <rect x="20.4" y="30.5" width="7.2" height="8.5" rx="1.4" fill="var(--accent)" />
      </svg>
      {withText && (
        <span className="name">
          Mahalla Assistant
          <small>Xorazm · Urganch · Navbahor</small>
        </span>
      )}
    </span>
  );
}
