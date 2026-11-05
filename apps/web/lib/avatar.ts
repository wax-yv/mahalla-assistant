const PALETTE = ["avatar-0", "avatar-1", "avatar-2", "avatar-3", "avatar-4", "avatar-5"];

function hash(text: string): number {
  let h = 0;
  for (let i = 0; i < text.length; i += 1) {
    h = (h << 5) - h + text.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h);
}

export function initials(fullName?: string | null): string {
  if (!fullName) return "?";
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export function avatarTone(seed?: string | null): string {
  const key = (seed ?? "").trim();
  if (!key) return PALETTE[0];
  return PALETTE[hash(key) % PALETTE.length];
}

export function avatar(seed?: string | null, fullName?: string | null, large = false): {
  className: string;
  text: string;
} {
  return {
    className: `avatar ${avatarTone(seed ?? fullName)}${large ? " avatar-lg" : ""}`,
    text: initials(fullName),
  };
}
