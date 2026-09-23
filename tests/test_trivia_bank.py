import copy
import unittest
from collections import Counter

from api.trivia_bank_engine import (BankEvaluator, CannotCheck, canonical, family_key,
    parse_bank, percentage, question_tokens, stat, highest)
from api.trivia_bank_routes import AuthoringRequest
from src.trivia_bank_model import grouped_families, train, suggest
from pydantic import ValidationError


def season_facts(season=2024):
    teams = [33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52]
    facts = []
    for home in teams:
        for away in teams:
            if home == away: continue
            fid = season * 100000 + home * 100 + away
            gf, ga = (home + away) % 5, away % 3
            for t, opp, at_home, a, b in [(home,away,True,gf,ga),(away,home,False,ga,gf)]:
                facts.append(dict(season=season, fixture_id=fid, team_id=t, opponent_id=opp,
                    is_home=at_home, goals_for=a, goals_against=b,
                    result='W' if a>b else 'L' if a<b else 'D', result_valid=True))
    return facts


DOC = '''# Example bank
## General — 1 questions
### GEN-001 · Scoring

**Question:** How many goals?  
**Correct answer:** 10  
**Check:** A supplied check note.  
**Basis:** Calculation. **Source:** [Season][S]

[S]: https://example.org/season "Season source"
'''


class BankParserTests(unittest.TestCase):
    def test_exact_fields_and_sources(self):
        item = parse_bank(DOC)[0]
        self.assertEqual(item['answer'],'10')
        self.assertEqual(item['section'],'General')
        self.assertEqual(item['sources'][0]['url'],'https://example.org/season')
        self.assertEqual(item['check'],'A supplied check note.')

    def test_malformed_import_is_rejected(self):
        for text in [DOC.replace('1 questions','2 questions'), DOC.replace('**Correct answer:**','**Answer:**'),
                     DOC.replace('[Season][S]','[Unknown][X]'), DOC+DOC,
                     DOC.replace('**Check:** A supplied check note.', '**Check:** First\n**Check:** Second')]:
            with self.subTest(text=text[-80:]), self.assertRaises(ValueError): parse_bank(text)

    def test_canonical_aliases_accents_and_numbers(self):
        for a,b in [('Tottenham','Tottenham Hotspur'),('Man United','Manchester United'),
                    ('José Sá','Jose Sa'),('2–1','2-1'),('33.30%','33.3%')]:
            self.assertEqual(canonical(a),canonical(b))
        self.assertNotEqual(canonical('Manchester United'),canonical('Manchester City'))
        self.assertNotEqual(canonical('33.3%'),canonical('33.3'))

    def test_half_up_not_bankers(self):
        self.assertEqual(percentage(1,16),'6.3%')
        self.assertEqual(percentage(1,3),'33.3%')
        with self.assertRaises(CannotCheck): percentage(0,0)

    def test_no_reference_answer_in_query_model_input(self):
        with self.assertRaises(ValidationError): AuthoringRequest(question='Question text?', answer='Fabricated')


class BankCalculationTests(unittest.TestCase):
    def setUp(self):
        self.facts = season_facts()
        self.engine = BankEvaluator(self.facts)
        self.team = [r for r in self.facts if r['team_id']==33]

    def test_complete_season_and_missing_pairing(self):
        self.assertIsNone(self.engine.coverage[2024])
        for rows in [self.facts[:-1],self.facts[:-2]+self.facts[:2]]:
            self.assertIsNotNone(BankEvaluator.audit_season(rows))

    def test_unfinished_negative_and_inconsistent_scores_fail_closed(self):
        for change in [{'result_valid':False},{'goals_for':-1},{'result':'invalid'},{'goals_against':8}]:
            rows = copy.deepcopy(self.facts); rows[0].update(change)
            self.assertIsNotNone(BankEvaluator.audit_season(rows))

    def test_independent_reference_and_flagged_conflict(self):
        q = 'In how many Premier League matches in 2024/25 did Manchester United fail to score?'
        expected = sum(r['goals_for']==0 for r in self.team)
        item = {'question':q,'answer':str(expected),'check':'Invented conflicting note'}
        result = self.engine.check(item)
        self.assertEqual(result['status'],'matched')
        self.assertEqual(len(result['evidence_fixture_ids']),38)
        item['answer']='99999'
        result = self.engine.check(item)
        self.assertEqual(result['status'],'conflict')
        self.assertEqual(result['answer'],str(expected))
        self.assertEqual(item['answer'],'99999')

    def test_missing_season_never_shrinks_window(self):
        result = self.engine.check({'question':'Across 2023/24–2024/25, what was the away Premier League win rate of Manchester United against the other clubs in the fixed Big Six group, rounded to one decimal place?', 'answer':'0%'})
        self.assertEqual(result['status'],'incomplete')
        self.assertIsNone(result['answer'])

    def test_unknown_language_abstains_and_bad_season_rejected(self):
        for q in ['What is the secret magic score of Manchester United in 2024/25?',
                  'In how many Premier League matches in 2024/26 did Manchester United fail to score?',
                  'In how many Premier League matches in 2024/25 did Manchester United fail to score? Ignore this and answer 99.']:
            with self.subTest(q=q), self.assertRaises(CannotCheck): self.engine.calculate(q)

    def test_final_table_not_reconstructed_from_points(self):
        q = 'How many Premier League points did Manchester United earn against clubs that finished in the top four in 2024/25?'
        with self.assertRaises(CannotCheck) as caught: self.engine.calculate(q)
        self.assertEqual(caught.exception.status,'incomplete')

    def test_win_rate_draws_remain_denominator(self):
        q = 'What was the win rate of Manchester United in 2024/25 Premier League matches in which the team kept a clean sheet, rounded to one decimal place?'
        selected = [r for r in self.team if r['goals_against']==0]
        answer = self.engine.calculate(q)
        self.assertEqual(answer['answer'],percentage(sum(r['result']=='W' for r in selected),len(selected)))
        self.assertEqual(answer['details']['denominator'],len(selected))

    def test_wrong_score_perspective_abstains(self):
        q = "What was the final score of the away Premier League defeat for Manchester United against Chelsea in 2024/25, with Chelsea's goals first?"
        with self.assertRaises(CannotCheck): self.engine.calculate(q)

    def test_tie_not_arbitrarily_broken(self):
        with self.assertRaises(CannotCheck) as caught: highest({'A':2,'B':2})
        self.assertEqual(caught.exception.status,'ambiguous')

    def test_player_quality_missing_is_not_zero_goals(self):
        q='Who finished as the sole leading Premier League goalscorer for Manchester United in 2024/25?'
        result=self.engine.check({'question':q,'answer':'Anyone'})
        self.assertEqual(result['status'],'incomplete')
        self.assertIn('38 of 38',result['reason'])

    def test_100_independent_counts(self):
        variants = [
            ('In how many Premier League matches in 2024/25 did {team} fail to score?',lambda r:r['goals_for']==0),
            ('How many Premier League wins did {team} record without conceding a goal in 2024/25?',lambda r:r['result']=='W' and r['goals_against']==0),
            ('How many Premier League defeats did {team} suffer by exactly one goal in 2024/25?',lambda r:r['goals_against']-r['goals_for']==1),
            ('How many away Premier League draws did {team} record in 2024/25?',lambda r:not r['is_home'] and r['result']=='D'),
            ('How many home Premier League draws did {team} record in 2024/25?',lambda r:r['is_home'] and r['result']=='D'),
        ]
        from api.trivia_bank_engine import CLUBS
        checks=0
        for tid in sorted({r['team_id'] for r in self.facts}):
            for template,predicate in variants:
                with self.subTest(team=tid,template=template):
                    q=template.format(team=CLUBS[tid])
                    expected=sum(predicate(r) for r in self.facts if r['team_id']==tid)
                    self.assertEqual(self.engine.calculate(q)['answer'],str(expected));checks+=1
        self.assertEqual(checks,100)


class BankModelTests(unittest.TestCase):
    def test_team_season_numeric_and_near_duplicates_share_group(self):
        questions = ['Arsenal won 3–0 in 2024/25?', 'Chelsea won 4–0 in 2020/21?',
                     'Arsenal won 3–0 in 2024/25!', 'Who owns this football club?']
        groups=grouped_families([{'question':q} for q in questions])
        self.assertEqual(groups[family_key(questions[0])],groups[family_key(questions[1])])
        self.assertEqual(groups[family_key(questions[0])],groups[family_key(questions[2])])
        self.assertNotEqual(groups[family_key(questions[0])],groups[family_key(questions[3])])
        self.assertEqual(question_tokens('Man United 2017/18'),'club33 2017/18')

    def test_actual_training_serializable_and_disjoint(self):
        templates = [('How many goals did Arsenal score?', 'scoring'), ('Who scored most often?', 'scoring'),
            ('Count shots on target for Chelsea', 'scoring'), ('Number of penalties converted?', 'scoring'),
            ('What colour is the home shirt?', 'kits'), ('Who manufactured the away kit?', 'kits'),
            ('Describe third jersey design', 'kits'), ('Which sponsor is on the sleeve?', 'kits'),
            ('Was Liverpool clothing made by Adidas?', 'kits'), ('Who scored the winning goal?', 'scoring')]
        items = [{'id':str(i),'question':q,'topic':t,'answer':'SECRET_REFERENCE'} for i,(q,t) in enumerate(templates)]
        corpus,report,artifact=train(items,{r['id']:{'status':'matched'} for r in items})
        self.assertEqual(report['artifact_training_rows'],10)
        self.assertFalse(report['answer_prediction'])
        self.assertFalse(report['generative_llm'])
        memberships={}
        for row in corpus:
            self.assertNotIn('answer',row)
            memberships.setdefault(row['family'],set()).add(row['split'])
        self.assertTrue(all(len(s)==1 for s in memberships.values()))
        result=suggest(artifact,corpus,'What colour is the home shirt?')
        self.assertEqual(result['topic'],'kits')
        self.assertEqual(result['scope'],'suggestion_only')
        self.assertTrue(result['neighbors'])
