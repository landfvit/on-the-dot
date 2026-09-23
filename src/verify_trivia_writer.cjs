// Opt-in browser check against a running local private Studio. Does not save drafts.
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
    const browser = await chromium.launch({headless: true, channel: 'chrome'});
    try {
        const context = await browser.newContext({httpCredentials: {
            username: process.env.TRIVIA_EDITOR_USERNAME, password: process.env.TRIVIA_EDITOR_PASSWORD}});
        const login = await context.request.post('http://127.0.0.1:8002/login', {form: {
            username: process.env.TRIVIA_EDITOR_USERNAME, password: process.env.TRIVIA_EDITOR_PASSWORD}, maxRedirects: 0});
        if (login.status() !== 303) throw new Error('Private Studio login failed');
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', e => errors.push(e.message));
        await page.setViewportSize({width: 1440, height: 1050});
        await page.goto('http://127.0.0.1:8002/internal/trivia#question-writer');
        await page.locator('#writer-examples button').first().waitFor();
        const original = await page.locator('#writer-examples button').first().innerText();
        await page.locator('#writer-examples button').first().click();
        await page.getByRole('button', {name: 'Find answer', exact: true}).click();
        await page.locator('#writer-confirm').waitFor({state: 'visible', timeout: 180000});
        await page.locator('#writer-confirm').click();
        await page.locator('#writer-answer-section').waitFor({state: 'visible'}).catch(async () => {
            throw new Error('Answer did not appear: ' + await page.locator('#writer-status').innerText() + '; browser errors: ' + errors.join('; '));
        });
        const answer = await page.locator('#writer-answer').innerText();
        const details = await page.locator('#writer-details').innerText();
        if (!/Lukaku/.test(answer) || !/16/.test(details)) throw new Error('Expected Lukaku and 16 goals');
        if (await page.locator('#writer-question').inputValue() !== original) throw new Error('User text changed');
        const out = path.resolve('data/private/writer-ui-check'); fs.mkdirSync(out, {recursive: true});
        await page.locator('#question-writer').scrollIntoViewIfNeeded();
        await page.screenshot({path: path.join(out, 'desktop.png')});
        await page.setViewportSize({width: 390, height: 844});
        await page.locator('#question-writer').scrollIntoViewIfNeeded();
        await page.screenshot({path: path.join(out, 'mobile.png')});
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
        if (overflow) throw new Error('Mobile horizontal overflow');
        const leagueQuestion = 'Who won the Premier League in 2025/26 season?';
        await page.locator('#writer-question').fill(leagueQuestion);
        const leagueResponse = page.waitForResponse(r => r.url().endsWith('/api/trivia/writer/interpret') && r.request().method() === 'POST');
        await page.getByRole('button', {name: 'Find answer', exact: true}).click();
        const leagueData = await (await leagueResponse).json();
        if (leagueData.status !== 'calculated') throw new Error('League winner needs an unnecessary model fallback');
        await page.locator('#writer-answer-section').waitFor({state: 'visible'});
        const leagueAnswer = await page.locator('#writer-answer').innerText();
        if (leagueAnswer !== leagueData.calculation.answer) throw new Error('League answer mismatch');
        if (await page.locator('#writer-question').inputValue() !== leagueQuestion) throw new Error('League question changed');
        await page.screenshot({path: path.join(out, 'league-winner-mobile.png')});
        await page.locator('#writer-question').fill('Which club drew the most games?');
        if (!await page.locator('#writer-answer-section').isHidden()) throw new Error('Stale answer visible');
        if (!await page.locator('#writer-save').isDisabled()) throw new Error('Stale save enabled');
        await page.getByRole('button', {name: 'Find answer', exact: true}).click();
        await page.getByText('Include an explicit season, for example 2017/18. No season is assumed.', {exact: true}).waitFor();
        if (errors.length) throw new Error(errors.join('; '));
        console.log(JSON.stringify({answer, details, leagueAnswer, originalPreserved: true, mobileOverflow: overflow, errors, screenshots: out}));
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
