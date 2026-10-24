"""Bounded API diagnostics: metadata and structure, never credentials or PII."""
import json

BODY_KEYS=set(('choices message content items case_id intent confidence supporting_phrase system_id resource_id '
               'record_type facts_json supporting_text error code type param usage prompt_tokens completion_tokens '
               'total_tokens completion_tokens_details reasoning_tokens prompt_tokens_details cached_tokens '
               'finish_reason id model object created index x_groq usage_breakdown queue_time prompt_time '
               'completion_time total_time failed_generation').split())


class SchemaValidationError(ValueError):
    def __init__(self,path,expected,actual):
        self.path,self.expected,self.actual=path,expected,actual
        super().__init__(f'{path}: expected {expected}, got {actual}')


def rate_headers(headers):
    allowed={'retry-after','x-ratelimit-limit-requests','x-ratelimit-limit-tokens',
             'x-ratelimit-remaining-requests','x-ratelimit-remaining-tokens',
             'x-ratelimit-reset-requests','x-ratelimit-reset-tokens'}
    return {key.lower():str(value)[:64] for key,value in headers.items() if key.lower() in allowed}


def redacted_body(value):
    """Preserve JSON structure/types; mask every content string, including prose."""
    if isinstance(value,dict):
        output={}
        for index,(key,child) in enumerate(value.items()):
            if key in {'content','facts_json','failed_generation'} and isinstance(child,str):
                try:child=json.loads(child)
                except ValueError:pass
            output[key if key in BODY_KEYS else f'[REDACTED_KEY_{index}]']=redacted_body(child)
        return output
    if isinstance(value,list):return [redacted_body(child) for child in value]
    if isinstance(value,str):return f'[REDACTED {len(value)} chars]'
    if type(value) in {int,float}:return '[REDACTED number]'
    return value


def body_diagnostic(value,limit=4096):
    body=redacted_body(value)
    text=json.dumps(body,ensure_ascii=False)
    return body if len(text)<=limit else {'redacted_body_prefix':text[:limit],'truncated':True}
