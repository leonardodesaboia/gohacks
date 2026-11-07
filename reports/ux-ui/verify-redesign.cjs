const { chromium } = require('C:/Users/User/AppData/Local/npm-cache/_npx/381cec31605a419a/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const { pathToFileURL } = require('url');
const results = { pages: [], errors: [], checks: [] };
async function capture(page, name) {
  await page.screenshot({ path: path.join(__dirname, name + '.png'), fullPage: true });
  const geometry = await page.evaluate(() => ({
    viewport: innerWidth, width: document.documentElement.scrollWidth,
    heading: document.querySelector('h1')?.innerText,
    evidenceWidths: [...document.querySelectorAll('.sx-campos dd')].filter(el => el.getBoundingClientRect().width).map(el => el.getBoundingClientRect().width),
    controls: [...document.querySelectorAll('button')].filter(el => el.getBoundingClientRect().width && !el.disabled).map(el => {
      const r = el.getBoundingClientRect();
      const x = Math.min(innerWidth - 1, r.x + r.width / 2), y = r.y + r.height / 2;
      return { text: el.innerText, height: r.height, hit: y > 0 && y < innerHeight && r.x >= 0 && r.right <= innerWidth ? el.contains(document.elementFromPoint(x, y)) : null };
    })
  }));
  results.pages.push({ name, ...geometry });
  assert(geometry.width <= geometry.viewport + 1, name + ': page overflows');
}
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Users/User/AppData/Local/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.on('pageerror', e => results.errors.push(e.message));
    await page.goto(pathToFileURL(path.resolve('site/index.html')).href);
    await capture(page, 'after-desktop-initial');
    for (let i = 0; i < 3; i++) await page.locator('#avancar').click();
    await capture(page, 'after-desktop-overview');
    assert.match(await page.locator('.sx-resultado').innerText(), /28 pagamentos/);
    assert.match(await page.locator('.sx-metricas').innerText(), /6 acionamentos confirmados/);
    await page.getByRole('tab', { name: 'Fila do analista', exact: true }).click();
    await page.locator('summary:visible').filter({ hasText: 'Ver evidências' }).first().click();
    await capture(page, 'after-desktop-evidence');
    for (const width of [1024, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      await capture(page, 'after-' + width + '-evidence');
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    for (const [tab, name] of [['Lote de pagamentos', 'batch'], ['Encaminhamentos', 'contacts'], ['Histórico de ações', 'history']]) {
      await page.getByRole('tab', { name: tab, exact: true }).click();
      await capture(page, 'after-desktop-' + name);
    }
    await page.locator('#pre').click();
    await page.getByRole('tab', { name: 'Visão geral', exact: true }).click();
    assert(await page.locator('#avancar').isDisabled());
    assert.match(await page.locator('#painel').innerText(), /Simulação concluída/);
    await page.locator('#reiniciar').click();
    assert(!(await page.locator('#avancar').isDisabled()));
    assert.match(await page.locator('.sx-status').innerText(), /Pronta/);
    await page.getByRole('button', { name: 'Fila inteira no corte', exact: true }).click();
    assert.equal(await page.locator('#pre').innerText(), 'Até o pré-fechamento');
    await page.locator('#pre').click();
    await page.getByRole('tab', { name: 'Encaminhamentos', exact: true }).click();
    assert.match(await page.locator('#painel').innerText(), /Solicitações de aprovação/);
    await page.setViewportSize({ width: 320, height: 900 });
    await capture(page, 'after-mobile-approvals');
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole('tab', { name: 'Visão geral', exact: true }).focus();
    await page.keyboard.press('End');
    assert.equal(await page.getByRole('tab', { selected: true }).innerText(), 'Histórico de ações');
    await page.keyboard.press('Home');
    assert.equal(await page.getByRole('tab', { selected: true }).innerText(), 'Visão geral');
    results.checks.push('Static: both scenarios, all tabs, 320–1440 px, before/after, end/reset, keyboard Home/End. No CSS injected.');
    const live = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    live.on('pageerror', e => results.errors.push(e.message));
    await live.goto('http://127.0.0.1:8513');
    await live.getByRole('heading', { name: 'Conferência de pagamentos', exact: true }).waitFor({ timeout: 60000 });
    await capture(live, 'after-streamlit-initial');
    for (const hour of ['15:00', '16:00', '17:00']) {
      await live.getByRole('button', { name: 'Avançar 1 hora', exact: true }).click();
      await live.waitForFunction(h => document.querySelector('.sx-relogio-num')?.textContent.includes(h), hour);
      await live.locator('[data-testid="stStatusWidget"]').waitFor({ state: 'hidden', timeout: 60000 });
    }
    await capture(live, 'after-streamlit-overview');
    await live.getByRole('tab', { name: 'Fila do analista', exact: true }).click();
    await live.locator('summary:visible').filter({ hasText: 'Ver evidências' }).first().click();
    await live.setViewportSize({ width: 390, height: 844 });
    await capture(live, 'after-streamlit-mobile');
    results.checks.push('Streamlit: initial state, three steps, queue, evidence, mobile.');
    assert.deepEqual(results.errors, []);
    console.log(JSON.stringify({ pages: results.pages.map(({name,viewport,width}) => ({name,viewport,width})), checks: results.checks, errors: results.errors }));
  } finally {
    fs.writeFileSync(path.join(__dirname, 'redesign-verification.json'), JSON.stringify(results, null, 2));
    await browser.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
