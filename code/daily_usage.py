"""UTC calendar usage: confirmed provider responses, never persisted estimates."""
import json
import logging
import shutil
import threading
import time
from datetime import datetime,timezone
from pathlib import Path

from common import atomic_json,digest
from quota import DailyQuotaError


class DailyUsageLedger:
    def __init__(self,path,*,clock=time.time,legacy_dir=None,models=()):
        self.path=Path(path);self.clock=clock;self.lock=threading.RLock()
        self.pending={};self.sequence=0;self.unavailable=False
        self.state={'date':self._date(),'timezone':'UTC','models':{}}
        if self.path.is_file():
            try:
                state=json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(state['models'],dict):raise ValueError('invalid model usage')
                datetime.strptime(state['date'],'%Y-%m-%d')
                if state.get('timezone')!='UTC':raise ValueError('invalid quota timezone')
                for values in state['models'].values():
                    if not isinstance(values,dict):raise ValueError('invalid model counters')
                    values.setdefault('cached_tokens_today',0)
                    if any(type(values.get(k)) is not int or values[k]<0 for k in
                           ['requests_today','tokens_today','cached_tokens_today','unknown_usage_calls']):raise ValueError('invalid usage counters')
                    if values['cached_tokens_today']>values['tokens_today']:raise ValueError('invalid cached usage')
                self.state=state
            except (OSError,ValueError,KeyError,TypeError):self.unavailable=True
        elif legacy_dir:
            self._migrate(Path(legacy_dir),models)
        self._refresh()

    def _date(self):return datetime.fromtimestamp(self.clock(),timezone.utc).date().isoformat()

    def _refresh(self):
        if self.state['date']!=self._date():
            self.state={'date':self._date(),'timezone':'UTC','models':{}}

    def _model(self,model):
        return self.state['models'].setdefault(model,{'requests_today':0,'tokens_today':0,
            'cached_tokens_today':0,'unknown_usage_calls':0})

    def _save(self):atomic_json(self.path,self.state)

    def _migrate(self,directory,models):
        confirmed=unconfirmed=0;backup=None
        for model in models:
            path=directory/(digest(model)+'.json')
            if not path.is_file():continue
            if backup is None:
                stamp=datetime.fromtimestamp(self.clock(),timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                backup=directory.parent/'groq_quota_archive'/stamp;backup.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,backup/path.name)
            try:entries=json.loads(path.read_text(encoding='utf-8'))['reservations']
            except (OSError,ValueError,KeyError,TypeError):unconfirmed+=1;continue
            for entry in entries:
                try:
                    if datetime.fromtimestamp(entry['wall_at'],timezone.utc).date().isoformat()!=self._date():continue
                    actual,estimate=entry['tokens'],entry.get('minute_tokens',entry['tokens'])
                    # A changed settled charge proves a response with known usage.
                    # Equal legacy values cannot distinguish success from estimates.
                    if type(actual) is int and actual>=0 and actual!=estimate:
                        values=self._model(model);values['requests_today']+=1;values['tokens_today']+=actual;confirmed+=1
                    else:unconfirmed+=1
                except (KeyError,ValueError,TypeError,OverflowError):unconfirmed+=1
        if backup:
            self.state['migration']={'confirmed_entries':confirmed,'unconfirmed_legacy_entries':unconfirmed,
                                     'usage_kind':'settled legacy quota tokens; cached split unavailable'}
            self._save()
            logging.getLogger('audit').info('QUOTA MIGRATION | confirmed=%d | unconfirmed estimates excluded=%d | originals archived',
                                           confirmed,unconfirmed)

    def snapshot(self,model):
        with self.lock:
            self._refresh();values=dict(self._model(model))
            selected=[tokens for owner,tokens in self.pending.values() if owner==model]
            return {**values,'date':self.state['date'],'timezone':'UTC','model':model,
                    'inflight_reserved_tokens':sum(selected),'inflight_reserved_requests':len(selected),
                    'state_unavailable':self.unavailable}

    def reserve(self,model,tokens,rpd,tpd):
        with self.lock:
            state=self.snapshot(model)
            actual=max(0,state['tokens_today']-state['cached_tokens_today'])
            reason=('STATE_UNAVAILABLE' if self.unavailable else
                    'RPD_WOULD_EXCEED_LIMIT' if state['requests_today']+state['inflight_reserved_requests']>=rpd else
                    'TPD_WOULD_EXCEED_LIMIT' if actual+state['inflight_reserved_tokens']+tokens>tpd else None)
            if reason:
                error=DailyQuotaError(reason)
                error.details={**state,'rpd':rpd,'tpd':tpd,'estimated_request':tokens,'reason':reason}
                raise error
            self.sequence+=1;self.pending[self.sequence]=(model,tokens)
            return self.sequence

    def release(self,reservation):
        with self.lock:self.pending.pop(reservation,None)

    def record_response(self,model,total_tokens,cached_tokens=0):
        with self.lock:
            self._refresh();values=self._model(model);values['requests_today']+=1
            if type(total_tokens) is int and total_tokens>=0:
                values['tokens_today']+=total_tokens
                values['cached_tokens_today']+=max(0,min(total_tokens,int(cached_tokens or 0)))
            else:values['unknown_usage_calls']+=1
            self._save()
