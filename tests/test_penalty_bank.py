import os
import re
import unittest
from unittest.mock import patch
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from api.penalty_bank import answer_kind,answer_pools,eligible,make_options,option_key,load_pack
from api.penalty_routes import NewGame
from trivia_app.main import app


def item(answer,topic='Unusual season counts',question='How many matches?'):
    return {'id':'TEST-001','answer':answer,'topic':topic,'question':question}


class PenaltyChoiceTests(unittest.TestCase):
    def test_numeric_boundaries_and_exact_reference(self):
        for answer in ['0','1','38','-12','0.0%','100.0%','33.3%','0.5']:
            for _ in range(20):
                q=item(answer)
                options,correct=make_options(q,{})
                self.assertEqual(len({option_key(o['text']) for o in options}),4)
                self.assertEqual(next(o['text'] for o in options if o['id']==correct),answer)
                if answer.endswith('%'):
                    self.assertTrue(all(0<=Decimal(o['text'].rstrip('%'))<=100 for o in options))

    def test_typed_candidates_and_no_alias_as_distractor(self):
        rows=[item('Manchester United'),item('Chelsea'),item('Arsenal'),item('Tottenham'),
              item('Nike','Kit manufacturers'),item('Puma','Kit manufacturers'),
              item('Adidas','Kit manufacturers'),item('Umbro','Kit manufacturers')]
        pools=answer_pools(rows)
        q=item('Manchester United');q['accepted']=['Man Utd']
        pools['club'].add('Man Utd')
        options,correct=make_options(q,pools)
        self.assertEqual(sum(option_key(o['text'])==option_key('Man Utd') for o in options),1)
        options,_=make_options(rows[-1],pools)
        self.assertTrue(all(o['text'] in pools['manufacturer'] for o in options))

    def test_scores_and_seasons(self):
        for answer in ['0–0','0–9','9–0','2025/26']:
            q=item(answer)
            options,correct=make_options(q,{})
            self.assertEqual(len({option_key(o['text']) for o in options}),4)
            self.assertEqual(options[int(correct)]['text'],answer)

    def test_special_kit_answers_and_related_colours(self):
        answers=['Black','Maroon','White','Green','100th anniversary','Ed Sheeran','Bob Paisley','Liverpool street signs']
        rows=[item(a,'Kits and design') for a in answers]+[item(a,'Managers') for a in ['Mikel Arteta','Pep Guardiola','Jürgen Klopp']]
        pools=answer_pools(rows)
        for q in rows:
            options,correct=make_options(q,pools)
            self.assertEqual(options[int(correct)]['text'],q['answer'])
            if q['answer']=='Maroon': self.assertTrue(all(o['text'] not in ('Red','Purple') for o in options))

    def test_conflicts_and_ties_excluded_but_owner_references_allowed(self):
        for status in ['matched','unsupported','incomplete']:
            self.assertTrue(eligible({'status':status,'reason':''}))
        self.assertFalse(eligible({'status':'conflict','reason':''}))
        self.assertFalse(eligible({'status':'ambiguous','reason':'Expected one answer; database candidates: A, B'}))
        self.assertTrue(eligible({'status':'ambiguous','reason':'Database player found, but reference name is not a registered alias'}))

    def test_unknown_answer_type_never_gets_random_untyped_options(self):
        with self.assertRaises(ValueError): make_options(item('Unknown text','Unknown topic'),{})

    def test_missing_general_never_falls_back_to_a_team(self):
        from fastapi import HTTPException
        with patch('api.penalty_bank.catalog',return_value=[{'id':f'bank:{uuid4()}:ARS'}]):
            with self.assertRaises(HTTPException): load_pack(None,'general')

    def test_explicit_pack_identifier_not_arbitrary_input(self):
        from pydantic import ValidationError
        self.assertEqual(NewGame().pack,'general')
        self.assertEqual(NewGame(pack=f'bank:{uuid4()}:MUN').mode,'solo')
        for value in ['random','bank:invalid:MUN',"';DELETE FROM pvp_matches"]:
            with self.assertRaises(ValidationError): NewGame(pack=value)


class PenaltiesOnlyAccessTests(unittest.TestCase):
    def setUp(self):
        env=patch.dict(os.environ,{'TRIVIA_EDITOR_USERNAME':'editor','TRIVIA_EDITOR_PASSWORD':'long-local-test-password'})
        env.start();self.addCleanup(env.stop)
        self.client=TestClient(app)
        self.auth=('editor','long-local-test-password')

    def test_public_home_and_navigation_are_penalties_only(self):
        for path in ['/','/penalties']:
            r=self.client.get(path)
            self.assertEqual(r.status_code,200)
            self.assertIn('solo-penalties',r.text)
            self.assertIn('penalty_scene.js',r.text)
            self.assertNotIn('>Solo quizzes</a>',r.text)
            self.assertIn('<html lang="en">',r.text)
            for label in ['Private PvP','Category','Difficulty','Next shot','Ready to shoot']:
                self.assertIn(label,r.text)
            for link in ['/internal/trivia','href="/quizzes"','href="/trivia"']:
                self.assertNotIn(link,r.text)

    def test_all_other_api_routes_require_editor(self):
        count=0
        for route,methods in app.openapi()['paths'].items():
            if not route.startswith('/api/') or route.startswith(('/api/penalties/','/api/players/')) or (route.startswith('/api/solo/') and not route.startswith('/api/solo/editor/')):
                continue
            path=re.sub(r'\{[^}]+\}',str(uuid4()),route)
            for method in methods:
                with self.subTest(path=route,method=method):
                    response=self.client.request(method,path,json={})
                    self.assertEqual(response.status_code,401,response.text)
                    self.assertEqual(response.headers['cache-control'],'no-store')
                    count+=1
        self.assertGreater(count,25)

    def test_private_pages_and_assets_are_not_public_backdoors(self):
        for path in ['/quizzes','/trivia','/internal/trivia','/internal/trivia/bank']:
            self.assertEqual(self.client.get(path,follow_redirects=False).status_code,303)
            response=self.client.get(path,auth=self.auth)
            self.assertEqual(response.status_code,200)
            self.assertIn('Sign out',response.text)
        for path in ['/trivia-assets/bank.js','/trivia-assets/training.js','/trivia-assets/play.js','/assets/js/trivia.js']:
            self.assertEqual(self.client.get(path).status_code,401)
            self.assertEqual(self.client.get(path,auth=self.auth).status_code,200)
        for path in ['/trivia-assets/app.css','/trivia-assets/penalties.css','/trivia-assets/penalties.js','/trivia-assets/penalty_scene.js']:
            self.assertEqual(self.client.get(path).status_code,200)

    def test_fail_closed_without_editor_configuration(self):
        with patch.dict(os.environ,{'TRIVIA_EDITOR_PASSWORD':''}):
            self.assertEqual(self.client.get('/').status_code,200)
            for path in ['/api/trivia/play/questions','/api/trivia/play/quizzes','/trivia-assets/bank.js','/internal/trivia']:
                self.assertEqual(self.client.get(path).status_code,404)
