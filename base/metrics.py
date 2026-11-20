"""Token counts from provider usage; offline JSON size is kept separate."""
from dataclasses import dataclass, asdict

@dataclass
class Usage:
    input_tokens:int=0
    output_tokens:int=0
    cached_input_tokens:int=0
    cache_write_tokens:int=0
    requests:int=0
    tool_calls:int=0
    first_input_tokens:int|None=None

    def add(self,response,provider):
        u=response.get('usage',{})
        if 'output' in response and 'input_tokens' in u:
            n=u['input_tokens'];o=u.get('output_tokens',0);writes=u.get('input_tokens_details',{}).get('cache_write_tokens',0)
            cached=u.get('input_tokens_details',{}).get('cached_tokens',0)
            calls=sum(b.get('type')=='function_call' for b in response['output'])
        elif provider=='anthropic':
            cached=u.get('cache_read_input_tokens',0);writes=u.get('cache_creation_input_tokens',0)
            n=u.get('input_tokens',0)+cached+writes;o=u.get('output_tokens',0)
            calls=sum(b.get('type')=='tool_use' for b in response.get('content',[]))
        else:
            n=u.get('prompt_tokens',0);o=u.get('completion_tokens',0);writes=0
            cached=u.get('prompt_tokens_details',{}).get('cached_tokens',0)
            calls=sum(len(c.get('message',{}).get('tool_calls') or []) for c in response.get('choices',[]))
        if min(n,o,cached,writes)<0 or cached+writes>n:raise ValueError('Invalid usage')
        if not self.requests:self.first_input_tokens=n
        self.input_tokens+=n;self.output_tokens+=o;self.cached_input_tokens+=cached;self.cache_write_tokens+=writes
        self.requests+=1;self.tool_calls+=calls

    def report(self):return {**asdict(self),'total_tokens':self.input_tokens+self.output_tokens}

def paired(rows, baseline='identity', candidate='g9'):
    """Only identical task/checkpoint/repeat pairs enter the denominator."""
    groups={}
    for r in rows:
        if type(r.get('passed')) is not bool:raise ValueError('Only official binary scores may enter pass table')
        k=(r['task'],r['checkpoint_sha256'],r['repeat'])
        arm=r['arm'];g=groups.setdefault(k,{})
        if arm in g:raise ValueError('Duplicate result arm')
        g[arm]=r
    pairs=[(g[baseline],g[candidate]) for g in groups.values() if baseline in g and candidate in g]
    n=len(pairs);b=sum(x['passed'] for x,y in pairs);c=sum(y['passed'] for x,y in pairs)
    def total(arm,key):return sum(x[arm].get('usage',{}).get(key,0) for x in pairs)
    bt=total(0,'tool_calls');ct=total(1,'tool_calls')
    first=[(x['usage']['first_input_tokens'],y['usage']['first_input_tokens']) for x,y in pairs if x.get('usage',{}).get('first_input_tokens') is not None and y.get('usage',{}).get('first_input_tokens') is not None]
    bi=sum(x for x,y in first);ci=sum(y for x,y in first)
    return {'paired_samples':n,'unpaired_conditions':len(groups)-n,'baseline_passed':b,'candidate_passed':c,
      'baseline_rate':b/n if n else None,'candidate_rate':c/n if n else None,'delta_pp':100*(c-b)/n if n else None,
      'regressions':[x['task'] for x,y in pairs if x['passed'] and not y['passed']],
      'gains':[x['task'] for x,y in pairs if not x['passed'] and y['passed']],
      'baseline_tool_calls':bt,'candidate_tool_calls':ct,'net_added_tool_calls':ct-bt,
      'positive_added_tool_calls':sum(max(0,y['usage']['tool_calls']-x['usage']['tool_calls']) for x,y in pairs),
      'baseline_mean_first_input_tokens':bi/len(first) if first else None,'candidate_mean_first_input_tokens':ci/len(first) if first else None,
      'baseline_mean_tool_calls':bt/n if n else None,'candidate_mean_tool_calls':ct/n if n else None,
      'first_input_pairs':len(first),'mean_extra_first_input_tokens':(ci-bi)/len(first) if first else None,
      'first_input_increase_percent':100*(ci-bi)/bi if bi else None,
      'baseline_total_tokens':total(0,'total_tokens'),'candidate_total_tokens':total(1,'total_tokens')}

def cost_from_usage(usage, rates_per_million):
    """Explicit caller-supplied rates; no assumed provider price or cache discount."""
    required={'input','output','cached_input','cache_write'}
    if set(rates_per_million)!=required or any(v<0 for v in rates_per_million.values()):raise ValueError('Supply all four nonnegative rates')
    ordinary=usage.input_tokens-usage.cached_input_tokens-usage.cache_write_tokens
    if ordinary<0:raise ValueError('Cache subsets exceed total input')
    return (ordinary*rates_per_million['input']+usage.output_tokens*rates_per_million['output']+
            usage.cached_input_tokens*rates_per_million['cached_input']+usage.cache_write_tokens*rates_per_million['cache_write'])/1_000_000
