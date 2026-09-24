"""Provided artwork is public, correctly assigned and does not alter the shell."""
from html.parser import HTMLParser
from pathlib import Path
import struct
import unittest

from fastapi.testclient import TestClient
from trivia_app.main import app

ROOT = Path(__file__).resolve().parents[1]


class Images(HTMLParser):
    def __init__(self):
        super().__init__();self.images=[];self.icons=[]

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='img' and attrs.get('class')=='home-logo':self.images.append(attrs)
        if tag=='link' and attrs.get('rel') in ('icon','apple-touch-icon'):self.icons.append(attrs)


class BrandAssetTests(unittest.TestCase):
    def test_logos_are_public_png_files_with_their_original_dimensions(self):
        client=TestClient(app)
        for name in ('logo','mark'):
            response=client.get(f'/trivia-assets/brand/{name}.png')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['content-type'],'image/png')
            self.assertEqual(response.content,(ROOT/'trivia_app'/'static'/'brand'/f'{name}.png').read_bytes())
            self.assertEqual(response.content[:8],b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II',response.content[16:24]),(2000,2000))
        self.assertNotEqual(client.get('/trivia-assets/brand/private.png').status_code,200)

    def test_wordmark_on_both_entry_pages_and_symbol_as_favicon_everywhere(self):
        client=TestClient(app)
        for path in ('/','/how-to-play','/penalties','/leaderboard','/account','/history'):
            parser=Images();parser.feed(client.get(path).text)
            self.assertEqual({icon['rel'] for icon in parser.icons},{'icon','apple-touch-icon'})
            self.assertEqual({icon['href'] for icon in parser.icons if icon['rel']=='icon'},
                             {'/trivia-assets/brand/favicon.png?v=2','/trivia-assets/brand/favicon.svg?v=2'})
            self.assertEqual(next(icon['href'] for icon in parser.icons if icon['rel']=='apple-touch-icon'),
                             '/trivia-assets/brand/mark.png?v=1')
            if path in ('/','/how-to-play','/penalties'):
                self.assertEqual(len(parser.images),1)
                self.assertEqual(parser.images[0]['alt'],'ON THE DOT.')
                self.assertEqual(parser.images[0]['src'],'/trivia-assets/brand/logo.png?v=1')
            else:self.assertEqual(parser.images,[])

    def test_legacy_favicon_request_resolves_to_the_symbol(self):
        response=TestClient(app).get('/favicon.ico')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content,(ROOT/'trivia_app'/'static'/'brand'/'favicon.png').read_bytes())
        self.assertEqual(struct.unpack('>II',response.content[16:24]),(64,64))

    def test_vector_favicon_embeds_the_original_symbol_without_redrawing_it(self):
        import base64
        import xml.etree.ElementTree as ET
        response=TestClient(app).get('/trivia-assets/brand/favicon.svg?v=2')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['content-type'],'image/svg+xml')
        root=ET.fromstring(response.content)
        x,y,width,height=map(float,root.attrib['viewBox'].split())
        self.assertEqual(width,height)
        self.assertLess(width,1700)
        self.assertGreater(x,0);self.assertGreater(y,0)
        image=root.find('{http://www.w3.org/2000/svg}image')
        original=base64.b64decode(image.attrib['href'].split(',',1)[1])
        self.assertEqual(original,(ROOT/'trivia_app'/'static'/'brand'/'mark.png').read_bytes())
