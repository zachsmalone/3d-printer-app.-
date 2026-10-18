import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Mesh,Vector3} from 'three';
import {STLExporter} from 'three/addons/exporters/STLExporter.js';
import {STLLoader} from 'three/addons/loaders/STLLoader.js';
import {heightfield} from '../src/geometry.js';

function closed(g){
  const p=g.attributes.position,idx=g.index.array,edges=new Map(),winding=new Map();
  let volume=0;
  for(let i=0;i<idx.length;i+=3){
    const [a,b,c]=[idx[i],idx[i+1],idx[i+2]];
    const va=new Vector3().fromBufferAttribute(p,a),vb=new Vector3().fromBufferAttribute(p,b),vc=new Vector3().fromBufferAttribute(p,c);
    assert(new Vector3().subVectors(vb,va).cross(new Vector3().subVectors(vc,va)).lengthSq()>0,'nondegenerate triangles');
    volume+=va.dot(new Vector3().crossVectors(vb,vc))/6;
    for(const [x,y] of [[a,b],[b,c],[c,a]]){
      const key=[x,y].sort((l,r)=>l-r).join(':');
      edges.set(key,(edges.get(key)||0)+1);
      winding.set(key,(winding.get(key)||0)+(x<y?1:-1));
    }
  }
  assert([...edges.values()].every(x=>x===2),'every edge shared twice');
  assert([...winding.values()].every(x=>x===0),'consistent winding');
  assert(volume>0,'positive signed volume');
}
test('flat, gradient and stepped fields are closed and outward wound',()=>{
  for(const [nx,ny,f] of [[1,1,()=>1],[20,15,x=>.8+2.4*x/20],[160,8,x=>.4+Math.min(15,Math.floor(x/10))*.25]]){
    const g=heightfield(nx,ny,120,90,f);closed(g);g.dispose();
  }
});
test('binary STL roundtrip retains millimetre dimensions and thickness',()=>{
  const g=heightfield(40,30,150,112.5,x=>x<20?3.2:.8);
  const bytes=new STLExporter().parse(new Mesh(g),{binary:true});
  const restored=new STLLoader().parse(bytes.buffer);
  restored.computeBoundingBox();
  const size=restored.boundingBox.getSize(new Vector3());
  assert(Math.abs(size.x-150)<1e-4);assert(Math.abs(size.y-112.5)<1e-4);assert(Math.abs(size.z-3.2)<1e-4);
  const p=restored.attributes.position;
  for(let i=0;i<p.count;i++)for(const v of [p.getX(i),p.getY(i),p.getZ(i)])assert(Number.isFinite(v));
  g.dispose();restored.dispose();
});
test('black areas are thicker than white areas in monochrome mapping',()=>{
  const dark=3.2,light=.8,g=heightfield(4,2,20,10,x=>.8+(1-x/4)*(3.2-.8));
  assert(Math.abs(g.attributes.position.getZ(0)-dark)<1e-5);
  assert(Math.abs(g.attributes.position.getZ(4)-light)<1e-5);g.dispose();
});
test('invalid dimensions and zero/nonfinite thickness are rejected',()=>{
  for(const args of [[0,2,10,10,()=>1],[2,2,NaN,10,()=>1],[2,2,10,-1,()=>1],[2,2,10,10,()=>0],[2,2,10,10,()=>Infinity]])
    assert.throws(()=>heightfield(...args),RangeError);
});
