import { expect, test, type Page } from '@playwright/test';

const MOT_DE_PASSE = process.env.NEOFLOW_MOT_DE_PASSE ?? 'neoflow';

async function seConnecter(page: Page, login: string) {
  await page.goto('/connexion');
  await page.getByLabel('Identifiant').fill(login);
  await page.getByLabel('Mot de passe').fill(MOT_DE_PASSE);
  await page.getByRole('button', { name: 'Se connecter' }).click();
  await expect(page.getByRole('button', { name: 'Se déconnecter' })).toBeVisible();
}

test('alice crée et soumet une demande générique sans montant, bob la valide', async ({ page }) => {
  const titre = `Demande E2E ${Date.now()}`;
  let urlDemande = '';

  await test.step('alice crée une demande GENERIQUE sans montant', async () => {
    await seConnecter(page, 'alice');
    await page.getByRole('link', { name: 'Nouvelle demande' }).click();
    await page.getByLabel('Type', { exact: true }).selectOption('GENERIQUE');
    await page.getByLabel('Titre', { exact: true }).fill(titre);
    await page.getByLabel('Description', { exact: true }).fill('Demande créée par le test de bout en bout.');
    await page.getByLabel('Date de début').fill('2026-12-01');
    await page.getByRole('button', { name: 'Enregistrer le brouillon' }).click();

    await expect(page.getByRole('heading', { name: titre })).toBeVisible();
    await expect(page.getByTestId('statut')).toHaveAttribute('data-statut', 'BROUILLON');
    urlDemande = page.url();
  });

  await test.step('alice soumet la demande', async () => {
    await page.getByRole('button', { name: 'Soumettre' }).click();
    await expect(page.getByTestId('statut')).toHaveAttribute('data-statut', 'SOUMISE');
  });

  await test.step('bob valide la demande', async () => {
    await page.getByRole('button', { name: 'Se déconnecter' }).click();
    await seConnecter(page, 'bob');
    await page.goto(urlDemande);
    await page.getByRole('button', { name: 'Valider' }).click();
    await expect(page.getByTestId('statut')).toHaveAttribute('data-statut', 'VALIDEE');
    await expect(page.getByText(/VALIDATION par bob/)).toBeVisible();
  });
});
