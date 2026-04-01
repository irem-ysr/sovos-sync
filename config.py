from pathlib import Path

WSDL_URL = "https://integrationservicewithoutmtom.digitalplanet.com.tr/IntegrationService.asmx?WSDL"
SERVICE_URL = "https://integrationservicewithoutmtom.digitalplanet.com.tr/IntegrationService.asmx"

CORPORATE_CODE = "MZYCAFETAR"
LOGIN_NAME = "wsadminuser"
PASSWORD = "d0v+.Gm-x5"

GOOGLE_SERVICE_ACCOUNT_FILE = Path("/Users/PC/Desktop/sovos-api/google-service-account.json")
SPREADSHEET_NAME = "Sovos Fatura Takibi"
OUTGOING_SHEET_NAME = "Giden Faturalar"
INCOMING_SHEET_NAME = "Gelen Faturalar"

LOOKBACK_DAYS = 30
SOAP_TIMEOUT_SECONDS = 300