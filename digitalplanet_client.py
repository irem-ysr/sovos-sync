from __future__ import annotations

from datetime import datetime
from typing import Any
import xml.etree.ElementTree as ET

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from zeep import Client, Settings
from zeep.helpers import serialize_object
from zeep.transports import Transport


def _to_plain(obj: Any) -> Any:
    return serialize_object(obj, target_cls=dict)


class DigitalPlanetClient:
    def __init__(self, wsdl_url: str, corporate_code: str, login_name: str, password: str, timeout: int = 300):
        self.wsdl_url = wsdl_url
        self.corporate_code = corporate_code
        self.login_name = login_name
        self.password = password
        self.timeout = timeout

        session = Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST", "GET"],
        )
        session.mount("https://", HTTPAdapter(max_retries=retries))
        session.mount("http://", HTTPAdapter(max_retries=retries))

        transport = Transport(session=session, timeout=timeout)
        settings = Settings(strict=False, xml_huge_tree=True)

        self.client = Client(wsdl=self.wsdl_url, transport=transport, settings=settings)

        self.service_url = self.wsdl_url.replace("?WSDL", "").replace("?wsdl", "")

        binding_name = None
        for name in self.client.wsdl.bindings.keys():
            if "soap12" in str(name).lower():
                binding_name = name
                break

        if not binding_name:
            binding_name = list(self.client.wsdl.bindings.keys())[0]

        print("KULLANILAN BINDING:", binding_name)
        print("KULLANILAN ENDPOINT:", self.service_url)

        self.service = self.client.create_service(binding_name, self.service_url)
        self.ticket: str | None = None

    def _extract_ticket_from_xml(self, xml_bytes: bytes) -> str | None:
        if not xml_bytes:
            return None

        try:
            root = ET.fromstring(xml_bytes)
        except Exception:
            return None

        for elem in root.iter():
            tag = elem.tag.lower()
            if tag.endswith("getformsauthenticationticketresult"):
                return (elem.text or "").strip() or None

        return None

    def authenticate(self) -> str:
        try:
            with self.client.settings(raw_response=True):
                response = self.service.GetFormsAuthenticationTicket(
                    self.corporate_code,
                    self.login_name,
                    self.password,
                )
        except Exception as exc:
            raise RuntimeError(
                f"Ticket isteği atılamadı. Endpoint={self.service_url}. Hata: {exc}"
            ) from exc

        status_code = getattr(response, "status_code", None)
        content_type = response.headers.get("Content-Type", "")
        content = response.content or b""

        print("AUTH STATUS:", status_code)
        print("AUTH CONTENT-TYPE:", content_type)

        ticket = self._extract_ticket_from_xml(content)

        if not ticket:
            preview = content[:2000].decode("utf-8", errors="replace")
            print("AUTH RESPONSE PREVIEW:")
            print(preview if preview else "[boş cevap]")
            raise RuntimeError(
                "Ticket çıkarılamadı. Login bilgileri veya servis yanıtı kontrol edilmeli."
            )

        self.ticket = ticket
        print("Ticket alındı.")
        return ticket

    def ensure_ticket(self) -> str:
        if not self.ticket:
            return self.authenticate()
        return self.ticket

    def _call(self, method_name: str, *args) -> dict:
        self.ensure_ticket()
        method = getattr(self.service, method_name)

        try:
            result = method(*args)
        except Exception as exc:
            text = str(exc)
            if "Access Denied" in text or "denied" in text.lower():
                self.ticket = None
                self.ensure_ticket()
                args = (self.ticket, *args[1:]) if args else (self.ticket,)
                result = method(*args)
            else:
                raise RuntimeError(f"{method_name} çağrısı başarısız: {exc}") from exc

        return _to_plain(result)

    def get_available_sent_invoices_by_date(self, start_date: datetime, end_date: datetime) -> dict:
        ticket = self.ensure_ticket()
        return self._call(
            "GetAvailableSentInvoicesByDate",
            ticket,
            self.corporate_code,
            start_date,
            end_date,
        )

    def get_incoming_invoices_by_issue_date(self, start_date: datetime, end_date: datetime) -> dict:
        ticket = self.ensure_ticket()
        return self._call(
            "GetIncomingInvoicesByIssueDate",
            ticket,
            self.corporate_code,
            start_date,
            end_date,
        )

    def get_available_invoices_by_date(self, start_date: datetime, end_date: datetime) -> dict:
        ticket = self.ensure_ticket()
        return self._call(
            "GetAvailableInvoicesByDate",
            ticket,
            self.corporate_code,
            start_date,
            end_date,
        )

    def get_earchive_invoices_by_date(self, start_date: datetime, end_date: datetime) -> dict:
        ticket = self.ensure_ticket()
        return self._call(
            "GetEArchiveInvoicesByDate",
            ticket,
            start_date,
            end_date,
        )

    def get_invoice_by_invoice_id(self, invoice_id: str, direction: str = "AllDirection") -> dict:
        ticket = self.ensure_ticket()
        return self._call(
            "GetInvoiceByInvoiceID",
            ticket,
            invoice_id,
            direction,
        )