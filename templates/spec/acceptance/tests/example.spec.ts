// Example to replace: spec story s001, criteria AC1 (@main) and AC2 (@ext-2a).
// Title: a plain sentence, then @<id> and one @<id>-ac<n> per criterion covered.
// Locators: getByRole, getByLabel, getByText with copy('<key>'); data only through the UI.
import { test, expect } from '@playwright/test';
import { copy } from '../copy';

test.describe('s001 : Créer une liste', () => {
  test.beforeEach(async ({ page, request }) => {
    expect((await request.post('/__test__/reset')).ok()).toBeTruthy();
    expect((await request.post('/__test__/users', { data: { name: 'alice' } })).ok()).toBeTruthy();
    await page.goto('/__test__/login-as/alice');
  });

  test('la liste créée apparaît dans mes listes @s001 @s001-ac1', async ({ page }) => {
    await page.getByRole('button', { name: copy('lists.create') }).click();
    await page.getByLabel(copy('lists.name')).fill('Courses');
    await page.getByRole('button', { name: copy('lists.save') }).click();
    await expect(page.getByRole('listitem').filter({ hasText: 'Courses' })).toBeVisible();
  });

  test('un nom vide est refusé et rien n’est créé @s001 @s001-ac2', async ({ page }) => {
    await page.getByRole('button', { name: copy('lists.create') }).click();
    await page.getByRole('button', { name: copy('lists.save') }).click();
    await expect(page.getByText(copy('lists.name-required'))).toBeVisible();
    await expect(page.getByRole('listitem')).toHaveCount(0);
  });
});
