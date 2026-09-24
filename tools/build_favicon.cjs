/* Frame the white-background mark in a rounded square. SVG and PNG exports
 * share the exact same clipping geometry; black-background originals remain
 * available as source archives. Requires Sharp. */
const fs=require('node:fs'),path=require('node:path'),sharp=require('sharp');
const directory=path.resolve(__dirname,'../trivia_app/static/brand');
(async()=>{
  const original=fs.readFileSync(path.join(directory,'mark-white.png'));
  const {data,info}=await sharp(original).ensureAlpha().raw().toBuffer({resolveWithObject:true});
  let left=info.width,top=info.height,right=-1,bottom=-1;
  for(let y=0;y<info.height;y++)for(let x=0;x<info.width;x++){
    const i=(y*info.width+x)*4;
    if(data[i+3]>128&&data[i+1]>100&&data[i+1]>data[i]*2&&data[i+1]>data[i+2]*1.2){
      left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y);
    }
  }
  if(right<left)throw Error('The original green symbol was not found');
  // Minimal 1% breathing room protects the small period from the rounded
  // corner without reintroducing the old wide outer margins.
  const bounds=Math.max(right-left+1,bottom-top+1);
  const side=bounds+2*Math.ceil(bounds*.01);
  const x=(left+right+1-side)/2,y=(top+bottom+1-side)/2;
  // Corner radius is 12.5% of the tile. The transparent outer corners let the
  // same white icon work on light and dark browser chrome without black edges.
  const rounded=`x="${x}" y="${y}" width="${side}" height="${side}" rx="${side/8}"`;
  // Embed a small, high-density raster in the SVG instead of making every
  // browser tab download the full-resolution editing source.
  const thumbnail=await sharp(original).resize(256,256).png({compressionLevel:9}).toBuffer();
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="${x} ${y} ${side} ${side}"><defs><clipPath id="tile"><rect ${rounded}/></clipPath></defs><g clip-path="url(#tile)"><rect ${rounded} fill="#fff"/><image x="0" y="0" width="${info.width}" height="${info.height}" href="data:image/png;base64,${thumbnail.toString('base64')}"/></g></svg>\n`;
  fs.writeFileSync(path.join(directory,'favicon.svg'),svg);
  await sharp(Buffer.from(svg)).resize(64,64).png().toFile(path.join(directory,'favicon.png'));
  await sharp(Buffer.from(svg)).resize(180,180).png().toFile(path.join(directory,'icon-180.png'));
  // Keep the wordmark's alpha channel: it sits directly on the page, without a tile.
  await sharp(path.join(directory,'logo-transparent-source.png')).resize(432,432).png({compressionLevel:9}).toFile(path.join(directory,'logo-transparent.png'));
  console.log('Favicon viewport:',{x,y,side},'Rounded white tile; PNG: 64x64 and 180x180');
})().catch(error=>{console.error(error);process.exitCode=1;});
