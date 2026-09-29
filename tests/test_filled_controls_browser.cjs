/* Local, read-only UI checks. Answer states below are DOM fixtures, not games. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8009';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));
const out='/tmp/on-the-dot-filled-controls';fs.mkdirSync(out,{recursive:true});
const controls='button,summary,.primary-link,.play-button,.top-navigation a,.top-navigation .nav-current,.page-return>a,.home-rules-bottom a,.game-mode-tabs a,.guide-jump a,.guide-guest>a,.solo-heading>a,.daily-ranking-link,#public-profile,.team-rules-link,.period-tabs span,.guide-scenarios span,.difficulty-options label,.auth-options label,.team-options label';
(async()=>{
    const browser=await chromium.launch({channel:'chrome',headless:true});
    try{
        const page=await browser.newPage(),errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));
        await page.route('**/api/**',route=>{
            if(route.request().method()==='GET')return route.continue();
            writes.push(route.request().url());return route.abort();
        });
        for(const width of [320,390,1440]){
            await page.setViewportSize({width,height:900});
            for(const path of ['/','/penalties','/daily','/friends','/leaderboard','/history','/account','/how-to-play']){
                await page.goto(origin+path);
                for(const theme of ['light','dark']){
                    if(await page.locator('html').getAttribute('data-theme')!==theme)await page.locator('.top-navigation [data-theme-toggle]').click();
                    await page.mouse.move(0,0);
                    const failures=await page.locator(controls).evaluateAll(elements=>elements.flatMap(e=>{
                        const s=getComputedStyle(e),visibleBorder=['Top','Right','Bottom','Left'].some(side=>parseFloat(s[`border${side}Width`])>0&&s[`border${side}Style`]!=='none'&&s[`border${side}Color`]!=='rgba(0, 0, 0, 0)');
                        return visibleBorder||s.boxShadow!=='none'||s.backgroundColor==='rgba(0, 0, 0, 0)'?[{id:e.id,label:e.textContent.trim().slice(0,45),border:s.borderTopColor,background:s.backgroundColor}]:[];
                    }));
                    assert.deepEqual(failures,[],`${path}, ${theme}: controls must use fill, not outlines`);
                    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${path}, ${width}`);
                    const baseline=await page.locator('.top-navigation a').first().evaluate(e=>getComputedStyle(e).backgroundColor);
                    assert.equal(baseline,theme==='dark'?'rgb(52, 58, 53)':'rgb(226, 228, 222)');
                    if(path==='/penalties'){
                        const easy=page.locator('.difficulty-options label').first(),before=await easy.boundingBox();
                        await page.locator('.difficulty-options label').nth(1).click();
                        assert.deepEqual(await easy.boundingBox(),before,'Selecting a difficulty must not move controls');
                        assert.equal(await page.locator('.difficulty-options label:has(:checked)').evaluate(e=>getComputedStyle(e).backgroundColor),theme==='dark'?'rgb(246, 243, 235)':'rgb(17, 17, 17)');
                        const colors=await page.evaluate(()=>{
                            const choices=document.getElementById('choices');
                            choices.replaceChildren(...['correct','incorrect'].map(state=>{const button=document.createElement('button');button.className=state;button.textContent='Test answer';return button;}));
                            return [...choices.children].map(button=>{const s=getComputedStyle(button);return {fill:s.backgroundColor,border:s.borderTopColor,radius:s.borderRadius};});
                        });
                        assert.deepEqual(colors,[{fill:'rgb(136, 176, 75)',border:'rgba(0, 0, 0, 0)',radius:'6px'},
                            {fill:theme==='dark'?'rgb(255, 134, 124)':'rgb(165, 44, 39)',border:'rgba(0, 0, 0, 0)',radius:'6px'}]);
                        await page.keyboard.press('Tab');await page.locator('.game-rules-link').focus();
                        assert(await page.locator('.game-rules-link').evaluate(e=>e.matches(':focus-visible')&&getComputedStyle(e).outlineStyle==='solid'),'Keyboard focus must stay visible');
                        await page.locator('.game-rules-link').evaluate(e=>e.blur());
                    }
                    if(['/','/penalties','/leaderboard','/account'].includes(path))await page.screenshot({path:`${out}/${width}-${path.slice(1)||'home'}-${theme}.png`,fullPage:true});
                }
            }
            console.log(`PASS ${width}: 8 pages, both themes, borderless fills, stable selection, answer colors and keyboard focus`);
        }
        assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
    }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
