import {loadKits,paintKit} from './kit_pixels.js?v=4';
const $=id=>document.getElementById(id);
let data,profile,selection=null,revision=0;
const season=kit=>`${kit.season}/${String(kit.season+1).slice(-2)}`;
function selected(){return data?.kits.find(k=>k.id===selection);}
function previews(){
  const kit=selected();if(!kit)return;
  const number=Number($('kit-number').value);
  paintKit($('kit-preview-front'),kit,number);paintKit($('kit-preview-back'),kit,number,true);
  $('kit-preview-name').textContent=`${kit.team} ${season(kit)} · ${kit.label}`;
}
function options(){
  const kits=data.kits.filter(k=>k.team_id===profile.club?.team_id);
  if(!kits.some(k=>k.id===selection))selection=kits.find(k=>k.type==='home')?.id||kits[0]?.id;
  $('kit-options').replaceChildren();
  for(const kit of kits){
    const label=document.createElement('label'),input=document.createElement('input'),canvas=document.createElement('canvas');
    input.type='radio';input.name='player-kit';input.value=kit.id;input.checked=kit.id===selection;
    input.setAttribute('aria-label',kit.label+' '+season(kit));
    label.title=kit.label+' '+season(kit);
    canvas.setAttribute('aria-hidden','true');paintKit(canvas,kit);
    label.append(input,canvas);$('kit-options').append(label);
    input.addEventListener('change',()=>{selection=kit.id;previews();$('kit-status').textContent='';});
  }
  previews();
}
async function update(p,own){
  if(!own)return;profile=p;const ticket=++revision;
  $('kit-form').hidden=true;$('kit-retry').hidden=true;$('kit-status').textContent='Loading kits...';
  if(!p.club){$('kit-status').textContent='Join a team to choose its kit.';return;}
  try{
    data=await loadKits();if(ticket!==revision)return;
    selection=p.outfit?.kit_id||null;
    const kit=selected()||data.kits.find(k=>k.team_id===p.club.team_id);
    if(!kit){$('kit-status').textContent='Kits for your team are being prepared.';return;}
    $('kit-number').value=p.outfit?.number||10;
    $('kit-status').textContent='';$('kit-form').hidden=false;options();
  }catch(e){if(ticket===revision){$('kit-status').textContent=e.message;$('kit-retry').hidden=false;}}
}
$('kit-number').addEventListener('input',previews);
$('kit-retry').addEventListener('click',()=>update(profile,true));
$('kit-form').addEventListener('submit',async event=>{
  event.preventDefault();if(!selected())return;
  const button=$('kit-save');button.disabled=true;$('kit-status').textContent='';
  try{
    const r=await fetch('/api/players/me/outfit',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({kit_id:selection,number:Number($('kit-number').value)})});
    const body=await r.json();if(!r.ok)throw Error(typeof body.detail==='string'?body.detail:'Check the shirt number (1–99).');
    profile.outfit=body.outfit;$('kit-status').textContent='Kit saved.';
  }catch(e){$('kit-status').textContent=e.message;}finally{button.disabled=false;}
});
window.addEventListener('points-profile',e=>update(e.detail.profile,e.detail.own));
if(globalThis.PointsProfile)update(PointsProfile.profile,PointsProfile.own);
