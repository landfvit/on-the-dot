from copy import deepcopy
import unittest
from uuid import uuid4

from src.release_solo_bank import blockers,estimate,EASY_TOPICS,MEDIUM_TOPICS,HARD_TOPICS


def example():
    ident=uuid4()
    return {'question_id':ident,'content':{'id':'ABC-001','question':'Who managed Example FC?','answer':'One'},
            'audit':{'status':'matched','accepted':['First']},'latest_audit':{'status':'matched','accepted':['First']},
            'question':{'text':'Who managed Example FC?','topic':'Managers','correct':'0',
                        'options':[{'id':str(i),'text':v} for i,v in enumerate(['One','Two','Three','Four'])],
                        'explanation':'One was the manager.','validation_status':'matched','authority':'database_matched',
                        'source':{'question_id':str(ident),'external_id':'ABC-001','references':[{'url':'https://example.com'}]}}}


class SoloBankReleaseTests(unittest.TestCase):
    def test_all_supported_topics_have_explicit_rules(self):
        for topics,level in [(EASY_TOPICS,'easy'),(MEDIUM_TOPICS,'medium'),(HARD_TOPICS,'hard')]:
            for topic in topics:
                with self.subTest(topic=topic):
                    q=example()['question'];q['topic']=topic
                    difficulty,reason=estimate(q)
                    self.assertEqual(difficulty,level);self.assertIn('not individually reviewed',reason)
                    self.assertIn('not individually reviewed or empirically calibrated',reason)
        self.assertFalse(EASY_TOPICS&MEDIUM_TOPICS);self.assertFalse(MEDIUM_TOPICS&HARD_TOPICS)

    def test_caretakers_and_kit_details_are_not_easy_by_topic_alone(self):
        q=example()['question'];q['text']='Who became the caretaker manager?'
        self.assertEqual(estimate(q)[0],'medium')
        q['topic']='Kits and design';q['text']='What was the main colour of the third shirt?'
        self.assertEqual(estimate(q)[0],'medium')
        q['text']='Whose signature was printed inside the shirt?'
        self.assertEqual(estimate(q)[0],'hard')

    def test_reading_load_and_decimal_precision_raise_difficulty(self):
        q=example()['question'];q['text']='word '*51
        self.assertEqual(estimate(q)[0],'hard')
        q=example()['question'];q['options'][0]['text']='33.3%'
        self.assertEqual(estimate(q)[0],'hard')

    def test_unknown_topic_requires_review(self):
        q=example()['question'];q['topic']='New unclassified topic'
        with self.assertRaises(ValueError):estimate(q)

    def test_valid_question_passes_without_mutating_evidence(self):
        row=example();original=deepcopy(row)
        self.assertEqual(blockers(row),[]);estimate(row['question']);self.assertEqual(row,original)

    def test_conflicting_latest_check_blocks_previously_matched_question(self):
        row=example();row['latest_audit']={'status':'conflict'}
        self.assertIn('latest audit is missing, conflicting or ambiguous',blockers(row))

    def test_missing_audits_and_ambiguous_winners_are_blocked(self):
        for check in [None,{}, {'status':'ambiguous','reason':'More than one winner'}, {'status':'unknown'}]:
            with self.subTest(check=check):
                row=example();row['audit']=check;row['latest_audit']=check
                self.assertTrue(blockers(row))

    def test_owner_attested_answers_keep_their_nonverified_authority(self):
        for status in ['incomplete','unsupported','ambiguous']:
            row=example();audit={'status':status,'reason':'Database player found, but reference name is not a registered alias'}
            row.update(audit=audit,latest_audit=audit)
            row['question'].update(validation_status=status,authority='user_attested')
            self.assertEqual(blockers(row),[])
            row['question']['authority']='database_matched';self.assertIn('Frozen answer authority mismatch',blockers(row))

    def test_distinct_choices_and_canonical_answer_are_required(self):
        mutations=[
            lambda q:q.update(options=None),
            lambda q:q.update(options=q['options'][:1]),
            lambda q:q['options'][1].update(id='0'),
            lambda q:q['options'][1].update(text='ONE'),
            lambda q:q['options'][1].update(text='First'),
            lambda q:q['options'][1].update(text=''),
            lambda q:q.update(correct='3'),
            lambda q:q.update(text='Different wording'),
            lambda q:q['source'].update(references=[]),
            lambda q:q['source'].update(question_id=str(uuid4())),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                row=example();mutation(row['question']);self.assertTrue(blockers(row))

    def test_two_or_three_recognition_choices_are_valid(self):
        for n in (2,3):
            row=example();row['question']['options']=row['question']['options'][:n]
            self.assertEqual(blockers(row),[])
