"""Versioned broad colour families, measured inside the shirt torso only."""
from collections import Counter
import colorsys

METHOD = 'shirt-torso-colours-v1'
COLOURS = {
    'white': ('White', '#ffffff', ['white','off white','off-white','bila','bily','bile']),
    'black': ('Black', '#171717', ['black','cerna','cerny','cerne']),
    'grey': ('Grey', '#888888', ['grey','gray','seda','sedy','sede']),
    'red': ('Red', '#dc242b', ['red','cervena','cerveny','cervene']),
    'blue': ('Blue', '#2477cc', ['blue','modra','modry','modre']),
    'navy': ('Navy blue', '#14244a', ['navy','navy blue','dark blue','blue','tmave modra','tmavomodra','modra']),
    'green': ('Green', '#23804d', ['green','zelena','zeleny','zelene']),
    'yellow': ('Yellow', '#f4d52c', ['yellow','zluta','zluty','zlute']),
    'orange': ('Orange', '#f18724', ['orange','oranzova','oranzovy','oranzove']),
    'pink': ('Pink', '#ee86ad', ['pink','ruzova','ruzovy','ruzove']),
    'purple': ('Purple', '#8153a3', ['purple','violet','fialova','fialovy','fialove']),
    'brown': ('Brown', '#795038', ['brown','hneda','hnedy','hnede']),
    'maroon': ('Maroon', '#782333', ['maroon','burgundy','claret','vinova','bordo']),
}


def colour_family(rgb):
    r,g,b = [v/255 for v in rgb[:3]]
    h,s,v = colorsys.rgb_to_hsv(r,g,b)
    if v < .18: return 'black'
    if s < .16: return 'white' if v >= .82 else 'grey'
    if v >= .88 and s < .23: return 'white'
    degrees = h*360
    if degrees < 18 or degrees >= 345:
        return 'maroon' if v < .58 else 'pink' if s < .5 else 'red'
    if degrees < 45: return 'brown' if v < .65 else 'orange'
    if degrees < 70: return 'yellow'
    if degrees < 175: return 'green'
    if degrees < 260: return 'navy' if v < .5 else 'blue'
    return 'pink' if degrees >= 315 and v > .7 else 'purple'


def dominant_colour(image):
    if image.size != (38,59):
        raise ValueError('Expected the Commons 38x59 shirt body')
    # Interior torso excludes the collar, outline, canvas, shorts and socks.
    pixels = list(image.convert('RGBA').crop((3,12,35,54)).getdata())
    if any(p[3] != 255 for p in pixels):
        return {'status':'incomplete_pixels','colour':None,'palette':[], 'method':METHOD}
    counts = Counter(colour_family(p) for p in pixels)
    ordered = counts.most_common()
    share = ordered[0][1]/len(pixels)
    margin = share-(ordered[1][1]/len(pixels) if len(ordered)>1 else 0)
    unambiguous = share >= .60 and margin >= .20
    return {'status':'available' if unambiguous else 'multicolour',
        'colour':ordered[0][0] if unambiguous else None, 'method':METHOD,
        'palette':[{'colour':key,'share':round(count/len(pixels),4)} for key,count in ordered]}


def colour_description(image,version='v2'):
    """V2 supports two/three substantial colour families; V1 stays reproducible."""
    measured=dominant_colour(image)
    palette=measured['palette']
    colours=[]
    two=[p for p in palette if p['share']>=.25]
    three=[p for p in palette if p['share']>=.20]
    if len(two)==2 and sum(p['share'] for p in two)>=.75:
        colours=sorted(p['colour'] for p in two)
    elif len(three)==3 and sum(p['share'] for p in three)>=.85:
        colours=sorted(p['colour'] for p in three)
    elif measured['status']=='available':
        colours=[measured['colour']]
    if version=='v3':
        if measured['status']=='available':colours=[measured['colour']]
        elif {'black','grey','white'}.issubset(colours) or {'blue','navy'}.issubset(colours):colours=[]
    elif version!='v2':raise ValueError('Unknown colour description version')
    return {**measured,'method':'shirt-torso-colours-'+version,'colours':colours,
        'colour':colours[0] if len(colours)==1 else None,
        'label':' and '.join(COLOURS[c][0].lower() for c in colours).capitalize() if colours else None,
        'status':'available' if colours else measured['status']}
