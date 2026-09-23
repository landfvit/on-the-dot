"""Deterministic context facts pinned independently to a football dataset."""
from datetime import datetime
import math
from fastapi import HTTPException
from kits.colours import COLOURS


def snapshot(conn,spec,data):
    row=conn.execute('SELECT * FROM trivia_context_snapshots WHERE context_id=%s AND dataset_id=%s',
        (spec.context_id,data['dataset_id'])).fetchone()
    if not row: raise HTTPException(422,'Context snapshot is missing or belongs to another football dataset')
    return row


def provenance(context):
    return {'snapshot_id':str(context['context_id']),'source_hash':context['source_hash'],
        'created_at':context['created_at'].isoformat(),'method':context['method']}


def kit_result(conn,spec,data,league):
    context=snapshot(conn,spec,data);season=spec.period.seasons[0]
    team=conn.execute('''SELECT team_name FROM trivia_match_team_facts WHERE dataset_id=%s
        AND league_id=%s AND season=%s AND team_id=%s LIMIT 1''',
        (data['dataset_id'],spec.league_id,season,spec.team_id)).fetchone()
    if not team: raise HTTPException(422,'Team is not present in the selected competition season')
    record=context['payload']['kits'].get(f'{season}:{spec.team_id}:{spec.kit_type}')
    version2=record and record.get('method') in ('shirt-torso-colours-v2','shirt-torso-colours-v3')
    components=record.get('colours',[]) if version2 else []
    available=bool(record and record['status']=='available' and (0<len(components)<=3 and len(set(components))==len(components) and all(c in COLOURS for c in components) if version2 else record['colour'] in COLOURS))
    colour=record['colour'] if available and not version2 else None
    label,swatch,aliases=COLOURS[colour] if colour else (None,None,[])
    if available and version2:
        label=' and '.join(COLOURS[c][0].lower() for c in components).capitalize()
        aliases=[label];colour='+'.join(components)
    warnings=[] if available else ['kit_'+(record['status'] if record else 'missing_record')]
    result={'dataset_id':data['dataset_id'],'dataset_created_at':data['created_at'],'engine_version':data['engine_version'],
        'specification':spec.model_dump(mode='json'),'resolved_seasons':[season],
        'question_text':f"What was the dominant shirt-body colour of {team['team_name']}'s {spec.kit_type} kit in {season}/{str(season+1)[-2:]}? (Broad colour family, from the Wikimedia Commons kit artwork.)",
        'answer':{'kind':'entity','entity_type':'colour','value':None,'label':label,'swatch':swatch,'unit':'colour',
            'accepted':[{'entity_id':colour,'name':label,'aliases':aliases}] if available else [],'sample_size':1 if available else 0},
        'coverage':{'unit':'kits','requested_matches':1,'eligible_matches':1 if available else 0,'matched_matches':1 if available else 0,
            'excluded_matches':0 if available else 1,'exclusions':{},'warnings':warnings,'publishable':available is True},
        'evidence':[], 'context_evidence':record, 'context_source':provenance(context)}
    if version2:
        result['question_text']=result['question_text'].replace('shirt-body colour','shirt-body colour or colour combination')
        result['answer']['colour_components']=[{'key':c,'aliases':COLOURS[c][2]} for c in components] if available else []
        result['answer']['grading_policy']='colour-set-v2'
        result['answer']['swatches']=[COLOURS[c][1] for c in components] if available else []
    return result


def weather_problem(row,kickoff,metric):
    if not row: return 'missing_weather'
    try:
        time=datetime.fromisoformat(row['sampled_at']);original=datetime.fromisoformat(row['kickoff_at'])
        if original != kickoff or abs((time-kickoff).total_seconds())>1800: return 'weather_time_mismatch'
    except (ValueError,TypeError,KeyError): return 'weather_time_mismatch'
    units=row.get('raw_payload',{}).get('hourly_units') or {}
    variable,unit=('temperature_2m','\u00b0C') if metric=='temperature_c' else ('precipitation','mm')
    if row.get('model')!='ERA5' or units.get(variable)!=unit: return 'weather_source_unverified'
    value=row.get(metric)
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value): return 'missing_weather_value'
    if (metric=='temperature_c' and not -100<=value<=60) or (metric=='precipitation_mm' and not 0<=value<=1000):
        return 'invalid_weather_value'
    return None


def filter_weather(rows,context,condition):
    for row in rows:
        weather=context['payload']['weather'].get(str(row['fixture_id']))
        problem=weather_problem(weather,row['match_date'],condition.metric)
        row['weather']=None if not weather else {k:weather.get(k) for k in ('sampled_at','kickoff_at','temperature_c',
            'precipitation_mm','model','source_url','retrieved_at','latitude','longitude','venue_id')}
        if problem:
            row['result_valid']=False;row['timeline_valid']=False;row['reasons']=[*row['reasons'],problem]
            row['weather_matches']=False
        else:
            value=weather[condition.metric];target=condition.value
            row['weather_matches']={'gte':value>=target,'lte':value<=target,'gt':value>target,'lt':value<target}[condition.operator]


def weather_description(condition):
    metric={'temperature_c':'ERA5 estimated air temperature (C) at the nearest hourly sample to kickoff',
        'precipitation_mm':'ERA5 estimated total precipitation (mm, including snow) in the hour preceding the nearest sample to kickoff'}[condition.metric]
    comparison={'gte':'at least','lte':'at most','gt':'above','lt':'below'}[condition.operator]
    return f'{metric} {comparison} {condition.value:g}; sample within 30 minutes of kickoff'
