import { afterEach, describe, expect, it, vi } from 'vitest';

import { api, ApiError, enregistrerIdentifiants } from './client';

function reponseJson(status: number, corps: unknown): Response {
  return new Response(JSON.stringify(corps), {
    status,
    headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' },
  });
}

describe('client API', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('transmet les identifiants Basic et demande la première page par défaut', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      reponseJson(200, { content: [], page: { size: 20, number: 0, totalElements: 0, totalPages: 0 } }),
    );
    vi.stubGlobal('fetch', fetchMock);
    enregistrerIdentifiants('alice', 'neoflow');

    await api.listerDemandes({ statut: 'SOUMISE' });

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/demandes?statut=SOUMISE&page=0&size=20');
    const entetes = new Headers(options.headers);
    expect(entetes.get('Authorization')).toBe(`Basic ${btoa('alice:neoflow')}`);
    expect(entetes.get('X-Requested-With')).toBe('XMLHttpRequest');
  });

  it('traduit un ProblemDetail 422 en ApiError avec la liste des erreurs', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        reponseJson(422, {
          title: 'Règles métier non respectées',
          detail: 'La demande ne respecte pas les règles métier.',
          erreurs: ['La date de fin doit être postérieure ou égale à la date de début'],
        }),
      ),
    );

    const erreur = await api
      .creerDemande({ type: 'GENERIQUE', titre: 'x', dateDebut: '2026-11-10', urgent: false })
      .catch((e: unknown) => e);

    expect(erreur).toBeInstanceOf(ApiError);
    expect((erreur as ApiError).status).toBe(422);
    expect((erreur as ApiError).erreurs).toHaveLength(1);
  });
});
