// Offline build only. All silhouettes/patterns are authored in kit_pixels.js;
// this command never requests, downloads, crops or recolors a source image.
import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');
const designs=JSON.parse(fs.readFileSync(path.join(root,'tools/player_kit_designs.json'),'utf8'));
const kits=[],clubs=[];
for(const c of designs.clubs){
  clubs.push({team_id:c.team_id,name:c.name,last_season:c.season});
  for(const [type,pattern,shirt,contrast,sleeve,trim,shorts,socks] of c.kits){
    kits.push({id:`${c.team_id}-${c.season}-${type}`,team_id:c.team_id,team:c.name,season:c.season,type,
      label:type[0].toUpperCase()+type.slice(1),design:{pattern,shirt,contrast,sleeve,trim,shorts,socks},
      source_url:c.references?.[0]||(c.season===2026?'https://www.premierleague.com/en/news/4672981':`https://commons.wikimedia.org/wiki/2025%E2%80%9326_${[44,48,39].includes(c.team_id)?'Premier_League':c.team_id===37?'EFL_League_One':'EFL_Championship'}_kits`),
      source_files:c.references?.slice(1)||[]});
  }
}
const missing=clubs.flatMap(c=>['home','away','third'].filter(type=>!kits.some(k=>k.team_id===c.team_id&&k.type===type)).map(type=>({team_id:c.team_id,name:c.name,type,reason:'Not yet verified and drawn'})));
const out=path.join(root,'trivia_app/static/player-kits');fs.mkdirSync(out,{recursive:true});
fs.writeFileSync(path.join(out,'catalog.json'),JSON.stringify({version:1,style:'Original pixel artwork',clubs,kits,missing})+'\n');
console.log(`${clubs.length} clubs, ${kits.length} authored kits; ${missing.length} sets pending artwork verification`);
