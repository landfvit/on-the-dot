/* Native circles keep the supplied symbol crisp without a background tile.
 * PNG exports preserve alpha. Original user artwork is never overwritten.
 * Requires Sharp; run after changing the geometry or palette below. */
const fs=require('node:fs'),path=require('node:path'),sharp=require('sharp');
const directory=path.resolve(__dirname,'../trivia_app/static/brand');
(async()=>{
  // Match --brand-green in points_theme.css. The 108px square viewport tightly
  // frames the 3x3 grid plus the small period, with no white/black background.
  const color='#88b04b';
  const circles=[];
  for(let row=0;row<3;row++)for(let column=0;column<3;column++){
    circles.push(`<circle cx="${16+column*32}" cy="${22+row*32}" r="16"/>`);
  }
  circles.push('<circle cx="102" cy="96" r="6"/>');
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 108 108" fill="${color}">${circles.join('')}</svg>\n`;
  fs.writeFileSync(path.join(directory,'favicon.svg'),svg);
  await sharp(Buffer.from(svg)).resize(64,64).png().toFile(path.join(directory,'favicon.png'));
  await sharp(Buffer.from(svg)).resize(180,180).png().toFile(path.join(directory,'icon-180.png'));
  console.log('Transparent palette-green favicon; PNG: 64x64 and 180x180');
})().catch(error=>{console.error(error);process.exitCode=1;});
