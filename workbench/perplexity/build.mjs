import {build} from 'esbuild';
import {mkdir,readFile,writeFile,copyFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const root=path.dirname(fileURLToPath(import.meta.url));
const output=path.resolve(root,'../../static/perplexity-workbench');
await mkdir(path.join(output,'fonts'),{recursive:true});
await mkdir(path.join(output,'licenses'),{recursive:true});
await build({
  entryPoints:[path.join(root,'src/app.js')],
  outfile:path.join(output,'app.js'),
  bundle:true,
  minify:true,
  legalComments:'eof',
  target:['es2022'],
});
for(const file of ['index.html','style.css'])await copyFile(path.join(root,'src',file),path.join(output,file));
for(const weight of [400,500,700])await copyFile(
  path.join(root,`node_modules/@fontsource/manrope/files/manrope-latin-${weight}-normal.woff2`),
  path.join(output,`fonts/manrope-latin-${weight}-normal.woff2`),
);
for(const [pkg,dest] of [['three','three-MIT.txt'],['lucide','lucide-ISC.txt'],['@fontsource/manrope','manrope-OFL.txt']])
  await copyFile(path.join(root,'node_modules',pkg,'LICENSE'),path.join(output,'licenses',dest));
const pkg=JSON.parse(await readFile(path.join(root,'package.json'),'utf8'));
await writeFile(path.join(output,'build-info.json'),JSON.stringify({
  name:pkg.name,version:pkg.version,branch:'Perplexity',
  dependencies:pkg.dependencies,
  scope:'Opt-in prototype, not a replacement for ZEIM CAD or lithophane APIs.',
},null,2)+'\n');
console.log(`Built ${output}. No CDN, external font, inline-script or CSP exception required.`);
