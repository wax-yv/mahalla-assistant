"use client";

export type EmptyArtKind = "search" | "document" | "task" | "inbox" | "chart";

export function EmptyArt({ kind = "search" }: { kind?: EmptyArtKind }) {
  return (
    <svg className="empty-art" viewBox="0 0 96 96" role="presentation" aria-hidden="true">
      <circle className="art-fill" cx="48" cy="48" r="42" />
      {kind === "search" && (
        <>
          <circle className="art-line" cx="43" cy="42" r="17" />
          <path className="art-line" d="M56 55 L69 68" />
          <path className="art-line-soft" d="M34 40 h18 M34 47 h12" />
        </>
      )}
      {kind === "document" && (
        <>
          <path className="art-line" d="M32 24 h20 l12 12 v36 H32 Z" />
          <path className="art-line" d="M52 24 v12 h12" />
          <path className="art-line-soft" d="M39 47 h18 M39 54 h18 M39 61 h11" />
        </>
      )}
      {kind === "task" && (
        <>
          <rect className="art-line" x="27" y="26" width="42" height="44" rx="6" />
          <path className="art-line" d="M35 41 l5 5 9-10" />
          <path className="art-line-soft" d="M35 58 h26 M35 64 h17" />
        </>
      )}
      {kind === "inbox" && (
        <>
          <path className="art-line" d="M26 46 l8-20 h28 l8 20 v22 H26 Z" />
          <path className="art-line" d="M26 46 h14 l4 8 h8 l4-8 h14" />
          <path className="art-line-soft" d="M39 36 h18" />
        </>
      )}
      {kind === "chart" && (
        <>
          <path className="art-line" d="M27 67 V33 M27 67 h42" />
          <rect className="art-accent" x="34" y="48" width="8" height="19" rx="2" />
          <rect className="art-accent" x="46" y="38" width="8" height="29" rx="2" />
          <rect className="art-accent" x="58" y="52" width="8" height="15" rx="2" />
        </>
      )}
    </svg>
  );
}
