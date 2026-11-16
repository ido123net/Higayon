import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
// Load the actual browser modules without introducing a JS build pipeline.
const moduleOf = async name => import(`data:text/javascript;base64,${Buffer.from(await readFile(new URL(`../static/${name}`,import.meta.url))).toString('base64')}`);
const {letters,progress}=await moduleOf('storage.js');
const {advance,writeWord,erase}=await moduleOf('navigation.js');
test('Hebrew normalization and paste filters',()=>assert.deepEqual(letters('ךםןףץ abc 123!'),[...'כמנפצ']));
test('word boundaries, overwrite and erase',()=>{const cells=[[0,10],[0,9],[0,8]],values={};let i=writeWord(values,cells,0,[...'אבגד']);assert.equal(i,2);assert.deepEqual(values,{'0,10':'א','0,9':'ב','0,8':'ג'});assert.equal(advance(2,3),2);i=erase(values,cells,i);assert.equal(i,2);i=erase(values,cells,i);assert.equal(i,1);assert.equal(values['0,9'],undefined);});
test('separate accounts and puzzles, restore, reject invalid cells',()=>{const data=new Map(),storage=()=>({getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v)}),cells=new Set(['0,10']),warnings=[];const a=progress('a','one',cells,v=>warnings.push(v),storage);a.save({'0,10':'ך','9,9':'א'});assert.deepEqual(a.load(),{'0,10':'כ'});assert.deepEqual(progress('b','one',cells,()=>{},storage).load(),{});assert.deepEqual(progress('a','two',cells,()=>{},storage).load(),{});assert.equal(warnings.length,0);});
test('unavailable storage reports a Hebrew message',()=>{const warnings=[],p=progress('a','one',new Set(),s=>warnings.push(s),()=>{throw Error();});assert.deepEqual(p.load(),{});p.save({});assert.equal(warnings.length,2);assert.match(warnings[0],/לא ניתן/);});
