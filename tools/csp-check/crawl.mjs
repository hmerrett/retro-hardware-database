// Drive a real browser over the site and report anything the Content-Security-
// Policy refused. ADR-0021.
//
// The suite can prove the header ships and that the markup does not obviously
// break it, but it has no browser, so it cannot prove a page still *works*. A
// blocked script is silent: no error the server sees, no failing request, just a
// control that has stopped doing anything. This is the only check that would
// notice.
//
// Every violation is caught twice over -- `securitypolicyviolation` fires on the
// document, and the refusal is also written to the console -- because a violation
// in a page that then throws should still be attributable to the policy and not
// to the exception it caused.
import { chromium } from 'playwright';

const BASE = process.env.CSP_BASE || 'http://localhost:18080';

// Straight page loads. The interactive work is below, because a policy breaks
// most easily in the code that runs after the page has settled.
const PAGES = [
  '/', '/machines', '/projects', '/projects/new', '/files', '/stats', '/for-sale',
  '/computers/new', '/parts/new', '/parts/new?type=storage', '/login',
  '/no-such-page',
];

// Things the page only does when somebody does something. Each is [label, path,
// async fn]; a throw is reported and the crawl carries on, because one broken
// interaction should not hide the twelve after it.
const INTERACTIONS = [
  ['search autocomplete', '/', async (page) => {
    const box = page.locator('header input[type=search]').first();
    await box.fill('a');
    await page.waitForTimeout(700);          // the suggestion request and its render
  }],
  ['theme toggle', '/', async (page) => {
    const toggle = page.locator('[data-theme-toggle], #themebtn, button[title*="theme" i]').first();
    if (await toggle.count()) { await toggle.click(); await page.waitForTimeout(200); }
  }],
  ['machine picker', '/computers/new', async (page) => {
    const maker = page.locator('input[name=manufacturer], select[name=manufacturer]').first();
    await maker.fill('Amstrad').catch(() => {});
    await page.waitForTimeout(500);          // catalogue lookup writes the model list
  }],
  ['part form, storage routing', '/parts/new?type=storage', async (page) => {
    const kind = page.locator('select[name=type], select[name=kind]').first();
    if (await kind.count()) { await kind.selectOption({ index: 1 }).catch(() => {}); }
    await page.waitForTimeout(300);
  }],
  // Two elements the markup starts hidden with a class rather than with a style
  // attribute (ADR-0022), which is a browser question and nothing else: a class
  // rule outranks an inline `display: ''`, so the script has to take the class
  // off. Setting the inline style instead leaves them hidden for ever, and every
  // test in the suite still passes -- which is how this nearly shipped.
  ['the empty line, when the filters hold everything back', '/', async (page) => {
    const box = page.locator('#q');
    if (!await box.count()) return;
    await box.fill('zzzz-no-such-thing-zzzz');
    await page.waitForTimeout(300);
    const empty = page.locator('#empty');
    if (!await empty.isVisible()) {
      throw new Error('#empty stayed hidden with every card filtered out');
    }
    await box.fill('');
    await page.waitForTimeout(300);
    if (await empty.isVisible()) throw new Error('#empty stayed up once cards came back');
  }],
  ['the same-make offer on a new part', '/parts/new', async (page) => {
    const note = page.locator('#samemake');
    if (!await note.count()) return;
    await page.locator('#manufacturer').fill('Trident');
    await page.locator('#model').fill('TVGA8900');
    await page.locator('#model').dispatchEvent('input');
    await page.waitForTimeout(400);
    if (!await note.isVisible()) {
      throw new Error('#samemake stayed hidden for a make and model already in the register');
    }
  }],
  ['lightbox', null, async (page, ctx) => {
    if (!ctx.itemPage) return;
    await page.goto(BASE + ctx.itemPage, { waitUntil: 'networkidle' });
    const shot = page.locator('img.zoomable').first();
    if (await shot.count()) { await shot.click(); await page.waitForTimeout(400); }
  }],
];

const violations = [];
const errors = [];
// An interaction that throws is a failure of its own kind: not the policy, and
// not a page error either, because the page is perfectly happy -- it is simply
// not doing what it is there to do. It used to be printed and otherwise ignored,
// so a run could report that an interaction "could not be driven" and still end
// OK, which is the monitor-that-only-greps-for-success ADR-0021 argues against.
const undriven = [];

function watch(page) {
  // `page.url()` at the moment it fires, not a label captured when the listener
  // was attached: one page object visits everything, so a fixed label puts every
  // finding on whatever page happened to be first.
  page.on('console', (msg) => {
    const text = msg.text();
    if (/Content Security Policy|Refused to (load|execute|apply|connect|frame)/i.test(text)) {
      violations.push({ where: page.url(), how: 'refused', what: text });
    }
  });
  page.on('pageerror', (err) => {
    // Not a policy violation, and reported as its own kind. Worth catching all
    // the same: a blocked script and a broken one look identical to a reader,
    // and this crawl is the only thing here that runs the JavaScript at all.
    // It is how `FORM is not defined` was found on the part form.
    errors.push({ where: page.url(), what: String(err).slice(0, 300) });
  });
  page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (ev) => {
      (window.__cspViolations = window.__cspViolations || []).push({
        directive: ev.effectiveDirective,
        blocked: ev.blockedURI,
        sample: ev.sample || '',
        line: ev.lineNumber,
      });
    });
  });
}

async function drain(page, where) {
  const found = await page.evaluate(() => {
    const out = window.__cspViolations || [];
    window.__cspViolations = [];
    return out;
  }).catch(() => []);
  for (const v of found) {
    violations.push({ where, how: 'event', what: `${v.directive} blocked ${v.blocked} ${v.sample}`.trim() });
  }
}

const browser = await chromium.launch();
const context = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await context.newPage();
watch(page);

// Signed in as the throwaway administrator the runner seeds, so the crawl sees the
// forms and the owner-only pages as well as the public ones (ADR-0032). The login
// page is crawled on the way in, which is one more page with the policy on it.
if (process.env.CSP_USER) {
  await page.goto(BASE + '/login', { waitUntil: 'networkidle' });
  await page.fill('#username', process.env.CSP_USER);
  await page.fill('#password', process.env.CSP_PASS || '');
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
}

// The policy has to actually be on the response, or everything below passes for
// the wrong reason: no header, no violations, a clean run and nothing proved.
const first = await page.goto(BASE + '/', { waitUntil: 'networkidle' });
const policy = first.headers()['content-security-policy'];
if (!policy) {
  console.error('FAIL: no Content-Security-Policy on the response. Nothing below would mean anything.');
  await browser.close();
  process.exit(2);
}
console.log('policy: ' + policy + '\n');

// An item page only exists if there is an item; the runner seeds one and passes
// its id in. Without it the item templates -- the photo column, the history, the
// part list -- go uncrawled, and those are where the scripts are.
const ctx = { itemPage: process.env.CSP_ITEM || null };
const paths = ctx.itemPage
  ? [...PAGES, ctx.itemPage, ctx.itemPage + '/edit']
  : PAGES;

for (const path of paths) {
  const where = `page ${path}`;
  const response = await page.goto(BASE + path, { waitUntil: 'networkidle' }).catch((e) => {
    violations.push({ where, how: 'navigation', what: String(e).slice(0, 200) });
    return null;
  });
  if (response && !response.headers()['content-security-policy']) {
    violations.push({ where, how: 'header', what: `no policy on a ${response.status()}` });
  }
  await drain(page, where);
  console.log(`  visited ${path}${response ? ' (' + response.status() + ')' : ''}`);
}

for (const [label, path, act] of INTERACTIONS) {
  const where = `interaction: ${label}`;
  try {
    if (path) await page.goto(BASE + path, { waitUntil: 'networkidle' });
    await act(page, ctx);
  } catch (e) {
    undriven.push({ where, what: String(e).slice(0, 200) });
    console.log(`  ${label}: could not be driven (${String(e).slice(0, 120)})`);
    await drain(page, where);
    continue;
  }
  await drain(page, where);
  console.log(`  exercised ${label}`);
}

await browser.close();

if (violations.length) {
  console.error(`\n${violations.length} policy violation(s):\n`);
  for (const v of violations) console.error(`  [${v.where}] (${v.how}) ${v.what}`);
}
if (errors.length) {
  console.error(`\n${errors.length} script error(s) -- not the policy, but broken all the same:\n`);
  for (const e of errors) console.error(`  [${e.where}] ${e.what}`);
}
if (undriven.length) {
  console.error(`\n${undriven.length} interaction(s) that could not be driven:\n`);
  for (const u of undriven) console.error(`  [${u.where}] ${u.what}`);
}
if (violations.length || errors.length || undriven.length) {
  console.error('\nFAIL');
  process.exit(1);
}
console.log('\nOK: nothing was refused, no page threw, and every interaction ran.');
