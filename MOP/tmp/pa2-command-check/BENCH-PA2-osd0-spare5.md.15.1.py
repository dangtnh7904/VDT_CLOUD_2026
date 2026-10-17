import collections, datetime as dt, json, math, sys
path, begin, end = sys.argv[1:]
stamp=lambda s: dt.datetime.fromisoformat(s.replace('Z','+00:00'))
seconds=(stamp(end)-stamp(begin)).total_seconds()
assert seconds > 0
rows=[json.loads(line) for line in open(path) if line.strip()]
assert rows, 'INCONCLUSIVE: no raw operations'
groups=collections.defaultdict(list)
for row in rows: groups[row['kind']].append(row)
result={'window_seconds':seconds,'boundary':'DB_RESULT_TIMESTAMP',
        'offered_load':'UNMEASURED','operations':{}}
for kind, items in sorted(groups.items()):
    good=[r for r in items if r['success'] is True]
    lat=sorted(float(r['latency_ms']) for r in good)
    def pct(q):
        return lat[max(0,math.ceil(q*len(lat))-1)] if lat else None
    times=sorted([stamp(begin),stamp(end)]+
                 [stamp(r['created_at']) for r in items])
    result['operations'][kind]={
      'completed':len(items),'success':len(good),
      'errors':len(items)-len(good),'completed_rps':len(items)/seconds,
      'success_rps':len(good)/seconds,
      'payload_MiB_s':(sum(int(r['bytes_count']) for r in good)
          /seconds/1048576 if kind in ('PUT','UPDATE','GET') else None),
      'p50_success_ms':pct(.50),'p95_success_ms':pct(.95),
      'p99_success_ms':pct(.99),'percentile_method':'nearest_rank',
      'max_result_gap_s':max((b-a).total_seconds()
          for a,b in zip(times,times[1:])),
      'quality':'LOW_SAMPLE' if len(good)<1000 else 'DESCRIPTIVE'}
print(json.dumps(result,indent=2))
