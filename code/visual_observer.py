"""Native, fact-only visual observations and source-preserving repair guards."""
import json
import re
from pydantic import BaseModel,ConfigDict,Field


class Observation(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    fact:str=Field(min_length=1)
    source_reference:str=Field(min_length=1)
    confidence:float=Field(ge=0,le=1,allow_inf_nan=False)


class EvidenceObservation(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    observations:list[Observation]
    ambiguities:list[str]
    missing_information:list[str]


VISION_SCHEMA={'type':'OBJECT','properties':{
    'observations':{'type':'ARRAY','items':{'type':'OBJECT','properties':{
        'fact':{'type':'STRING'},'source_reference':{'type':'STRING'},
        'confidence':{'type':'NUMBER','minimum':0,'maximum':1}},
        'required':['fact','source_reference','confidence']}},
    'ambiguities':{'type':'ARRAY','items':{'type':'STRING'}},
    'missing_information':{'type':'ARRAY','items':{'type':'STRING'}}},
    'required':['observations','ambiguities','missing_information']}


def parse_visual(value,source_origin=''):
    envelope=EvidenceObservation.model_validate(value)
    rows=[];incomplete=bool(envelope.ambiguities or envelope.missing_information)
    for item in envelope.observations:
        try:fact=json.loads(item.fact)
        except ValueError:
            fact={}
            for part in item.fact.split(';'):
                match=re.fullmatch(r'\s*([a-z][a-z0-9_]*)\s*=\s*(.*?)\s*',part,re.S)
                if not match:incomplete=True;continue
                key,value=match.groups()
                try:fact[key]=json.loads(value)
                except ValueError:fact[key]=value
        if not isinstance(fact,dict) or not re.fullmatch(r'[A-Za-z][\w-]*',str(fact.get('resource_id',''))):
            incomplete=True;continue
        facts=fact.get('facts',fact)
        if not isinstance(facts,dict):incomplete=True;continue
        rows.append({'resource_id':fact['resource_id'],'system_id':str(fact.get('system_id',source_origin)),
            'record_type':str(fact.get('record_type','')),'facts_json':json.dumps(facts,ensure_ascii=False,separators=(',',':')),
            'supporting_text':item.source_reference})
    return rows,incomplete


def validate_repair(value,source):
    envelope=EvidenceObservation.model_validate(value)
    normalized=source.replace('\\"','"').replace('\\\\','\\')
    for item in envelope.observations:
        for text in [item.fact,item.source_reference]:
            if text not in source and text not in normalized:raise ValueError('repair introduced unsupported text')
    for text in envelope.ambiguities+envelope.missing_information:
        if text not in source and text not in normalized:raise ValueError('repair introduced unsupported context')
    return value
