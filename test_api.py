import urllib.request, json

req = urllib.request.Request(
    'http://localhost:8000/api/v1/chat',
    data=json.dumps({
        'message': 'Phân biệt Alternately & Alternatively',
        'history': [],
        'llm_provider': 'OpenAI (GPT-4o-mini)'
    }).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

try:
    res = urllib.request.urlopen(req)
    open('out.txt', 'wb').write(res.read())
except urllib.error.HTTPError as e:
    open('out.txt', 'wb').write(e.read())
