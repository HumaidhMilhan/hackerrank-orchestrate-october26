"""Local OCR with geometry-preserving text and explicit evidence scope."""
import json
import logging
import re
import threading
import time
from pathlib import Path

from common import RESOURCE_RE,atomic_json,digest,identifiers

_engine=None
_lock=threading.Lock()


def assemble_screen(regions):
    lines=[];scores=[];link_scores=[];uncertain_anchor=False
    for box,text,score in sorted(regions or [],key=lambda row:(sum(p[1] for p in row[0])/4,min(p[0] for p in row[0]))):
        if not str(text).strip():continue
        y=sum(p[1] for p in box)/4;x=min(p[0] for p in box);scores.append(float(score))
        if ('@' in text or re.search(r'\buser[ _-]',text,re.I) or RESOURCE_RE.search(text)) and float(score)<.65:
            uncertain_anchor=True
        if identifiers(text) or RESOURCE_RE.search(text):link_scores.append(float(score))
        line=next((line for line in reversed(lines) if abs(line['y']-y)<9),None)
        if line is None:line={'y':y,'cells':[]};lines.append(line)
        line['cells'].append((x,str(text).strip()))
    text='\n'.join(' | '.join(value for _,value in sorted(line['cells'])) for line in lines)
    # OCR can fuse a numeric ID and the next UI cell with a dash. Tokenize the
    # visible delimiter without changing any identifier characters.
    text=re.sub(r'\b((?:user|account|analytics|search|support|export|data_flow|backup|audit_record|marketing)_\d+)-(?=[a-z])',r'\1 | ',text)
    text=re.sub(r'\b((?:user|account|analytics|search|support|export|data_flow|backup|audit_record|marketing)_\d+)-(?=\s|$)',r'\1',text)
    confidence=sum(scores)/len(scores) if scores else 0
    resources=sorted(set(RESOURCE_RE.findall(text)))
    subjects=sorted(identifiers(text))
    alias_mentions=re.findall(r'\b[\w.-]+\.(?:pdf|png|jpg|jpeg|zip|csv|json)\b',text,re.I)
    aliases=sorted(set(alias_mentions))
    # Repetition identifies a selected filename shown in both its table row and
    # detail panel. Ownership still requires a separate eligible catalog binding.
    primary_aliases=[alias for alias in aliases if alias_mentions.count(alias)>1]
    reliable_coverage=bool(text and confidence>=.80 and not uncertain_anchor)
    # Scope is usable only when OCR read the screen and recovered actual linking
    # identifiers. Empty/noisy OCR cannot make an unknown artifact disappear.
    return {'text':text,'confidence':confidence,'possible_identifiers':subjects,'possible_resources':resources,'possible_aliases':aliases,
            'primary_aliases':primary_aliases,
            'scope_complete':reliable_coverage and (bool(link_scores and min(link_scores)>=.65 and
                                  sum(link_scores)/len(link_scores)>=.80 and (subjects or resources)) or bool(aliases)),
            'engine':'rapidocr-onnxruntime/1.2.3'}


def read_screen(image,cache_dir):
    global _engine
    path=Path(cache_dir)/(digest({'image':digest(image),'version':4})+'.json')
    if path.is_file():
        try:return {**json.loads(path.read_text(encoding='utf-8')),'cache_hit':True,'seconds':0.0}
        except (OSError,ValueError,TypeError):
            logging.getLogger('audit').warning('LOCAL OCR | unreadable cache; rebuilding observation')
    started=time.monotonic()
    try:
        with _lock:
            if _engine is None:
                from rapidocr_onnxruntime import RapidOCR
                _engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1)
            regions,_=_engine(image)
        result=assemble_screen(regions)
        result['seconds']=round(time.monotonic()-started,3)
        result['cache_hit']=False
        atomic_json(path,result)
        return result
    except Exception as exc:
        logging.getLogger('audit').warning('LOCAL OCR | unavailable (%s); scope remains UNKNOWN',type(exc).__name__)
        return {'text':'','scope_complete':False,'possible_identifiers':[],'possible_resources':[]}
