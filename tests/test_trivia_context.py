from datetime import datetime,timezone,timedelta
import unittest
from uuid import uuid4
from PIL import Image
from pydantic import ValidationError
from api.trivia_models import TriviaSpec,WeatherFilter
from api.trivia_context import weather_problem,filter_weather
from api.trivia_engine import aggregate
from kits.colours import dominant_colour,colour_family,colour_description,COLOURS
from api.trivia import grade_answer
from api.trivia_models import GradeAnswer


class ContextTests(unittest.TestCase):
    def test_two_colour_policy_is_versioned_and_keeps_v1_unchanged(self):
        image=Image.new('RGBA',(38,59),'black');image.paste('orange',(3,12,19,54))
        self.assertEqual(dominant_colour(image)['status'],'multicolour')
        result=colour_description(image)
        self.assertEqual(result['method'],'shirt-torso-colours-v2')
        self.assertEqual(result['colours'],['black','orange'])
        self.assertEqual(result['label'],'Black and orange')
        image.paste('black',(3,12,35,54));image.paste('orange',(3,12,6,54))
        self.assertEqual(colour_description(image)['colours'],['black'])

    def test_colour_combination_grading_requires_every_colour_in_any_order(self):
        answer={'grading_policy':'colour-set-v2','colour_components':[{'key':c,'aliases':COLOURS[c][2]} for c in ['black','orange']]}
        for value in ['black and orange','orange and black','black & orange','orange, black','cerna a oranzova','\u010dern\u00e1 a oran\u017eov\u00e1']:
            with self.subTest(value=value):self.assertTrue(grade_answer(answer,GradeAnswer(text=value))['correct'])
        for value in ['black','orange','black and red','black and orange and white','black and black and orange']:
            with self.subTest(value=value):self.assertFalse(grade_answer(answer,GradeAnswer(text=value))['correct'])
        self.assertFalse(grade_answer(answer,GradeAnswer(value=0))['correct'])

    def test_v3_keeps_clear_primary_colours_and_flags_tonal_ambiguity(self):
        image=Image.new('RGBA',(38,59),'red');image.paste('orange',(3,12,15,54))
        self.assertEqual(colour_description(image,'v2')['colours'],['orange','red'])
        self.assertEqual(colour_description(image,'v3')['colours'],['red'])
        image=Image.new('RGBA',(38,59),'black');image.paste('grey',(3,12,13,54));image.paste('white',(13,12,23,54))
        self.assertEqual(colour_description(image,'v3')['status'],'multicolour')
        self.assertEqual(colour_description(image,'v3')['colours'],[])

    def setUp(self):
        self.kit={'template':'kit_colour','league_id':39,'team_id':33,'period':{'mode':'seasons','seasons':[2024]},
            'context_id':uuid4(),'kit_type':'third','minimum_sample':1}

    def test_kit_requires_one_exact_season_and_no_match_filters(self):
        self.assertEqual(TriviaSpec(**self.kit).kit_type,'third')
        for fields in [{'context_id':None},{'kit_type':None},{'period':{'mode':'all'}},
                {'period':{'mode':'seasons','seasons':[2023,2024]}},{'minimum_sample':10},{'venue':'away'},
                {'weather':{'metric':'temperature_c','operator':'gt','value':5}}]:
            with self.subTest(fields=fields),self.assertRaises(ValidationError):TriviaSpec(**{**self.kit,**fields})

    def test_weather_filter_bounds_and_unsupported_combinations(self):
        for fields in [{'metric':'precipitation_mm','operator':'gt','value':-1},
                {'metric':'temperature_c','operator':'gt','value':float('nan')},
                {'metric':'temperature_c','operator':'gt','value':61}]:
            with self.assertRaises(ValidationError):WeatherFilter(**fields)
        with self.assertRaises(ValidationError):
            TriviaSpec(template='top_scorer',league_id=39,period={'mode':'all'},context_id=uuid4(),
                weather={'metric':'temperature_c','operator':'gt','value':0})

    def test_shirt_colour_excludes_collar_outline_and_rejects_ties(self):
        image=Image.new('RGBA',(38,59),'black')
        image.paste('white',(3,12,35,54))
        self.assertEqual(dominant_colour(image)['colour'],'white')
        image.paste('red',(3,12,19,54))
        result=dominant_colour(image)
        self.assertEqual(result['status'],'multicolour')
        self.assertIsNone(result['colour'])
        self.assertEqual(dominant_colour(Image.new('RGBA',(38,59),(0,0,0,0)))['status'],'incomplete_pixels')
        self.assertEqual(colour_family((0,26,103)),'navy')

    def test_weather_requires_matching_time_units_model_and_finite_values(self):
        kickoff=datetime(2024,8,16,19,tzinfo=timezone.utc)
        row={'kickoff_at':kickoff.isoformat(),'sampled_at':kickoff.isoformat(),'model':'ERA5',
            'temperature_c':10,'precipitation_mm':0,'raw_payload':{'hourly_units':{'temperature_2m':'\u00b0C','precipitation':'mm'}}}
        self.assertIsNone(weather_problem(row,kickoff,'temperature_c'))
        for fields in [{'kickoff_at':(kickoff+timedelta(hours=1)).isoformat()},
                {'sampled_at':(kickoff+timedelta(minutes=31)).isoformat()}, {'model':'forecast'},
                {'temperature_c':None},{'temperature_c':float('inf')},{'raw_payload':{}}]:
            with self.subTest(fields=fields):self.assertIsNotNone(weather_problem({**row,**fields},kickoff,'temperature_c'))

    def test_missing_weather_is_excluded_not_dry_and_conditions_intersect(self):
        kickoff=datetime(2024,8,16,19,tzinfo=timezone.utc)
        weather={'kickoff_at':kickoff.isoformat(),'sampled_at':kickoff.isoformat(),'model':'ERA5',
            'precipitation_mm':0,'raw_payload':{'hourly_units':{'precipitation':'mm'}}}
        rows=[{'fixture_id':i,'match_date':kickoff,'result_valid':True,'timeline_valid':True,'reasons':[],
            'checkpoint_for':0,'checkpoint_against':2,'result':'W','goals_for':3,'goals_against':2} for i in (1,2,3)]
        context={'payload':{'weather':{'1':weather,'2':{**weather,'precipitation_mm':1}}}}
        spec=TriviaSpec(template='conditional_win_rate',league_id=39,team_id=33,period={'mode':'all'},minimum_sample=1,
            condition={'minute':80,'goal_difference':-2},context_id=uuid4(),weather={'metric':'precipitation_mm','operator':'gt','value':0})
        filter_weather(rows,context,spec.weather)
        result=aggregate(spec,rows)
        self.assertEqual([r['disposition'] for r in result['evidence']],['not_matched','matched','excluded'])
        self.assertEqual(result['answer']['denominator'],1)
        self.assertFalse(result['coverage']['publishable'])
        self.assertIn('missing_weather',result['coverage']['exclusions'])
