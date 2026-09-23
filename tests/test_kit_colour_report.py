import json
from pathlib import Path
import unittest
from src.kit_colour_report import parse_page,cell,create_records


class ReportTests(unittest.TestCase):
    def test_source_header_without_artwork_remains_a_row(self):
        page={'season':1999,'sections':[{'level':'3','line':'Example FC'}],'text':{'*':'<h3>Example FC</h3>'}}
        self.assertEqual(parse_page(page),[('Example FC',[])])
        page.update(revid=1,retrieved_at='test')
        result=create_records([page])
        self.assertEqual(set(result[0]['kits']),{'home','away','third'})
        self.assertTrue(all(k['status']=='not_listed' for k in result[0]['kits'].values()))

    def test_declared_base_is_not_a_verified_dominant_colour(self):
        self.assertEqual(cell({'status':'missing_pixels','declared_base_hint':'Red'}),'Unverified (base: Red)')
        self.assertEqual(cell({'status':'available','label':'Black and orange'}),'Black and orange')

    def test_real_old_gallery_layout_and_typos_preserve_all_twenty_clubs(self):
        root=Path(__file__).resolve().parents[1]/'data/kits/research/pages'
        if not (root/'2007.json').exists():self.skipTest('Cached research pages unavailable')
        for year in range(1999,2014):
            if not (root/f'{year}.json').exists():continue
            page=json.loads((root/f'{year}.json').read_text());rows=parse_page(page)
            self.assertEqual(len(rows),20,year)
            self.assertEqual(len({name for name,_ in rows}),20)
        rows=dict(parse_page(json.loads((root/'2007.json').read_text())))
        self.assertNotIn('Aston Vila',rows)
        self.assertEqual({k['type'] for k in rows['Aston Villa']},{'home','away','third'})
        if (root/'2011.json').exists():
            rows=dict(parse_page(json.loads((root/'2011.json').read_text())))
            self.assertNotIn('Tottenham Hotpsur',rows)
            self.assertEqual({k['type'] for k in rows['Tottenham Hotspur']},{'home','away','third'})
