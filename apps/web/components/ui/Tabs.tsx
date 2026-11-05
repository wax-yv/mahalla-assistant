"use client";

import { createContext, useContext, useId, useRef, type ReactNode } from "react";

export type TabItem<T extends string> = { key: T; label: string; icon?: ReactNode };

type TabCtx = { id: string; active: string };
const TabCtx = createContext<TabCtx>({ id: "tab", active: "" });

/**
 * WAI-ARIA tab pattern (audit P1-11):
 * — role="tablist" / "tab" / "tabpanel"
 * — ro‘lqaror: ← → ↑ ↓ Home End
 * — faol tab tabindex=0, qolganlari -1
 *
 * `children` orqali panellar beriladi — ular `TabPanel` komponenti bilan
 * `<Tabs>...</Tabs>` ichida bo‘lishi shart (ID bog‘lanishi uchun).
 */
export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  ariaLabel,
  children,
}: {
  tabs: ReadonlyArray<TabItem<T>>;
  value: T;
  onChange: (key: T) => void;
  ariaLabel: string;
  children?: ReactNode;
}) {
  const baseId = useId();
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  function focusAt(index: number) {
    const clamped = Math.max(0, Math.min(index, tabs.length - 1));
    onChange(tabs[clamped].key);
    refs.current[clamped]?.focus();
  }

  return (
    <TabCtx.Provider value={{ id: baseId, active: value }}>
      <div className="tabbar" role="tablist" aria-label={ariaLabel}>
        {tabs.map((tab, index) => {
          const selected = tab.key === value;
          return (
            <button
              key={tab.key}
              id={`${baseId}-tab-${tab.key}`}
              ref={(el) => { refs.current[index] = el; }}
              role="tab"
              type="button"
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${tab.key}`}
              tabIndex={selected ? 0 : -1}
              className={selected ? "active" : ""}
              onClick={() => onChange(tab.key)}
              onKeyDown={(e) => {
                if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); focusAt(index + 1); }
                else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); focusAt(index - 1); }
                else if (e.key === "Home") { e.preventDefault(); focusAt(0); }
                else if (e.key === "End") { e.preventDefault(); focusAt(tabs.length - 1); }
              }}
            >
              {tab.icon}
              {tab.label}
            </button>
          );
        })}
      </div>
      {children}
    </TabCtx.Provider>
  );
}

/**
 * Tab panel — `aria-labelledby` bilan bog‘langan.
 *
 * Barcha panellar DOM’da doim turadi; faol bo‘lmagan panel `hidden` bilan
 * yashiriladi. Shu sababli har bir tabning `aria-controls` havolasi har doim
 * mavjud elementga ishora qiladi (WAI-ARIA APG talabi).
 */
export function TabPanel<T extends string>({
  tabKey,
  children,
}: {
  tabKey: T;
  children: ReactNode;
}) {
  const { id, active } = useContext(TabCtx);
  const isActive = active === tabKey;
  return (
    <div
      id={`${id}-panel-${tabKey}`}
      role="tabpanel"
      aria-labelledby={`${id}-tab-${tabKey}`}
      tabIndex={0}
      hidden={!isActive}
    >
      {children}
    </div>
  );
}
