const fs = require('node:fs/promises');
const path = require('node:path');
async function main() {
  const dest = path.join(__dirname, '../public/vendor');
  await fs.mkdir(dest, {recursive:true});
  for (const file of ['tesseract.min.js','worker.min.js']) await fs.copyFile(path.join(__dirname,'../node_modules/tesseract.js/dist',file),path.join(dest,file));
  await fs.mkdir(path.join(dest,'core'),{recursive:true});
  for (const file of await fs.readdir(path.join(__dirname,'../node_modules/tesseract.js-core'))) if (/\.wasm(\.js)?$/.test(file)) await fs.copyFile(path.join(__dirname,'../node_modules/tesseract.js-core',file),path.join(dest,'core',file));
  await fs.copyFile(path.join(__dirname,'../node_modules/tesseract.js/LICENSE.md'),path.join(dest,'TESSERACT-LICENSE'));
  await fs.mkdir(path.join(dest,'lang'),{recursive:true});
  await fs.copyFile(path.join(__dirname,'../node_modules/@tesseract.js-data/eng/4.0.0_best_int/eng.traineddata.gz'),path.join(dest,'lang/eng.traineddata.gz'));
  console.log('OCR assets ready; image recognition runs locally in the browser.');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
