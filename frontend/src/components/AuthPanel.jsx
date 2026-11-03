import { useState } from 'react';
import api from '../api';

export default function AuthPanel({ user, onAuthenticated }) {
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true); setError('');
    try {
      await api.post(`/api/auth/${register ? 'register' : 'login'}`, Object.fromEntries(form));
      await onAuthenticated();
    } catch (err) { setError(err.response?.data?.error || 'Unable to sign in. Try again.'); }
    finally { setBusy(false); }
  }
  async function logout() {
    setBusy(true); setError('');
    try { await api.post('/api/auth/logout'); await onAuthenticated(); }
    catch { setError('Unable to sign out. Try again.'); }
    finally { setBusy(false); }
  }
  return <section className="card auth" aria-label="Account">
    {user ? <><p>Signed in as <strong>{user.name || user.email}</strong></p><button onClick={logout} disabled={busy}>Sign out</button></> :
      <details><summary>Sign in or create an account</summary>
        <form onSubmit={submit}>
          {register && <label>Name<input name="name" maxLength={100} autoComplete="name" /></label>}
          <label>Email<input name="email" type="email" required maxLength={254} autoComplete="email" /></label>
          <label>Password<input name="password" type="password" required minLength={register ? 10 : undefined} maxLength={72} autoComplete={register ? 'new-password' : 'current-password'} /></label>
          <button type="submit" disabled={busy}>{busy ? 'Please wait…' : register ? 'Create account' : 'Sign in'}</button>
          <button type="button" className="subtle" onClick={() => setRegister(!register)}>{register ? 'Use an existing account' : 'Create an account'}</button>
        </form>
      </details>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
