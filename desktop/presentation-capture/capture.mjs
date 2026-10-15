import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

const output = path.resolve('desktop/presentation-capture/artifacts');
const sha = process.env.GITHUB_SHA || 'local';
const readmeUrl = `https://github.com/megasoft1978/bytepleat/blob/${sha}/README.md`;
const websiteUrl = 'http://127.0.0.1:4173/';
await fs.mkdir(output, { recursive: true });

const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
try {
  const website = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  await website.goto(websiteUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await website.waitForTimeout(1000);
  await website.screenshot({ path: path.join(output, 'website-desktop.png'), fullPage: true });
  await website.setViewportSize({ width: 390, height: 844 });
  await website.screenshot({ path: path.join(output, 'website-mobile.png'), fullPage: true });

  const readme = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  await readme.goto(readmeUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
  const body = readme.locator('.markdown-body');
  await body.waitFor({ state: 'visible', timeout: 30000 });
  await readme.screenshot({ path: path.join(output, 'readme-github-desktop.png') });
  const desktopHeading = body.getByRole('heading', { name: 'Desktop app (alpha)' });
  await desktopHeading.scrollIntoViewIfNeeded();
  await readme.screenshot({ path: path.join(output, 'readme-desktop-app.png') });
  await readme.setViewportSize({ width: 390, height: 844 });
  await readme.evaluate(() => window.scrollTo(0, 0));
  await readme.screenshot({ path: path.join(output, 'readme-github-mobile.png') });

  await fs.writeFile(path.join(output, 'capture-metadata.json'), JSON.stringify({
    commit: sha,
    websiteUrl,
    readmeUrl,
    screenshots: [
      'website-desktop.png',
      'website-mobile.png',
      'readme-github-desktop.png',
      'readme-desktop-app.png',
      'readme-github-mobile.png'
    ],
    capturedHeadless: true
  }, null, 2) + '\n');
} finally {
  await browser.close();
}
