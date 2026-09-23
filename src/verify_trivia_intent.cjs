// Opt-in, read-only UI verification of the real trained recognition adapter.
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
    const browser = await chromium.launch({headless: true, channel: 'chrome'});
    try {
        const context = await browser.newContext();
        const login = await context.request.post('http://127.0.0.1:8002/login', {form: {
            username: process.env.TRIVIA_EDITOR_USERNAME, password: process.env.TRIVIA_EDITOR_PASSWORD}, maxRedirects: 0});
        if (login.status() !== 303) throw new Error('Studio login failed');
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.setViewportSize({width: 1440, height: 1050});
        await page.goto('http://127.0.0.1:8002/internal/trivia#question-writer');
        await page.locator('#writer-examples button').first().waitFor();
        const question = 'How many goals has Marcus Rashford scored in his premier league career';
        await page.locator('#writer-question').fill(question);
        const pending = page.waitForResponse(r => r.url().endsWith('/api/trivia/writer/interpret'), {timeout: 180000});
        await page.locator('#writer-submit').click();
        const interpreted = await (await pending).json();
        if (interpreted.method !== 'intent_model' || interpreted.query.time_scope !== 'career' || interpreted.query.season !== null) {
            throw new Error('Expected trained career recognition: ' + JSON.stringify(interpreted));
        }
        await page.locator('#writer-confirm').waitFor({state: 'visible'});
        if (!await page.locator('#writer-answer-section').isHidden()) throw new Error('Answer shown before confirmation');
        const answering = page.waitForResponse(r => r.url().endsWith('/api/trivia/writer/answer'));
        await page.locator('#writer-confirm').click();
        const answered = await (await answering).json();
        await page.locator('#writer-answer-section').waitFor({state: 'visible'});
        if (answered.calculation.details.player_id !== 909) throw new Error('Incorrect resolved player');
        if (await page.locator('#writer-question').inputValue() !== question) throw new Error('Original text changed');
        if (!await page.locator('#writer-save').isDisabled()) throw new Error('Partial answer could be saved');
        if (!/Incomplete/.test(await page.locator('#writer-evidence').innerText())) throw new Error('Missing coverage warning');
        const out = path.resolve('data/private/intent-ui-check'); fs.mkdirSync(out, {recursive: true});
        await page.locator('#question-writer').scrollIntoViewIfNeeded();
        await page.screenshot({path: path.join(out, 'desktop.png')});
        await page.setViewportSize({width: 390, height: 844});
        await page.locator('#writer-answer-section').scrollIntoViewIfNeeded();
        await page.screenshot({path: path.join(out, 'mobile.png')});
        if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Mobile overflow');
        const league = 'Who won the Premier League in 2025/26 season?';
        await page.locator('#writer-question').fill(league);
        if (!await page.locator('#writer-answer-section').isHidden()) throw new Error('Stale career answer');
        const leaguePending = page.waitForResponse(r => r.url().endsWith('/api/trivia/writer/interpret'));
        await page.locator('#writer-submit').click();
        const leagueResult = await (await leaguePending).json();
        if (leagueResult.status !== 'calculated') throw new Error('League-wide query failed');
        if (errors.length) throw new Error(errors.join('; '));
        console.log(JSON.stringify({method: interpreted.method, query: interpreted.query,
            careerAnswer: answered.calculation.answer, playerId: answered.calculation.details.player_id,
            leagueAnswer: leagueResult.calculation.answer, errors, screenshots: out}));
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
