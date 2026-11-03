"use client";

import { useEffect, useMemo, useState } from "react";
import { Badge, Empty, ErrorNote, Loading, PageHead } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";

type Program = {
  id: string;
  name: string;
  type: string;
  organization: string;
  target_group: string;
  amount: string;
  interest_rate: string;
  term_months: string;
  grace_period: string;
  required_documents: string[];
  application_channel: string;
  official_url: string;
  last_verified_at: string | null;
  status: string;
  notes: string;
};

const TYPE_LABELS: Record<string, { label: string; tone: string }> = {
  credit: { label: "Kredit", tone: "brand" },
  subsidy: { label: "Subsidiya", tone: "ok" },
  benefit: { label: "Ijtimoiy yordam", tone: "info" },
  grant: { label: "Grant", tone: "warn" },
};

export default function ProgramsPage() {
  const [programs, setPrograms] = useState<Program[] | null>(null);
  const [error, setError] = useState("");
  const [org, setOrg] = useState("");
  const [type, setType] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [citizenId, setCitizenId] = useState("");
  const [matches, setMatches] = useState<{ program_name: string; result: string; reasons: string[]; missing_fields: string[] }[] | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get<{ items: Program[] }>("/programs")
      .then((data) => setPrograms(data.items))
      .catch((err) => setError(err instanceof Error ? err.message : "Xatolik"));
  }, []);

  const organizations = useMemo(
    () => Array.from(new Set((programs ?? []).map((program) => program.organization))).sort(),
    [programs]
  );

  const filtered = (programs ?? []).filter(
    (program) =>
      (!org || program.organization === org) &&
      (!type || program.type === type)
  );

  async function match() {
    if (!citizenId.trim()) {
      setError("Fuqaro ID kiriting (masalan F-00001).");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await api.post<{ items: typeof matches }>("/programs/match", { citizen_id: citizenId.trim() });
      setMatches(result.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Moslik hisoblanmadi.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead
        kicker="Kredit va subsidiya"
        title="Davlat dasturlari katalogi"
        lede="Dastur shartlari, zarur hujjatlar va rasmiy manbalar. AI assistent faqat foydalanuvchi tanlagan bank bo‘yicha ma'lumot beradi."
      />
      {error && <ErrorNote message={error} />}
      <div className="filters">
        <select className="select" value={org} onChange={(e) => setOrg(e.target.value)}>
          <option value="">Tashkilot — barchasi</option>
          {organizations.map((item) => (
            <option key={item}>{item}</option>
          ))}
        </select>
        <select className="select" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">Tur — barchasi</option>
          <option value="credit">Kredit</option>
          <option value="subsidy">Subsidiya</option>
          <option value="benefit">Ijtimoiy yordam</option>
          <option value="grant">Grant</option>
        </select>
      </div>

      <div className="card card-pad mb">
        <h3 className="mb">Fuqaro bo‘yicha moslik tekshiruvi</h3>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            className="input"
            style={{ maxWidth: 260 }}
            placeholder="Fuqaro ID, masalan F-00001"
            value={citizenId}
            onChange={(e) => setCitizenId(e.target.value)}
          />
          <button className="btn primary" disabled={busy} onClick={match}>
            Tekshirish
          </button>
        </div>
        {matches && (
          <div className="table-wrap mt">
            <table className="data">
              <thead>
                <tr>
                  <th>Dastur</th>
                  <th>Natija</th>
                  <th>Asos</th>
                </tr>
              </thead>
              <tbody>
                {matches.map((match) => (
                  <tr key={match.program_name}>
                    <td>{match.program_name}</td>
                    <td>
                      <Badge tone={match.result === "mos kelishi mumkin" ? "ok" : match.result === "mos kelmaydi" ? "danger" : "warn"}>
                        {match.result}
                      </Badge>
                    </td>
                    <td className="text-soft">
                      {match.reasons.slice(0, 2).join(" ")}
                      {match.missing_fields.length > 0 && ` · yetishmaydi: ${match.missing_fields.join(", ")}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {!programs && !error && <Loading />}
      <div className="grid grid-2">
        {filtered.map((program) => {
          const meta = TYPE_LABELS[program.type] ?? { label: program.type, tone: "muted" };
          return (
            <div className="card card-pad" key={program.id}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "flex-start" }}>
                <h3>{program.name}</h3>
                <Badge tone={meta.tone}>{meta.label}</Badge>
              </div>
              <p className="text-soft mt">{program.organization} · {program.target_group}</p>
              <dl className="kv mt">
                <dt>Summa</dt>
                <dd>{program.amount}</dd>
                <dt>Stavka</dt>
                <dd>{program.interest_rate}</dd>
                <dt>Muddat</dt>
                <dd>{program.term_months} · imtiyozli davr: {program.grace_period}</dd>
                <dt>Hujjatlar</dt>
                <dd>{program.required_documents.join(", ")}</dd>
                <dt>Ariza</dt>
                <dd>{program.application_channel}</dd>
                <dt>Oxirgi tekshiruv</dt>
                <dd>{fmtDate(program.last_verified_at)}</dd>
              </dl>
              <div className="mt" style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                {program.official_url && (
                  <a className="link" href={program.official_url} target="_blank" rel="noreferrer">
                    Rasmiy manba ↗
                  </a>
                )}
                <button
                  className="btn sm"
                  onClick={() =>
                    setSelected((prev) =>
                      prev.includes(program.id) ? prev.filter((id) => id !== program.id) : [...prev, program.id]
                    )
                  }
                >
                  {selected.includes(program.id) ? "✓ Tanlangan" : "Taqqoslashga qo‘shish"}
                </button>
              </div>
              <p className="text-faint mt" style={{ fontSize: 12.5 }}>
                {program.notes}
              </p>
            </div>
          );
        })}
        {programs && filtered.length === 0 && <Empty title="Dastur topilmadi" icon="₴" />}
      </div>

      {selected.length > 1 && (
        <div className="card mt">
          <div className="card-head">
            <h3>Taqqoslash ({selected.length})</h3>
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Parametr</th>
                  {selected.map((id) => (
                    <th key={id}>{programs?.find((p) => p.id === id)?.name.slice(0, 40)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(
                  [
                    ["Tashkilot", (p: Program) => p.organization],
                    ["Summa", (p: Program) => p.amount],
                    ["Stavka", (p: Program) => p.interest_rate],
                    ["Muddat", (p: Program) => p.term_months],
                    ["Imtiyozli davr", (p: Program) => p.grace_period],
                    ["Ariza kanali", (p: Program) => p.application_channel],
                  ] as const
                ).map(([label, getter]) => (
                  <tr key={label}>
                    <td className="text-faint">{label}</td>
                    {selected.map((id) => {
                      const program = programs?.find((p) => p.id === id);
                      return <td key={id}>{program ? getter(program) : "—"}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
