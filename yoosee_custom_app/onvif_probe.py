import hashlib, base64, datetime, secrets
import requests
import os
ip = os.environ.get('CAM_IP', '192.168.1.100'); port = int(os.environ.get('CAM_PORT', '5000')); user = os.environ.get('CAM_USER', 'admin'); pwd = os.environ.get('CAM_PASSWORD', '')
nonce = secrets.token_bytes(16)
created = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z')
digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + pwd.encode()).digest()).decode()
nonce_b64 = base64.b64encode(nonce).decode()
soap = (
 '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
 '<s:Header><Security xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"><UsernameToken>'
 f'<Username>{user}</Username>'
 '<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">'
 f'{digest}</Password>'
 '<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">'
 f'{nonce_b64}</Nonce>'
 '<Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
 f'{created}</Created></UsernameToken></Security></s:Header>'
 '<s:Body><tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities></s:Body></s:Envelope>'
)
for path in ['/onvif/device_service']:
    url = f'http://{ip}:{port}{path}'
    try:
        r = requests.post(url, data=soap.encode(),
                          headers={'Content-Type': 'application/soap+xml; charset=utf-8'},
                          timeout=6)
        print(path, r.status_code, len(r.content))
        txt = r.text
        print(txt[:2500])
    except Exception as e:
        print(path, 'ERR', repr(e))
