const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context=vm.createContext({});vm.runInContext(fs.readFileSync('trivia_app/static/question_text.js','utf8'),context);
const format=(text,names)=>context.PointsQuestion.text({text,options:names.map((text,id)=>({text,id}))});
test('two to four existing choices are omitted from the question, regardless of button order',()=>{
 for(const separator of [' or ',', ','; ',' / ',' | ']){
  assert.equal(format('Which of these players was a goalkeeper in 2023/24: Leandro Trossard'+separator+'David Raya?',['David Raya','Leandro Trossard']),'Which of these players was a goalkeeper in 2023/24?');
 }
 assert.equal(format('Which player was a goalkeeper: A, B, C or D?',['D','B','A','C']),'Which player was a goalkeeper?');
 assert.equal(format('Which player was a goalkeeper: A, B, or C?',['C','A','B']),'Which player was a goalkeeper?');
 assert.equal(format('Who scored more goals: Marcus Rashford or Wayne Rooney?',['Wayne Rooney','Marcus Rashford']),'Who scored more goals?');
});
test('punctuation inside answer labels and typographic differences are preserved',()=>{
 assert.equal(format('Which ground: St Mary\u2019s Stadium or Old Trafford?',["St Mary's Stadium",'Old Trafford']),'Which ground?');
 assert.equal(format('Which player: Pierre-Emile H\u00f8jbjerg or Emerson Royal?',['Emerson Royal','Pierre-Emile H\u00f8jbjerg']),'Which player?');
 assert.equal(format('Which colours: Black and orange or Black and white?',['Black and orange','Black and white']),'Which colours?');
 assert.equal(format('Which result: 2:1 or 3:1?',['2:1','3:1']),'Which result?');
 assert.equal(format('Which season: 2024/25 or 2025/26?',['2025/26','2024/25']),'Which season?');
 assert.equal(format('Which player: Smith or Smith Jones?',['Smith','Smith Jones']),'Which player?');
});
test('keep clues, partial lists, missing options and all unrelated questions unchanged',()=>{
 for(const text of [
  'Who won the Premier League in 2024/25?',
  'Which player: A or B in the 2023/24 season?',
  'Which player: A or missing?',
  'Which player: A?',
  'Which player: A or A?',
  'Which player: A or B or?',
  'Which player: A or B. Use only league matches.',
  'Who won 2:1 at home?',
  'What does this mean: a first-team appearance?',
 ])assert.equal(format(text,['A','B']),text);
 assert.equal(context.PointsQuestion.text(null),'');
 const question={text:'Which player: A or B?',options:[{id:'a',text:'A'},{id:'b',text:'B'}],correct:'b'};
 const before=JSON.stringify(question);assert.equal(context.PointsQuestion.text(question),'Which player?');assert.equal(JSON.stringify(question),before);
 assert.equal(format(question.text,[]),question.text);
});
