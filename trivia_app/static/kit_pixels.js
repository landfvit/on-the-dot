/* Shared pixel clothing for the profile preview and the Three.js figures.
 * Every pixel is drawn here: no source bitmap, tracing or image download.
 * Catalogue definitions describe stripes, hoops, sleeves and socks.
 * Change silhouettes here, not in separate preview/game implementations. */
let pending;
export function loadKits(){
  if(!pending)pending=fetch('/trivia-assets/player-kits/catalog.json?v=1').then(r=>{
    if(!r.ok)throw Error('Kits could not load. Please retry.');return r.json();
  }).catch(e=>{pending=null;throw e;});
  return pending;
}
const digits=[['111','101','101','101','111'],['010','110','010','010','111'],['111','001','111','100','111'],['111','001','111','001','111'],['101','101','111','001','001'],['111','100','111','001','111'],['111','100','111','101','111'],['111','001','010','010','010'],['111','101','111','101','111'],['111','101','111','001','111']];
export function kitPixels(kit,part,number=10){
  const d=kit.design,[w,h]={front:[18,20],back:[18,20],sleeve:[6,8],shorts:[12,6],sock:[5,8]}[part];
  const colors=Object.fromEntries(Object.entries({B:d.shirt,P:d.contrast,A:d.sleeve,T:d.trim,C:d.shorts,S:d.socks}).map(([k,v])=>[k,parseInt(v.slice(1),16)]));
  const shirt=part==='front'||part==='back';
  const rows=Array.from({length:h},(_,y)=>Array.from({length:w},(_,x)=>{
    if(!shirt){
      if(part==='sleeve')return y===h-2?'T':'A';
      if(part==='shorts')return x===1||x===w-2?'T':'C';
      return y===1?'T':'S';
    }
    let pattern=false;
    switch(d.pattern){
      case 'stripes':pattern=Math.floor((x+1)/3)%2===0;break;
      case 'pinstripes':pattern=x%4===0;break;
      case 'hoops':pattern=y>3&&y%5===0;break;
      case 'band':pattern=y>=7&&y<=10;break;
      case 'sash':pattern=Math.abs(x-(17-y*.7))<2;break;
      case 'checks':pattern=(Math.floor(x/3)+Math.floor(y/3))%2===0;break;
      case 'zigzag':pattern=(x+y+(Math.floor(y/4)%2)*3)%7<2;break;
      case 'flecks':pattern=(x*7+y*11)%17<3;break;
      case 'hem':pattern=y>14&&(x+y)%4<2;break;
      case 'sidepanels':pattern=x<4||x>13;break;
      case 'fade-stripes':pattern=x%6<3&&y>5&&((x+y)%4<Math.floor((y-4)/4));break;
      case 'saints':pattern=[2,5,6,7,10,11,12,15].includes(x);break;
    }
    return pattern?'P':'B';
  }));
  // Collar and cuffs stay bold enough for the game's intentionally low
  // resolution. Front chest marks are omitted, leaving actual shirt patterns.
  if(shirt){for(let x=5;x<13;x++)rows[1][x]='T';for(let x=7;x<11;x++)rows[2][x]='T';}
  colors.K=0x202820;
  // A restrained, one-pixel outline belongs to the garment silhouette only.
  function bounds(y){
    if(part==='front'||part==='back')return y===0?[5,w-6]:y===1?[3,w-4]:y===h-1?[2,w-3]:[1,w-2];
    return [0,w-1];
  }
  for(let y=0;y<h;y++){
    const [left,right]=bounds(y);
    for(let x=0;x<w;x++)if(x<left||x>right)rows[y][x]='.';
    else if(x===left||x===right||y===0||y===h-1)rows[y][x]='K';
  }
  if(part==='shorts')for(let y=h-2;y<h;y++)for(let x=w/2-1;x<=w/2;x++)rows[y][x]='.';
  if(part==='back'){
    // Draw native 3x5 glyphs with one-pixel strokes and a one-pixel gap.
    // Fractional resizing duplicated the centre column and made "1" heavier
    // than the other digits. The same glyph now works in either digit slot.
    const value=String(Number.isInteger(number)&&number>=1&&number<=99?number:10);
    const numberWidth=value.length*4-1,ink=[],x0=Math.floor((w-numberWidth)/2),y0=7;
    [...value].forEach((digit,i)=>digits[Number(digit)].forEach((row,y)=>{
      [...row].forEach((pixel,x)=>{if(pixel==='1')ink.push([x0+i*4+x,y0+y]);});
    }));
    let luminance=0,count=0;
    for(const [x,y] of ink){const c=colors[rows[y][x]];luminance+=(c>>16&255)*.2126+(c>>8&255)*.7152+(c&255)*.0722;count++;}
    colors.N=luminance/count>150?0x151a16:0xffffff;colors.O=colors.N===0xffffff?0x151a16:0xffffff;
    for(const [x,y] of ink)for(const [dx,dy] of [[-1,0],[1,0],[0,-1],[0,1]])if(rows[y+dy]?.[x+dx]&&rows[y+dy][x+dx]!=='.')rows[y+dy][x+dx]='O';
    for(const [x,y] of ink)rows[y][x]='N';
  }
  return {rows:rows.map(row=>row.join('')),colors};
}
export function paintKit(canvas,kit,number=10,back=false){
  const c=canvas.getContext('2d');canvas.width=40;canvas.height=44;
  c.clearRect(0,0,40,44);c.imageSmoothingEnabled=false;
  function draw(part,x,y){const {rows,colors}=kitPixels(kit,part,number);
    rows.forEach((row,dy)=>[...row].forEach((key,dx)=>{if(key!=='.'){c.fillStyle='#'+colors[key].toString(16).padStart(6,'0');c.fillRect(x+dx,y+dy,1,1);}}));}
  draw('sleeve',5,4);draw('sleeve',29,4);draw(back?'back':'front',11,2);
  draw('shorts',14,23);draw('sock',14,31);draw('sock',21,31);
}
