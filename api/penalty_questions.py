"""Frozen four-option packs. No LLM or external API in a running match."""
from decimal import Decimal
import secrets
from api.numeric_choices import options as numeric_options


def options(value,step=1,suffix=''):
    return numeric_options(f'{Decimal(str(value)):f}{suffix}', minimum_step=step)


def maths_examples(i):
    return [
            (f'A team won {i} of 25 matches. What is its win rate?',i*4,4,' %',f'{i} / 25 x 100 = {i*4} %.'),
            (f'A team has {i} win{"s" if i!=1 else ""} and 3 draws. How many points has it earned?',i*3+3,3,'',f'{i} x 3 + 3 = {i*3+3} points.'),
            (f'A team scored {i*3} goals in 6 matches. What is its average goals per match?',Decimal(i)/2,Decimal('.5'),'',f'{i*3} / 6 = {i/2:g}.'),
            (f'A team played 24 matches and conceded in {i} of them. How many clean sheets did it keep?',24-i,1,'',f'24 - {i} = {24-i}.')]


def english_maths_view(question, key):
    # Translate legacy match wording without changing its frozen choices or answer.
    parts=key.split(':')
    if len(parts)!=3 or parts[0]!='maths-v1' or parts[1] not in ('0','1','2','3'):
        return question
    if parts[2] not in {str(i) for i in range(1,21)}:
        return question
    example=maths_examples(int(parts[2]))[int(parts[1])]
    result={**question,'text':example[0]}
    if 'explanation' in question:result['explanation']=example[4]
    return result


def maths_pack():
    questions=[]
    for i in range(1,21):
        for kind,(text,value,step,suffix,explanation) in enumerate(maths_examples(i)):
            choices,correct=options(value,step,suffix)
            questions.append({'key':f'maths-v1:{kind}:{i}','text':text,'options':choices,'correct':correct,
                'explanation':explanation,'source':'Deterministic arithmetic; model examples, not club records.', 'group':kind})
    # Pair questions of the same kind, then randomise pair order for equal roles.
    pairs=[]
    for kind in range(4):
        group=[q for q in questions if q['group']==kind];secrets.SystemRandom().shuffle(group)
        pairs.extend([group[i:i+2] for i in range(0,len(group),2)])
    secrets.SystemRandom().shuffle(pairs)
    return [q for pair in pairs for q in pair]


def library_pack(conn):
    rows=conn.execute("""SELECT DISTINCT ON(question_id) version_id,question_text,answer,question_id
        FROM trivia_question_versions WHERE state='published' AND verified_at IS NOT NULL
        ORDER BY question_id,revision DESC""").fetchall()
    result=[]
    for row in rows:
        answer=row['answer']
        if answer.get('kind') not in ('integer','decimal','percentage') or answer.get('value') is None:continue
        value=Decimal(str(answer['value']));step=Decimal(1).scaleb(-answer.get('rounding_decimals',0))
        choices,correct=options(value,step,' %' if answer['kind']=='percentage' else '')
        result.append({'key':str(row['version_id']),'text':row['question_text'],'options':choices,
            'correct':correct,'explanation':f"{value:g}"+(' %' if answer['kind']=='percentage' else ''),
            'source':'Verified published POINTS question version '+str(row['version_id'])})
    secrets.SystemRandom().shuffle(result)
    return result
