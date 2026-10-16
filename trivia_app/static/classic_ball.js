/* A classic stitched football: 12 black pentagons and 20 white hexagons.
 * Truncate Three's regular icosahedron. Physics still lives in stadium_scene.
 * The small framebuffer gives the rotating geometry a pixel-art silhouette.
 */
import * as THREE from './vendor/three/three.module.min.js';

export function classicFootball(radius) {
  const ico=new THREE.IcosahedronGeometry(1,0),source=ico.attributes.position;
  const vertices=[],triangles=[],neighbours=[];
  for(let i=0;i<source.count;i+=3){
    const face=[];
    for(let j=0;j<3;j++){
      const point=new THREE.Vector3().fromBufferAttribute(source,i+j);
      let index=vertices.findIndex(v=>v.distanceToSquared(point)<1e-8);
      if(index<0){index=vertices.length;vertices.push(point);neighbours.push(new Set());}
      face.push(index);
    }
    triangles.push(face);
    for(let j=0;j<3;j++){
      neighbours[face[j]].add(face[(j+1)%3]);
      neighbours[face[j]].add(face[(j+2)%3]);
    }
  }
  ico.dispose();
  const edge=(a,b)=>vertices[a].clone().multiplyScalar(2).add(vertices[b]).divideScalar(3);
  const scale=radius/edge(0,[...neighbours[0]][0]).length();
  const positions=[],colors=[],light=new THREE.Vector3(-1,3,-2).normalize();
  function panel(points,black){
    const centre=points.reduce((sum,p)=>sum.add(p),new THREE.Vector3()).divideScalar(points.length);
    const normal=centre.clone().normalize();
    const tangent=points[0].clone().sub(centre).normalize();
    const bitangent=new THREE.Vector3().crossVectors(normal,tangent);
    points.sort((a,b)=>Math.atan2(a.clone().sub(centre).dot(bitangent),a.clone().sub(centre).dot(tangent))-
      Math.atan2(b.clone().sub(centre).dot(bitangent),b.clone().sub(centre).dot(tangent)));
    const shade=.88+.12*Math.max(0,normal.dot(light));
    const color=new THREE.Color(black?0x171b18:0xffffff).multiplyScalar(shade);
    for(let i=0;i<points.length;i++)for(const p of [centre,points[i],points[(i+1)%points.length]]){
      positions.push(...p.clone().multiplyScalar(scale).toArray());colors.push(color.r,color.g,color.b);
    }
  }
  for(const [a,b,c] of triangles)panel([edge(a,b),edge(b,a),edge(b,c),edge(c,b),edge(c,a),edge(a,c)],false);
  vertices.forEach((_,a)=>panel([...neighbours[a]].map(b=>edge(a,b)),true));
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  geometry.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));
  const mesh=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({vertexColors:true}));
  mesh.name='classic-black-white-football';
  return mesh;
}
