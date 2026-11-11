import { ApiError } from '../api/client';

export function MessageErreur({ erreur }: { erreur: unknown }) {
  if (!erreur) return null;
  const message = erreur instanceof Error ? erreur.message : String(erreur);
  const details = erreur instanceof ApiError ? erreur.erreurs : [];
  return (
    <div role="alert" className="alerte">
      <p>{message}</p>
      {details.length > 0 && (
        <ul>
          {details.map((detail) => (
            <li key={detail}>{detail}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
