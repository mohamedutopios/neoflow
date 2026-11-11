import { useState, type FormEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/auth';
import { MessageErreur } from '../components/MessageErreur';

export function LoginPage() {
  const { connecter } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [login, setLogin] = useState('');
  const [motDePasse, setMotDePasse] = useState('');
  const [erreur, setErreur] = useState<unknown>(null);
  const [envoi, setEnvoi] = useState(false);

  async function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    setErreur(null);
    setEnvoi(true);
    try {
      await connecter(login.trim(), motDePasse);
      const depuis = (location.state as { depuis?: string } | null)?.depuis ?? '/demandes';
      navigate(depuis, { replace: true });
    } catch (e) {
      setErreur(e);
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <section className="carte connexion">
      <h1>Connexion</h1>
      <form onSubmit={soumettre}>
        <label htmlFor="login">Identifiant</label>
        <input id="login" value={login} onChange={(e) => setLogin(e.target.value)} autoComplete="username" required />
        <label htmlFor="motDePasse">Mot de passe</label>
        <input
          id="motDePasse"
          type="password"
          value={motDePasse}
          onChange={(e) => setMotDePasse(e.target.value)}
          autoComplete="current-password"
          required
        />
        <MessageErreur erreur={erreur} />
        <button type="submit" disabled={envoi}>
          Se connecter
        </button>
      </form>
      <p className="aide">Comptes de démonstration : alice, bob, admin.</p>
    </section>
  );
}
