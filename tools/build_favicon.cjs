/* Lossless source artwork inside a tight square SVG viewport. The PNG export
 * is a compatibility fallback for browsers without SVG favicons. The original
 * mark and wordmark are never overwritten or redrawn. Requires Sharp. */
const fs=require('node:fs'),path=require('node:path'),sharp=require('sharp');
const directory=path.resolve(__dirname,'../trivia_app/static/brand');
(async()=>{
  const original=fs.readFileSync(path.join(directory,'mark.png'));
  const {data,info}=await sharp(original).ensureAlpha().raw().toBuffer({resolveWithObject:true});
  let left=info.width,top=info.height,right=-1,bottom=-1;
  for(let y=0;y<info.height;y++)for(let x=0;x<info.width;x++){
    const i=(y*info.width+x)*4;
    if(data[i+3]>128&&data[i+1]>100&&data[i+1]>data[i]*2&&data[i+1]>data[i+2]*1.2){
      left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y);
    }
  }
  if(right<left)throw Error('The original green symbol was not found');
  // A square viewport preserves the circles and the small period. Two source
  // pixels of bleed retain antialiased edges without visible tab-size padding.
  const side=Math.max(right-left+1,bottom-top+1)+4;
  const x=(left+right+1-side)/2,y=(top+bottom+1-side)/2;
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="${x} ${y} ${side} ${side}"><image x="0" y="0" width="${info.width}" height="${info.height}" href="data:image/png;base64,${original.toString('base64')}"/></svg>\n`;
  fs.writeFileSync(path.join(directory,'favicon.svg'),svg);
  await sharp(Buffer.from(svg)).resize(64,64).png().toFile(path.join(directory,'favicon.png'));
  console.log('Favicon viewport:',{x,y,side},'PNG: 64x64; original artwork unchanged');
})().catch(error=>{console.error(error);process.exitCode=1;});
