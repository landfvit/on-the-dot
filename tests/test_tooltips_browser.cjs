/* Local assets, mocked accounts. Checks top-layer hints without real writes. */
const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const origin=process.env.MOBILE_TEST_URL||'http://127.0.0.1:8009',out='/private/tmp/on-the-dot-tooltips';
assert(['localhost','127.0.0.1'].includes(new URL(origin).hostname));fs.mkdirSync(out,{recursive:true});
async function fits(page,selector){
 const result=await page.locator(selector).evaluate(trigger=>{
  const tip=document.querySelector('#ui-tooltip'),a=trigger.getBoundingClientRect(),b=tip.getBoundingClientRect();
  return {bounds:[b.left,b.top,b.right,b.bottom],viewport:[innerWidth,innerHeight],
   overlap:Math.min(a.right,b.right)>Math.max(a.left,b.left)&&Math.min(a.bottom,b.bottom)>Math.max(a.top,b.top),
   described:trigger.getAttribute('aria-describedby')?.includes(tip.id),
   native:trigger.hasAttribute('title'),topmost:document.elementFromPoint(b.x+b.width/2,b.y+b.height/2)===tip};
 });
 assert(result.bounds[0]>=7&&result.bounds[1]>=7&&result.bounds[2]<=result.viewport[0]-7&&result.bounds[3]<=result.viewport[1]-7,result);
 assert(!result.overlap,'Hint never covers its trigger');assert(result.described);assert(!result.native);assert(result.topmost,'Hint is above any dialog');
}
(async()=>{
 const engine=process.env.TEST_BROWSER||'chrome',browser=engine==='webkit'?await webkit.launch():await chromium.launch({channel:'chrome',headless:true});
 try{
  for(const [width,height] of [[320,568],[390,700],[844,390],[1440,900]])for(const theme of ['light','dark']){
   if(process.env.TEST_WIDTH&&width!==Number(process.env.TEST_WIDTH))continue;
   const page=await browser.newPage({viewport:{width,height}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(t=>localStorage.setItem('onthedot.theme',t),theme);
   await page.route('**/api/**',r=>r.fulfill({status:401,json:{detail:'Sign in'}}));
   await page.goto(origin+'/how-to-play');
   const nav=page.locator('.top-navigation [data-ui-tooltip]');
   for(let i=0;i<await nav.count();i++){
    const item=nav.nth(i);await item.hover();await page.locator('#ui-tooltip:not([hidden])').waitFor();
    await fits(page,`.top-navigation [data-ui-tooltip]:nth-child(${i+1})`);
    assert.equal(await page.locator('#ui-tooltip').textContent(),await item.getAttribute('data-ui-tooltip'));
    await page.keyboard.press('Escape');assert(!await page.locator('#ui-tooltip').isVisible());
   }
   // Leaving before the hover delay must cancel, not show a stale tooltip.
   await nav.first().hover();await page.mouse.move(1,height-1);await page.waitForTimeout(450);
   assert(!await page.locator('#ui-tooltip').isVisible());
   await nav.first().hover();await page.locator('#ui-tooltip:not([hidden])').waitFor();
   await page.locator('#ui-tooltip').hover();await page.waitForTimeout(180);assert(await page.locator('#ui-tooltip').isVisible());
   await page.keyboard.press('Escape');
   // Theme and sound controls rewrite their titles after click.
   await page.locator('[data-theme-toggle]').click();await page.mouse.move(1,height-1);await page.locator('[data-theme-toggle]').hover();
   await page.locator('#ui-tooltip:not([hidden])').waitFor();
   assert.equal(await page.locator('#ui-tooltip').textContent(),await page.locator('[data-theme-toggle]').getAttribute('aria-label'));
   await page.keyboard.press('Escape');
   await page.evaluate(()=>{
    const button=document.createElement('button');button.id='edge-hint';button.title='A long label at the edge of the screen stays readable without hiding its button.';
    button.style.cssText='position:fixed;right:8px;bottom:8px;width:44px;height:44px;z-index:50';button.textContent='?';document.body.append(button);
   });
   await page.locator('#edge-hint').hover();await page.locator('#ui-tooltip:not([hidden])').waitFor();await fits(page,'#edge-hint');
   await page.screenshot({path:`${out}/${engine}-${width}-${theme}-edge.png`});
   await page.keyboard.press('Escape');
   await page.evaluate(()=>{
    document.querySelector('#edge-hint').remove();const dialog=document.querySelector('#game-share-dialog');
    dialog.querySelector('[data-close-dialog]').title='Close sharing';dialog.showModal();
   });
   await page.locator('#game-share-dialog [data-close-dialog]').hover();await page.locator('#ui-tooltip:not([hidden])').waitFor();
   await fits(page,'#game-share-dialog [data-close-dialog]');
   await page.keyboard.press('Escape');assert(await page.locator('#game-share-dialog').isVisible(),'First Escape closes only the hint');
   await page.keyboard.press('Escape');assert(!await page.locator('#game-share-dialog').isVisible());
   // Keyboard hints do not depend on a mouse, and touch never leaves a hint.
   // Option+Tab includes links and buttons with Safari's default Mac setting.
   await page.locator('.points-brand').focus();await page.keyboard.press(engine==='webkit'?'Alt+Tab':'Tab');
   assert(await page.evaluate(()=>document.activeElement.closest('.top-navigation')&&document.activeElement.matches(':focus-visible')&&!!document.activeElement.dataset.uiTooltip));
   await page.waitForTimeout(500);
   await page.locator('#ui-tooltip:not([hidden])').waitFor();
   assert.equal(await page.locator('#ui-tooltip').textContent(),await page.evaluate(()=>document.activeElement.dataset.uiTooltip));
   await page.keyboard.press('Escape');
   await nav.first().dispatchEvent('pointerover',{pointerType:'touch'});await page.waitForTimeout(450);assert(!await page.locator('#ui-tooltip').isVisible());
   assert.deepEqual(errors,[]);await page.close();console.log(`PASS ${engine} ${width} ${theme}: viewport edges, dialog, keyboard, dynamic labels, hover cancellation, touch`);
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
