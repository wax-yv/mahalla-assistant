/**
 * Davlat uslubidagi gerb belgisi (audit P0-1 / 3.4).
 * 48×48 doira: o‘zbek naqshi (kumush qator chiziqlar + quyosh), atrofida ingichka halqa.
 * Matn: “MAHALLA ASSISTANT” + “Raqamli davlat boshqaruvi”.
 */
export function Logo({
  size = 32,
  withText = true,
  collapsed = false,
  subtitle = "Raqamli davlat boshqaruvi",
}: {
  size?: number;
  withText?: boolean;
  collapsed?: boolean;
  subtitle?: string;
}) {
  return (
    <span className="logo-wrap">
      <svg
        width={size}
        height={size}
        viewBox="0 0 48 48"
        fill="none"
        aria-hidden="true"
        className="logo-mark"
      >
        <circle cx="24" cy="24" r="22.5" fill="var(--brand-800)" />
        <circle cx="24" cy="24" r="22.5" stroke="var(--brand-400)" strokeWidth="1.5" />
        <circle cx="24" cy="24" r="18" stroke="var(--brand-500)" strokeWidth="1" strokeDasharray="2 3" />
        {/* Quyosh — markazda */}
        <path
          d="M24 9.5c1.6 2.1 4.2 3.3 4.2 6.1 0 1.9-1.2 3.3-2.6 4.2h3.9v8.4h-4.3v6.3h-2.4v-6.3h-4.3v-8.4h3.9c-1.4-.9-2.6-2.3-2.6-4.2 0-2.8 2.6-4 4.2-6.1Z"
          fill="#FFFFFF"
          fillOpacity="0.95"
        />
        {/* Kumush qator chiziqlar */}
        <path d="M12 33.5h24" stroke="var(--brand-300)" strokeWidth="1.6" strokeLinecap="round" />
        <path d="M14.5 36.8h19" stroke="var(--brand-400)" strokeWidth="1.4" strokeLinecap="round" />
        <path d="M17 40h14" stroke="var(--brand-500)" strokeWidth="1.2" strokeLinecap="round" />
      </svg>
      {withText && !collapsed && (
        <span className="logo-text">
          <span className="name">MAHALLA ASSISTANT</span>
          <span className="sub">{subtitle}</span>
        </span>
      )}
    </span>
  );
}
