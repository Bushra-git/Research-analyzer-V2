import { useState } from "react";
import axios from "axios";

const USER_STORAGE_KEY = "research_analyzer_user";

function readStoredUser() {
  try {
    const raw = localStorage.getItem(USER_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (error) {
    return null;
  }
}

function AuthPanel({ apiBaseUrl, onAuthenticated, guestAnalysesUsed = 0, guestAnalyzeLimit = 2 }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [currentUser, setCurrentUser] = useState(readStoredUser);
  const hasSession = Boolean(localStorage.getItem("research_analyzer_token"));

  const submit = async (event) => {
    event.preventDefault();
    setMessage("");
    setLoading(true);

    try {
      const endpoint = mode === "login" ? "login" : "register";
      const response = await axios.post(`${apiBaseUrl}/api/auth/${endpoint}`, {
        email,
        password,
        ...(mode === "register" ? { name } : {}),
      });
      localStorage.setItem("research_analyzer_token", response.data.token);
      localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(response.data.user));
      setCurrentUser(response.data.user);
      onAuthenticated(response.data.user);
      setEmail("");
      setPassword("");
      setName("");
    } catch (error) {
      setMessage(error.response?.data?.error || "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  const signOut = () => {
    localStorage.removeItem("research_analyzer_token");
    localStorage.removeItem(USER_STORAGE_KEY);
    setCurrentUser(null);
    onAuthenticated(null);
    setMessage("Signed out");
  };

  // Once logged in, show a welcome message instead of the sign-in form
  if (hasSession && currentUser) {
    const displayName = currentUser.name || currentUser.email;

    return (
      <div style={styles.wrap}>
        <div style={styles.welcomeBox}>
          <div style={styles.welcomeGreeting}>Welcome, {displayName} 👋</div>
          <div style={styles.welcomeEmail}>{currentUser.email}</div>
        </div>

        <button type="button" onClick={signOut} style={styles.signOutButton}>
          Sign out
        </button>

        {message && <small style={styles.message}>{message}</small>}
      </div>
    );
  }

  return (
    <div style={styles.wrap}>
      <div style={styles.note}>
        Guest access includes {guestAnalyzeLimit} free analyses. Used: {Math.min(guestAnalysesUsed, guestAnalyzeLimit)}/{guestAnalyzeLimit}
      </div>

      <form onSubmit={submit} style={styles.form}>
        <strong style={styles.title}>{mode === "login" ? "Sign in" : "Create account"}</strong>

        {mode === "register" && (
          <input
            aria-label="Name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Name"
            style={styles.input}
          />
        )}

        <input
          aria-label="Email"
          type="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="Email"
          style={styles.input}
        />

        <input
          aria-label="Password"
          type="password"
          required
          minLength={10}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Password (10+ characters)"
          style={styles.input}
        />

        <button type="submit" disabled={loading} style={styles.primaryButton}>
          {loading ? "Please wait..." : mode === "login" ? "Sign in" : "Register"}
        </button>

        <button type="button" onClick={() => setMode(mode === "login" ? "register" : "login")} style={styles.ghostButton}>
          {mode === "login" ? "Need an account? Register" : "Already registered? Sign in"}
        </button>

        {message && <small style={styles.message}>{message}</small>}
      </form>
    </div>
  );
}

const styles = {
  wrap: {
    marginTop: "12px",
  },
  note: {
    marginBottom: "10px",
    padding: "8px 10px",
    borderRadius: "8px",
    fontSize: "12px",
    fontWeight: "600",
    color: "#334155",
    background: "#f8fafc",
    border: "1px solid rgba(148, 163, 184, 0.35)",
  },
  welcomeBox: {
    padding: "14px 16px",
    borderRadius: "10px",
    background: "linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0%, rgba(37, 99, 235, 0.08) 100%)",
    border: "1px solid rgba(59, 130, 246, 0.25)",
    marginBottom: "10px",
  },
  welcomeGreeting: {
    fontSize: "15px",
    fontWeight: "700",
    color: "#1e293b",
    marginBottom: "4px",
  },
  welcomeEmail: {
    fontSize: "12px",
    color: "#64748b",
    fontWeight: "500",
  },
  form: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
  },
  title: {
    fontSize: "13px",
    color: "#0f172a",
    marginBottom: "2px",
  },
  input: {
    width: "100%",
    border: "1px solid #cbd5e1",
    borderRadius: "8px",
    padding: "8px 10px",
    fontSize: "13px",
    outline: "none",
    boxSizing: "border-box",
  },
  primaryButton: {
    width: "100%",
    border: "none",
    borderRadius: "8px",
    padding: "9px 10px",
    fontSize: "13px",
    fontWeight: "700",
    color: "#ffffff",
    background: "#0f172a",
    cursor: "pointer",
  },
  ghostButton: {
    width: "100%",
    border: "1px solid #cbd5e1",
    borderRadius: "8px",
    padding: "9px 10px",
    fontSize: "12px",
    fontWeight: "600",
    color: "#334155",
    background: "#ffffff",
    cursor: "pointer",
  },
  signOutButton: {
    width: "100%",
    border: "1px solid #fecaca",
    borderRadius: "8px",
    padding: "9px 10px",
    fontSize: "12px",
    fontWeight: "600",
    color: "#b91c1c",
    background: "#fff1f2",
    cursor: "pointer",
  },
  message: {
    display: "block",
    marginTop: "2px",
    fontSize: "12px",
    color: "#475569",
    textAlign: "center",
  },
};

export default AuthPanel;
