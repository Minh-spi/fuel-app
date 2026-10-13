// One-off capture from PVOIL's public historical-price page.
// Uses a visible local Edge window so the user can complete any site challenge.
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('@playwright/test');

const PAGE = 'https://www.pvoil.com.vn/tin-gia-xang-dau';
const OUTPUT = path.resolve('note/pvoil_history.json');
const fromYear = Number(process.argv[2] || new Date().getFullYear());
if (!Number.isInteger(fromYear) || fromYear < 2000 || fromYear > 2100) throw new Error('Pass a valid start year, e.g. 2026.');

function dateFromText(text) {
  const iso = text.match(/\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b/);
  if (iso) return { year: Number(iso[1]), month: Number(iso[2]), day: Number(iso[3]) };
  const local = text.match(/\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b/);
  return local ? { year: Number(local[3]), month: Number(local[2]), day: Number(local[1]) } : null;
}

async function main() {
  await fs.mkdir(path.dirname(OUTPUT), { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: false });
  try {
    const page = await browser.newPage({ locale: 'vi-VN', timezoneId: 'Asia/Ho_Chi_Minh' });
    console.log(`Opening ${PAGE}. If PVOIL asks for verification, complete it in the Edge window.`);
    await page.goto(PAGE, { waitUntil: 'domcontentloaded', timeout: 90000 }).catch(() => {});
    const select = page.locator('select.select-tabs.custom-select').first();
    try {
      await select.waitFor({ state: 'visible', timeout: 240000 });
    } catch {
      throw new Error('PVOIL history selector did not become available. No anti-bot challenge was bypassed.');
    }
    const options = await select.locator('option').evaluateAll(nodes => nodes.map(o => ({ value: o.value, label: o.textContent.trim() })).filter(o => o.value));
    if (!options.length) throw new Error('PVOIL returned no history periods.');
    const captures = [];
    for (const option of options) {
      const optionDate = dateFromText(option.label);
      if (optionDate && optionDate.year < fromYear) continue;
      const selectedValue = await select.inputValue();
      if (selectedValue !== option.value) {
        const before = await page.locator('table').evaluateAll(tables => tables.map(t => t.innerText).join('\n'));
        await select.selectOption(option.value);
        await page.waitForFunction(previous => {
          const current = [...document.querySelectorAll('table')].map(t => t.innerText).join('\n');
          return current && current !== previous;
        }, before, { timeout: 20000 });
      }
      const table = await page.locator('table').evaluateAll(tables => {
        const candidate = tables.find(t => /E10|E5/i.test(t.innerText));
        if (!candidate) return null;
        return {
          headers: [...candidate.querySelectorAll('thead th')].map(x => x.innerText.trim()),
          rows: [...candidate.querySelectorAll('tbody tr')].map(tr => [...tr.querySelectorAll('th,td')].map(x => x.innerText.trim()))
        };
      });
      if (!table || !table.rows.length) throw new Error(`No fuel-price rows for period: ${option.label}`);
      const context = `${table.headers.join(' ')}\n${option.label}`;
      const date = dateFromText(context);
      const time = context.match(/(?:lúc|từ|at)\s*(\d{1,2})\s*(?::|h|giờ)\s*(\d{2})/i);
      if (!date || !time) throw new Error(`Could not verify effective date/time from PVOIL table: ${option.label}`);
      const day = `${date.year}-${String(date.month).padStart(2,'0')}-${String(date.day).padStart(2,'0')}`;
      if (date.year < fromYear) continue;
      const products = table.rows.map(cells => ({ cells })).filter(row => row.cells.length >= 2);
      captures.push({ selected_period: option.label, effective_at: `${day}T${String(time[1]).padStart(2,'0')}:${time[2]}:00+07:00`, headers: table.headers, products });
      console.log(`Captured ${option.label}`);
    }
    if (!captures.length) throw new Error(`No periods from ${fromYear} were captured.`);
    const data = { source_url: PAGE, captured_at: new Date().toISOString(), from_year: fromYear, periods: captures };
    await fs.writeFile(OUTPUT, JSON.stringify(data, null, 2), 'utf8');
    console.log(`Saved ${captures.length} periods to ${OUTPUT}. Inspect it, then run scripts/import_pvoil_history.py --input note/pvoil_history.json --dry-run.`);
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
