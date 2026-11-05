"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { Eye, EyeOff, LoaderCircle, ShieldCheck } from "@/components/ui/icons";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { getMe, login } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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
      <div className="auth-side" aria-hidden="true">
        <div>
          <Logo withText={false} size={42} />
          <h1 className="mt">Mahalla ishini bitta oynadan boshqaring</h1>
          <p>
            Fuqarolar bazasi, murojaatlar, vazifalar nazorati, hisobotlar, Lex.uz qonunchiligi va
            kredit-subsidiya dasturlari — barchasi bir tizimda.
          </p>
          <div className="points">
            <div><ShieldCheck size={17} style={{ flexShrink: 0, marginTop: 2 }} /><span>AI agentlar o‘zbek lotin tilida manbali javob beradi; har bir yozuv amali tasdiqingiz bilan bajariladi.</span></div>
            <div><ShieldCheck size={17} style={{ flexShrink: 0, marginTop: 2 }} /><span>Qonunchilik bo‘limi Lex.uz dan jonli sinxronlanadi va manbali javob qaytaradi.</span></div>
            <div><ShieldCheck size={17} style={{ flexShrink: 0, marginTop: 2 }} /><span>Hisobotlar SQL ko‘rsatkichlaridan avtomatik shakllanadi, draft tasdiq bilan rasmiylashadi.</span></div>
          </div>
        </div>
        <div className="foot-note">Xorazm viloyati, Urganch shahri, Navbahor mahallasi</div>
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
          {error && (
            <div className="alert danger" role="alert">
              <ShieldCheck size={16} />
              <span>{error}</span>
            </div>
          )}
          <form onSubmit={submit} noValidate={false}>
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
                autoFocus
              />
            </div>
            <div className="field">
              <label htmlFor="password">Parol</label>
              <div style={{ position: "relative" }}>
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  className="input"
                  style={{ paddingRight: 44 }}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  required
                  minLength={2}
                />
                <button
                  type="button"
                  className="icon-btn"
                  style={{ position: "absolute", right: 6, top: 5 }}
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Parolni yashirish" : "Parolni ko‘rsatish"}
                  title={showPassword ? "Parolni yashirish" : "Parolni ko‘rsatish"}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>
            <button className="btn primary lg" style={{ width: "100%" }} disabled={busy || !username.trim() || !password}>
              {busy ? (
                <>
                  <LoaderCircle size={16} className="spin" /> Kirilmoqda…
                </>
              ) : (
                "Kirish"
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
