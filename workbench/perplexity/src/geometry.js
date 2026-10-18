import {BufferGeometry,BufferAttribute} from 'three';

/** Closed Z-up heightfield in millimetres. Optical calibration is not implied. */
export function heightfield(nx,ny,w,h,getHeight){
  if(!Number.isInteger(nx)||!Number.isInteger(ny)||nx<1||ny<1||nx>1024||ny>1024)
    throw new RangeError('Grid dimensions must be integers from 1 to 1024.');
  if(!Number.isFinite(w)||!Number.isFinite(h)||w<=0||h<=0||typeof getHeight!=='function')
    throw new RangeError('Use finite positive panel dimensions and a height function.');
  const n=(nx+1)*(ny+1),pos=new Float32Array(n*6),indices=[];
  for(let y=0;y<=ny;y++)for(let x=0;x<=nx;x++){
    const i=y*(nx+1)+x,t=getHeight(x,y);
    if(!Number.isFinite(t)||t<=0)throw new RangeError('Thickness must be finite and greater than zero.');
    pos[i*3]=x/nx*w-w/2;pos[i*3+1]=y/ny*h-h/2;pos[i*3+2]=t;
    pos[(n+i)*3]=pos[i*3];pos[(n+i)*3+1]=pos[i*3+1];pos[(n+i)*3+2]=0;
  }
  for(let y=0;y<ny;y++)for(let x=0;x<nx;x++){
    const a=y*(nx+1)+x,b=a+1,d=a+nx+1,c=d+1;
    indices.push(a,b,c,a,c,d,n+a,n+c,n+b,n+a,n+d,n+c);
  }
  const boundary=[];
  for(let x=0;x<=nx;x++)boundary.push(x);
  for(let y=1;y<=ny;y++)boundary.push(y*(nx+1)+nx);
  for(let x=nx-1;x>=0;x--)boundary.push(ny*(nx+1)+x);
  for(let y=ny-1;y>0;y--)boundary.push(y*(nx+1));
  for(let i=0;i<boundary.length;i++){
    const a=boundary[i],b=boundary[(i+1)%boundary.length];
    indices.push(a,n+b,b,a,n+a,n+b);
  }
  const g=new BufferGeometry();g.setAttribute('position',new BufferAttribute(pos,3));
  g.setIndex(indices);g.computeVertexNormals();return g;
}
