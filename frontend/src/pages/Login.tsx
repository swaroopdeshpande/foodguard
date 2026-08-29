import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../AuthContext";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("manager@foodguard.internal");
  const [password, setPassword] = useState("demo1234");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch (err: any) {
      setError("Login failed — check credentials, or run generate_demo_data.py first.");
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-stone-100">
      <form onSubmit={handleSubmit} className="bg-white shadow-sm border border-stone-200 rounded-lg p-8 w-96">
        <h1 className="text-xl font-semibold mb-1 text-stone-900">FoodGuard</h1>
        <p className="text-sm text-stone-500 mb-6">ML food-safety risk &amp; anomaly detection — local demo</p>

        <label className="block text-sm text-stone-600 mb-1">Email</label>
        <input
          className="w-full border border-stone-300 rounded px-3 py-2 mb-4 text-sm"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <label className="block text-sm text-stone-600 mb-1">Password</label>
        <input
          type="password"
          className="w-full border border-stone-300 rounded px-3 py-2 mb-4 text-sm"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

        <button className="w-full bg-emerald-700 text-white rounded py-2 text-sm font-medium hover:bg-emerald-800">
          Sign in
        </button>

        <p className="text-xs text-stone-400 mt-4">
          Demo accounts (seeded by generate_demo_data.py): admin@foodguard.internal,
          manager@foodguard.internal, kitchen@foodguard.internal — password: demo1234
        </p>
      </form>
    </div>
  );
}
