"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { getMe, login } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (getMe()) router.replace("/dashboard");
  }, [router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(username.trim(), password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kirish amalga oshmadi.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-side">
        <div>
          <Logo withText={false} size={44} />
          <h1 className="mt">Mahalla ishini bitta oynadan boshqaring</h1>
          <p>
            Fuqarolar bazasi, murojaatlar va vazifalar nazorati, kunlik hisobotlar, Lex.uz
            qonunchiligi va kredit-subsidiya maslahatlari — barchasi bir tizimda.
          </p>
          <div className="points">
            <div>
              <b>✦</b>
              <span>AI agentlar o‘zbek lotin tilida manbali javob beradi, har bir amal tasdiqingiz bilan bajariladi.</span>
            </div>
            <div>
              <b>§</b>
              <span>Qonunchilik bo‘limi Lex.uz dan jonli sinxronlanadi va manba bilan ko‘rsatadi.</span>
            </div>
            <div>
              <b>▤</b>
              <span>Kunlik, haftalik va oylik hisobotlar SQL ko‘rsatkichlaridan avtomatik shakllanadi.</span>
            </div>
          </div>
        </div>
        <div style={{ fontSize: 13, color: "#b9d5c6" }}>
          Demo: Xorazm viloyati, Urganch shahri, Navbahor mahallasi
        </div>
      </div>
      <div className="auth-card">
        <div className="auth-box">
          <div className="logo-row">
            <Logo />
            <span style={{ flex: 1 }} />
            <ThemeToggle />
          </div>
          <h1>Tizimga kirish</h1>
          <p className="sub">Login va parolingizni kiriting.</p>
          {error && <div className="alert danger">⚠️ {error}</div>}
          <form onSubmit={submit}>
            <div className="field">
              <label htmlFor="username">Login</label>
              <input
                id="username"
                className="input"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                required
                minLength={2}
              />
            </div>
            <div className="field">
              <label htmlFor="password">Parol</label>
              <input
                id="password"
                type="password"
                className="input"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                required
                minLength={2}
              />
            </div>
            <button className="btn primary" style={{ width: "100%" }} disabled={busy}>
              {busy ? "Kirilmoqda…" : "Kirish"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
