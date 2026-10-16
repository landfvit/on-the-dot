const test=require('node:test'),assert=require('node:assert/strict');
test('approved ball has 12 black pentagons and 20 white hexagons',async()=>{
  const {classicFootball}=await import('../trivia_app/static/classic_ball.js');
  const {Vector3}=await import('../trivia_app/static/vendor/three/three.module.min.js');
  const radius=.28,ball=classicFootball(radius),positions=ball.geometry.attributes.position,colors=ball.geometry.attributes.color;
  assert.equal(ball.name,'classic-black-white-football');assert.equal(positions.count,540);
  let black=0,white=0,maxRadius=0;
  for(let i=0;i<positions.count;i+=3){
    const points=[0,1,2].map(j=>new Vector3().fromBufferAttribute(positions,i+j));
    const normal=points[1].clone().sub(points[0]).cross(points[2].clone().sub(points[0]));
    assert(normal.dot(points[0])>0,'Every panel faces outwards');
    maxRadius=Math.max(maxRadius,...points.map(p=>p.length()));
    if(colors.getX(i)<.1)black++;else white++;
  }
  assert.equal(black,12*5);assert.equal(white,20*6);assert(Math.abs(maxRadius-radius)<1e-7);
  ball.geometry.dispose();ball.material.dispose();
});
