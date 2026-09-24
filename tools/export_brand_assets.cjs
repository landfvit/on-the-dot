/* Deterministic exports from the editable vector logos. No raster repainting.
 * Green discs / cream glyphs: edit brand/logo.svg and brand_wordmark.html.
 * NODE_PATH=<Sharp modules> node tools/export_brand_assets.cjs */
const sharp=require('sharp'),path=require('node:path');
const root=path.resolve(__dirname,'../trivia_app/static/brand');
(async()=>{
 for(const [source,file,size] of [['logo.svg','logo-transparent.png',432],['logo.svg','logo.png',2000],['favicon.svg','mark.png',2000],['favicon.svg','favicon.png',64],['favicon.svg','icon-180.png',180]]){
  await sharp(path.join(root,source)).resize(size,size).png().toFile(path.join(root,file));
  console.log(`Exported ${file} ${size}x${size}`);
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
