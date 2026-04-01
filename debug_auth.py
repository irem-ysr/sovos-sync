import requests

url = "https://integrationtest.eveelektronik.com.tr/IntegrationService.asmx"

soap_body = """<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                 xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
  <soap12:Body>
    <GetFormsAuthenticationTicket xmlns="http://tempuri.org/">
      <CorporateCode>MZYCAFETAR</CorporateCode>
      <LoginName>adminuser</LoginName>
      <Password>Muhasebe35**</Password>
    </GetFormsAuthenticationTicket>
  </soap12:Body>
</soap12:Envelope>"""

headers = {
    "Content-Type": 'application/soap+xml; charset=utf-8; action="http://tempuri.org/GetFormsAuthenticationTicket"'
}

resp = requests.post(url, data=soap_body.encode("utf-8"), headers=headers, timeout=60)

print("STATUS:", resp.status_code)
print("CONTENT-TYPE:", resp.headers.get("Content-Type"))
print(resp.text[:5000])