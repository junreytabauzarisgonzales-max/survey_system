import {cp, mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';

const output=fileURLToPath(new URL('../dist/app/',import.meta.url));
const source=fileURLToPath(new URL('../hosted-dist/',import.meta.url));
await mkdir(output,{recursive:true});
await cp(source,output,{recursive:true});
console.log('Hosted survey interface included at /app/; public documentation stays at /.');
