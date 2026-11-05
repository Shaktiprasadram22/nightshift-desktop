// Prepare appearance-only JSONC edits. The Python transaction owns all writes.
const fs=require('fs');
const parser=require('jsonc-parser');
const payload=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const source=fs.readFileSync(payload.source,'utf8');
let errors=[];const current=parser.parse(source,errors,{allowTrailingComma:true});
if(errors.length || !current || typeof current!=='object' || Array.isArray(current)) throw Error('Editor settings contain invalid JSONC; nothing was applied.');
const at=(obj,keys)=>keys.reduce((value,key)=>value&&value[key],obj);
let output=source;
for(const entry of payload.entries) {
  if(!['workbench.colorCustomizations','editor.tokenColorCustomizations'].includes(entry.keys[0]) || entry.keys.length!==2) throw Error('Unexpected editor setting');
  if(payload.mode==='undo' && JSON.stringify(at(current,entry.keys))!==JSON.stringify(entry.applied)) continue;
  const value=payload.mode==='undo'?(entry.existed?entry.old:undefined):entry.value;
  output=parser.applyEdits(output,parser.modify(output,entry.keys,value,{formattingOptions:{insertSpaces:true,tabSize:4,eol:'\n'}}));
}
fs.writeFileSync(payload.output,output,{mode:0o600});
const journal=payload.entries.map(entry=>({keys:entry.keys,existed:at(current,entry.keys)!==undefined,old:at(current,entry.keys)??null,applied:entry.value}));
if(payload.journal)fs.writeFileSync(payload.journal,JSON.stringify(journal),{mode:0o600});
