import { useState, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../lib/AuthContext';
import AuthFrame from '../components/AuthFrame';
import { authErrorMessage } from '../lib/auth-error';
export default function Login() {
    const { login } = useAuth();
    const navigate = useNavigate();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const handleSubmit = async (e: FormEvent) => {
        e.preventDefault();
        if (!email.trim() || !password) {
            setError('Email and password are required');
            return;
        }
        setError('');
        setSubmitting(true);
        try {
            await login(email.trim(), password);
            navigate('/', { replace: true });
        }
        catch (err) {
            setError(authErrorMessage(err, 'Login failed'));
        }
        finally {
            setSubmitting(false);
        }
    };
    return (<AuthFrame title="Welcome back." subtitle="Sign in and pick up where you left off.">
        <form onSubmit={handleSubmit} className="auth-form space-y-5">
          <div>
            <label htmlFor="email" className="auth-label">
              Email
            </label>
            <input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="your@email.com" required className="auth-input"/>
          </div>

          <div>
            <label htmlFor="password" className="auth-label">
              Password
            </label>
            <input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢" required className="auth-input"/>
          </div>

          {error && (<div role="alert" className="auth-error">
              {error}
            </div>)}

          <button type="submit" disabled={submitting} className="primary-button w-full">
            {submitting && (<svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
              </svg>)}
            {submitting ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <p className="text-center mt-4 text-sm muted">
          Don't have an account?{' '}
          <Link to="/register" className="accent hover:underline">
            Register
          </Link>
        </p>
        <p className="text-center mt-2 text-xs muted">
          Connect your Naukri or LinkedIn account after signing in.
        </p>
    </AuthFrame>);
}
