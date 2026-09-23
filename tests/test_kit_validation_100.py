"""100 named checks: data integrity, synthetic pixels, grading and import safety.

These are not 100 independently verified historical product descriptions.
Expected pixel colours and accepted answers below are explicit test oracles.
"""
import csv
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
from pydantic import ValidationError
import requests

from api.trivia import grade_answer
from api.trivia_models import GradeAnswer,TriviaSpec
from kits.colours import COLOURS,colour_description
from src.kit_colour_report import create_records,measure

ROOT=Path(__file__).resolve().parents[1]
CASES=[]


def case(group,name,check):
    CASES.append((group,name,check))


def season_check(year):
    def check(test):
        rows=[r for r in test.report['rows'] if r['season']==year]
        test.assertEqual(len(rows),20)
        test.assertEqual(len({r['team'] for r in rows}),20)
        csv_rows={r['team']:r for r in test.csv_rows if r['season']==f'{year}/{str(year+1)[-2:]}'}
        test.assertEqual(set(csv_rows),{r['team'] for r in rows})
        for row in rows:
            test.assertNotIn(row['team'],('Aston Vila','Tottenham Hotpsur'))
            test.assertEqual(set(row['kits']),{'home','away','third'})
            test.assertRegex(row['source_url'],r'^https://commons\.wikimedia\.org/w/index\.php\?oldid=\d+$')
            for kind,record in row['kits'].items():
                test.assertEqual(csv_rows[row['team']][kind+'_status'],record['status'])
                if record['status']=='available':
                    test.assertTrue(record['label'])
                    test.assertEqual(csv_rows[row['team']][kind],record['label'])
                    test.assertRegex(record['pixel_sha256'],r'^[a-f0-9]{64}$')
                    test.assertTrue(1<=len(record['colours'])<=3)
                    test.assertAlmostEqual(sum(p['share'] for p in record['palette']),1,places=3)
                else:
                    test.assertIsNone(record['label'])
                    test.assertEqual(record['colours'],[])
    return check


for year in range(1999,2027):case('season_integrity',str(year),season_check(year))

SWATCHES={'white':'#ffffff','black':'#000000','grey':'#888888','red':'#ff0000',
    'blue':'#2477cc','navy':'#14244a','green':'#23804d','yellow':'#ffff00',
    'orange':'#ff8800','pink':'#ee86ad','purple':'#8153a3','brown':'#795038','maroon':'#782333'}


def solid_check(key,hex_colour):
    def check(test):
        result=colour_description(Image.new('RGBA',(38,59),hex_colour),'v3')
        test.assertEqual(result['status'],'available')
        test.assertEqual(result['colours'],[key])
        test.assertEqual(result['palette'],[{'colour':key,'share':1.0}])
    return check


for key,value in SWATCHES.items():case('solid_pixels',key,solid_check(key,value))


def combination_check(left,right):
    def check(test):
        image=Image.new('RGBA',(38,59),SWATCHES[left])
        image.paste(SWATCHES[right],(19,12,35,54))
        result=colour_description(image,'v3')
        test.assertEqual(result['status'],'available')
        test.assertEqual(result['colours'],sorted([left,right]))
        test.assertIsNone(result['colour'])
    return check


for left,right in [('black','orange'),('black','red'),('blue','white'),('red','white'),
        ('green','white'),('yellow','black'),('purple','white'),('black','white'),
        ('green','yellow'),('red','blue'),('orange','white'),('red','yellow')]:
    case('combined_pixels',left+'_'+right,combination_check(left,right))


def edge_check(name):
    def check(test):
        image=Image.new('RGBA',(38,59),'red')
        expected=['red'];status='available'
        if name=='transparent':
            image.putpixel((10,20),(255,0,0,0));expected=[];status='incomplete_pixels'
        elif name=='wrong_dimensions':
            with test.assertRaises(ValueError):colour_description(Image.new('RGB',(59,38)),'v3')
            return
        elif name=='collar_excluded':image.paste('black',(0,0,38,12))
        elif name=='minor_stripe':image.paste('orange',(3,12,6,54))
        elif name=='three_colours':
            image.paste('white',(3,12,13,54));image.paste('blue',(13,12,24,54))
            expected=['blue','red','white']
        elif name=='blue_navy_ambiguity':
            image=Image.new('RGBA',(38,59),SWATCHES['blue']);image.paste(SWATCHES['navy'],(19,12,35,54))
            expected=[];status='multicolour'
        elif name=='neutral_shading_ambiguity':
            image=Image.new('RGBA',(38,59),'black');image.paste('grey',(3,12,13,54));image.paste('white',(13,12,24,54))
            expected=[];status='multicolour'
        elif name=='outside_torso_excluded':
            image=Image.new('RGBA',(38,59),(0,0,0,0));image.paste('red',(3,12,35,54))
        result=colour_description(image,'v3')
        test.assertEqual(result['status'],status);test.assertEqual(result['colours'],expected)
    return check


for name in ['transparent','wrong_dimensions','collar_excluded','minor_stripe','three_colours',
        'blue_navy_ambiguity','neutral_shading_ambiguity','outside_torso_excluded']:
    case('pixel_boundaries',name,edge_check(name))

GRADES=[('english','black and orange',True),('reversed','orange and black',True),
    ('ampersand','black & orange',True),('comma','orange, black',True),('slash','black/orange',True),
    ('plus','orange + black',True),('czech','cerna a oranzova',True),
    ('czech_accents','\u010dern\u00e1 a oran\u017eov\u00e1',True),('uppercase','BLACK AND ORANGE',True),
    ('whitespace','  black   and   orange  ',True),('mixed_language','black a oranzova',True),
    ('czech_reverse','oranzova a cerna',True),('missing_orange','black',False),
    ('missing_black','orange',False),('wrong_second','black and red',False),
    ('extra_colour','black and orange and white',False),('duplicate_black','black and black',False),
    ('duplicate_orange','orange and orange',False),('extra_duplicate','black and orange and black',False),
    ('negated','not black and orange',False),('substring','blackish and orange',False),
    ('trailing_separator','black and orange and',False),('no_separator','black orange',False),
    ('numeric',0,False)]


def grade_check(value,expected):
    def check(test):
        answer={'grading_policy':'colour-set-v2','colour_components':[
            {'key':c,'aliases':COLOURS[c][2]} for c in ['black','orange']]}
        response=GradeAnswer(value=value) if isinstance(value,int) else GradeAnswer(text=value)
        test.assertEqual(grade_answer(answer,response)['correct'],expected)
    return check


for name,value,expected in GRADES:case('answer_grading',name,grade_check(value,expected))

INVALID_SPECS=[('missing_context',{'context_id':None}),('missing_team',{'team_id':None}),
    ('missing_kit',{'kit_type':None}),('unknown_kit',{'kit_type':'fourth'}),
    ('implicit_seasons',{'period':{'mode':'all'}}),
    ('multiple_seasons',{'period':{'mode':'seasons','seasons':[2023,2024]}}),
    ('duplicate_seasons',{'period':{'mode':'seasons','seasons':[2024,2024]}}),
    ('match_venue',{'venue':'away'}),('match_sample',{'minimum_sample':10}),
    ('match_weather',{'weather':{'metric':'temperature_c','operator':'gt','value':10}})]


def spec_check(fields):
    def check(test):
        base={'template':'kit_colour','league_id':39,'team_id':33,'kit_type':'third',
            'context_id':'11111111-1111-4111-8111-111111111111',
            'period':{'mode':'seasons','seasons':[2024]},'minimum_sample':1}
        with test.assertRaises(ValidationError):TriviaSpec(**{**base,**fields})
    return check


for name,fields in INVALID_SPECS:case('specification_guards',name,spec_check(fields))


def import_check(name):
    def check(test):
        kit={'type':'home','layers':[]}
        page={'season':2024,'revid':123,'retrieved_at':'test','local_teams':[('Test FC',[kit])]}
        if name=='missing_set':
            result=create_records([page])[0]['kits']['third']
            test.assertEqual(result['status'],'not_listed');test.assertIsNone(result['label'])
        elif name=='ambiguous_layout':
            test.assertEqual(measure(kit)['status'],'ambiguous_source_layout')
        elif name=='duplicate_set':
            page['local_teams'][0][1].append(dict(kit))
            test.assertEqual(create_records([page])[0]['kits']['home']['status'],'multiple_source_variants')
        else:
            page['local_teams'][0][1].extend([{'type':'away'},{'type':'third'}])
            attempts=[];errors=[]
            def measured(kit,download=False):
                if download:
                    attempts.append(kit['type'])
                    if name=='rate_limit_stops_batch':
                        response=requests.Response();response.status_code=429;response.headers['Retry-After']='3600'
                        raise requests.HTTPError('rate limited',response=response)
                    return {'status':'available','label':'Red','colours':['red']}
                return {'status':'missing_pixels','label':None,'colours':[]}
            with patch('src.kit_colour_report.measure',side_effect=measured),patch('src.kit_colour_report.time.sleep'):
                rows=create_records([page],download_limit=1 if name=='bounded_batch' else 20,download_errors=errors)
            test.assertEqual(attempts,['home'])
            test.assertEqual(rows[0]['kits']['away']['status'],'missing_pixels')
            if name=='rate_limit_stops_batch':
                test.assertEqual(errors[0]['status_code'],429)
                test.assertEqual(errors[0]['retry_after'],'3600')
                test.assertEqual(errors[0]['kit_type'],'home')
            else:test.assertEqual(errors,[])
    return check


for name in ['missing_set','ambiguous_layout','duplicate_set','rate_limit_stops_batch','bounded_batch']:
    case('import_safety',name,import_check(name))


class KitValidation100(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((ROOT/'reports/kits/pl_kit_colours.json').read_text())
        with (ROOT/'reports/kits/pl_kit_colours.csv').open(encoding='utf-8-sig',newline='') as stream:
            cls.csv_rows=list(csv.DictReader(stream))


assert len(CASES)==100
for number,(group,name,check) in enumerate(CASES,1):
    check.__doc__=f'{group}: {name}'
    setattr(KitValidation100,f'test_{number:03d}_{group}_{name}',check)
