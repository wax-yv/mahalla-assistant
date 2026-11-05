"use client";

import { useEffect, useState } from "react";
import { Field } from "@/components/ui/inputs";
import { useToast } from "@/components/ui/overlays";
import { api } from "@/lib/api";

export type CitizenFormData = {
  id?: string;
  version?: number;
  full_name: string;
  gender: "Erkak" | "Ayol";
  birth_date: string;
  phone: string;
  family_id: string;
  family_role: string;
  education: string;
  employment_status: string;
  profession: string;
  social_status: string;
  needs: string;
  notes: string;
};

export const EMPTY_CITIZEN: CitizenFormData = {
  full_name: "", gender: "Erkak", birth_date: "", phone: "", family_id: "",
  family_role: "Farzand", education: "O‘rta", employment_status: "Ishlamaydi",
  profession: "Yo‘q", social_status: "Yo‘q", needs: "", notes: "",
};

const EDUCATION = ["Boshlang‘ich", "O‘rta", "O‘rta maxsus", "Oliy", "Yo‘q"];
const EMPLOYMENT = ["Ishlaydi", "Ishsiz", "Tadbirkor", "Pensioner", "O'qiydi", "Ishlamaydi"];
const ROLES = ["Ota", "Ona", "O‘g‘li", "Qizi", "Farzand", "Bobo", "Buvi", "Aka", "Uka", "Opa", "Singil", "Turmush o‘rtoq"];
const SOCIAL = [
  "Yo‘q", "Temir daftar", "Ko‘p bolali oila", "Yoshlar daftari", "Ayollar daftari",
  "Kam ta’minlangan oila", "Nogironligi bor (I guruh)", "Nogironligi bor (II guruh)",
  "Nogironligi bor (III guruh)", "Mehnat faxriysi", "Ijtimoiy himoyaga muhtoj", "To‘liq bo‘lmagan oila",
];

export function CitizenForm({
  open, onClose, initial, onSaved,
}: {
  open: boolean; onClose: () => void; initial?: Partial<CitizenFormData> | null; onSaved: (id: string) => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState<CitizenFormData>({ ...EMPTY_CITIZEN, ...initial });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isEdit = Boolean(initial?.id);
  const set = (patch: Partial<CitizenFormData>) => setForm((f) => ({ ...f, ...patch }));

  useEffect(() => {
    setForm({ ...EMPTY_CITIZEN, ...initial });
    setError("");
  }, [initial, open]);

  function validate(): string | null {
    if (form.full_name.trim().length < 3) return "F.I.Sh. kamida 3 belgidan iborat bo‘lishi kerak.";
    return null;
  }

  async function submit() {
    const problem = validate();
    if (problem) { setError(problem); return; }
    if (isEdit && typeof initial?.version !== "number") {
      setError("Yozuv versiyasi topilmadi. Sahifani yangilab qayta urinib ko‘ring.");
      return;
    }
    setBusy(true);
    setError("");
    const payload = {
      full_name: form.full_name.trim(),
      gender: form.gender,
      birth_date: form.birth_date || null,
      phone: form.phone.trim(),
      family_id: form.family_id || null,
      family_role: form.family_role,
      education: form.education,
      employment_status: form.employment_status,
      profession: form.profession || "Yo‘q",
      social_status: form.social_status || "Yo‘q",
      needs: form.needs.split(",").map((n) => n.trim()).filter(Boolean),
      notes: form.notes,
      ...(isEdit ? { version: initial!.version as number } : {}),
    };
    try {
      const saved = isEdit
        ? await api.patch<{ id: string }>(`/citizens/${initial!.id}`, payload)
        : await api.post<{ id: string }>("/citizens", payload);
      toast.show("success", isEdit ? "Fuqaro ma’lumotlari yangilandi." : "Yangi fuqaro qo‘shildi.");
      onSaved(saved.id);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Saqlash amalga oshmadi.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {error && <div className="alert danger" role="alert">{error}</div>}
      <div className="grid grid-2">
        <Field label="F.I.Sh." required htmlFor="cf-name">
          <input id="cf-name" className="input" value={form.full_name} onChange={(e) => set({ full_name: e.target.value })} />
        </Field>
        <Field label="Jinsi" required htmlFor="cf-gender">
          <select id="cf-gender" className="select" value={form.gender} onChange={(e) => set({ gender: e.target.value as "Erkak" | "Ayol" })}>
            <option>Erkak</option><option>Ayol</option>
          </select>
        </Field>
        <Field label="Tug‘ilgan sana" htmlFor="cf-birth">
          <input id="cf-birth" type="date" className="input" value={form.birth_date} onChange={(e) => set({ birth_date: e.target.value })} />
        </Field>
        <Field label="Telefon" hint="+998 XX XXX XX XX" htmlFor="cf-phone">
          <input id="cf-phone" className="input" value={form.phone} onChange={(e) => set({ phone: e.target.value })} placeholder="+998" />
        </Field>
        <Field label="Oiladagi o‘rni" htmlFor="cf-role">
          <select id="cf-role" className="select" value={form.family_role} onChange={(e) => set({ family_role: e.target.value })}>
            {ROLES.map((r) => <option key={r}>{r}</option>)}
          </select>
        </Field>
        <Field label="Oila ID (ixtiyoriy)" htmlFor="cf-family">
          <input id="cf-family" className="input mono" value={form.family_id} onChange={(e) => set({ family_id: e.target.value })} placeholder="OIL-0001" />
        </Field>
        <Field label="Ma’lumoti" htmlFor="cf-edu">
          <select id="cf-edu" className="select" value={form.education} onChange={(e) => set({ education: e.target.value })}>
            {EDUCATION.map((r) => <option key={r}>{r}</option>)}
          </select>
        </Field>
        <Field label="Bandligi" htmlFor="cf-emp">
          <select id="cf-emp" className="select" value={form.employment_status} onChange={(e) => set({ employment_status: e.target.value })}>
            {EMPLOYMENT.map((r) => <option key={r}>{r}</option>)}
          </select>
        </Field>
        <Field label="Kasbi" htmlFor="cf-prof">
          <input id="cf-prof" className="input" value={form.profession} onChange={(e) => set({ profession: e.target.value })} />
        </Field>
        <Field label="Ijtimoiy holati" htmlFor="cf-social">
          <select id="cf-social" className="select" value={form.social_status} onChange={(e) => set({ social_status: e.target.value })}>
            {SOCIAL.map((r) => <option key={r}>{r}</option>)}
          </select>
        </Field>
      </div>
      <Field label="Ehtiyojlari (vergul bilan)" htmlFor="cf-needs" hint="Masalan: Ish, Moddiy yordam">
        <input id="cf-needs" className="input" value={form.needs} onChange={(e) => set({ needs: e.target.value })} />
      </Field>
      <Field label="Izoh" htmlFor="cf-notes">
        <textarea id="cf-notes" className="textarea" rows={2} value={form.notes} onChange={(e) => set({ notes: e.target.value })} />
      </Field>
      <div className="row-end mt">
        <button className="btn ghost" onClick={onClose} disabled={busy}>Bekor qilish</button>
        <button className="btn primary" onClick={() => void submit()} disabled={busy}>
          {busy ? "Saqlanmoqda…" : isEdit ? "O‘zgarishlarni saqlash" : "Fuqaroni qo‘shish"}
        </button>
      </div>
    </>
  );
}
