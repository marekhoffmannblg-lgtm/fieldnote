import { useState, type FormEvent, type ReactNode } from "react";
import { useAuth } from "./AuthProvider";

function AuthShell({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return <main className="flex min-h-screen items-center justify-center bg-background p-4" style={{ fontFamily: "'Inter', sans-serif" }}>
    <section className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-sm" aria-labelledby="auth-title">
      <p className="text-xs font-medium tracking-wide text-primary">FIELDNOTE</p>
      <h1 id="auth-title" className="mt-2 text-lg font-semibold text-foreground">{title}</h1>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      {children}
    </section>
  </main>;
}

export function LoginScreen() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setWorking(true);
    try { await signIn(email, password); } catch (reason) { setError(reason instanceof Error ? reason.message : "Nie udało się zalogować."); } finally { setWorking(false); }
  };
  return <AuthShell title="Zaloguj się" description="Użyj konta utworzonego przez administratora.">
    <form className="mt-6 space-y-4" onSubmit={(event) => void submit(event)}>
      <label className="block text-sm font-medium text-foreground">E-mail<input autoComplete="email" required type="email" value={email} onChange={(event) => setEmail(event.target.value)} className="mt-1 w-full rounded border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30" /></label>
      <label className="block text-sm font-medium text-foreground">Hasło<input autoComplete="current-password" required type="password" value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1 w-full rounded border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30" /></label>
      {error && <p role="alert" className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <button disabled={working} className="w-full rounded bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60">{working ? "Logowanie…" : "Zaloguj"}</button>
    </form>
  </AuthShell>;
}

export function ChangeInitialPasswordScreen() {
  const { changeInitialPassword, signOut } = useAuth();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (password.length < 12) { setError("Hasło musi mieć co najmniej 12 znaków."); return; }
    if (password !== confirmation) { setError("Hasła nie są zgodne."); return; }
    setError(""); setWorking(true);
    try { await changeInitialPassword(password); } catch (reason) { setError(reason instanceof Error ? reason.message : "Nie udało się zmienić hasła."); } finally { setWorking(false); }
  };
  return <AuthShell title="Ustaw nowe hasło" description="Przed użyciem aplikacji musisz zmienić hasło początkowe.">
    <form className="mt-6 space-y-4" onSubmit={(event) => void submit(event)}>
      <label className="block text-sm font-medium text-foreground">Nowe hasło<input autoComplete="new-password" required type="password" value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1 w-full rounded border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30" /></label>
      <label className="block text-sm font-medium text-foreground">Powtórz hasło<input autoComplete="new-password" required type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} className="mt-1 w-full rounded border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30" /></label>
      {error && <p role="alert" className="rounded border border-red-200 bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <button disabled={working} className="w-full rounded bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60">{working ? "Zapisywanie…" : "Zapisz nowe hasło"}</button>
    </form>
    <button onClick={() => void signOut()} className="mt-4 text-sm text-muted-foreground underline hover:text-foreground">Wyloguj</button>
  </AuthShell>;
}

export function AuthLoadingScreen({ error }: { error?: string | null }) {
  return <AuthShell title={error ? "Konfiguracja wymagana" : "Wczytywanie sesji"} description={error || "Sprawdzamy uprawnienia konta."}><p className="mt-6 text-sm text-muted-foreground">{error ? "Skontaktuj się z administratorem środowiska." : "Proszę czekać…"}</p></AuthShell>;
}
