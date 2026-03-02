"""
modules/tool_usage/booking_manager.py
--------------------------------------
Executes the full TBO booking flows for hotels and flights after the
pipeline has selected them.

Hotel flow:   PreBook  →  Book
Flight flow:  FareQuote → FareRule → Book → Ticket

Auth:
  Hotels  — HTTP Basic (TBO_USERNAME : TBO_PASSWORD)
  Flights — TokenId from _tbo_air_authenticate() (reuses flight_tool cache)

Usage example (after run_pipeline selects hotel + flight):

    from modules.tool_usage.booking_manager import BookingManager
    from schemas.constraints import ConstraintBundle

    bm = BookingManager()

    # Hotel
    hotel_conf = bm.book_hotel(
        booking_code="1345320!TB!3!TB!af78e57f-...",
        total_fare=164.65,
        passengers=bundle.passengers,
        email="guest@example.com",
        phone="919999999999",
    )

    # Flight
    flight_conf = bm.book_flight(
        result_index="...",
        trace_id="...",
        passengers=bundle.passengers,
        is_domestic=True,
    )
"""

from __future__ import annotations

import uuid
from typing import Any

import config
from schemas.constraints import PassengerDetails

try:
    import requests as _requests
    from requests.auth import HTTPBasicAuth as _HTTPBasicAuth
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Shared low-level helpers
# ─────────────────────────────────────────────────────────────────────────────

def _hotel_post(path: str, body: dict) -> dict:
    """POST to TBO Hotel API with Basic Auth."""
    if not _REQUESTS_AVAILABLE:
        raise RuntimeError("'requests' package not installed. Run: pip install requests")
    url = f"{config.TBO_HOTEL_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    resp = _requests.post(
        url,
        json=body,
        auth=_HTTPBasicAuth(config.TBO_USERNAME, config.TBO_PASSWORD),
        timeout=config.TBO_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _air_post(path: str, body: dict) -> dict:
    """POST to TBO Air API (no auth header — token inside body)."""
    if not _REQUESTS_AVAILABLE:
        raise RuntimeError("'requests' package not installed. Run: pip install requests")
    url = f"{config.TBO_AIR_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    resp = _requests.post(
        url,
        json=body,
        headers={"Content-Type": "application/json"},
        timeout=config.TBO_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _get_air_token() -> str:
    """Reuse the cached token from flight_tool (same process cache)."""
    from modules.tool_usage.flight_tool import _tbo_air_authenticate
    return _tbo_air_authenticate()


# ─────────────────────────────────────────────────────────────────────────────
# Passenger serialisers
# ─────────────────────────────────────────────────────────────────────────────

def _hotel_customer_details(passengers: list[PassengerDetails]) -> list[dict]:
    """Convert PassengerDetails list → TBO Hotel CustomerDetails structure."""
    customers = []
    for p in passengers:
        customers.append({
            "CustomerNames": [
                {
                    "Title":     p.title or "Mr",
                    "FirstName": p.first_name,
                    "LastName":  p.last_name,
                    "Type":      "Adult" if p.passenger_type == 1 else "Child",
                }
            ]
        })
    return customers


def _air_passenger_list(passengers: list[PassengerDetails]) -> list[dict]:
    """Convert PassengerDetails list → TBO Air Passenger structure."""
    result = []
    for i, p in enumerate(passengers):
        pax: dict[str, Any] = {
            "PaxId":     i,
            "Title":     p.title or "Mr",
            "FirstName": p.first_name,
            "LastName":  p.last_name,
            "IsLeadPax": i == 0,
            "DateOfBirth": f"{p.date_of_birth}T00:00:00" if p.date_of_birth else "1985-01-01T00:00:00",
            "Type": p.passenger_type,   # 1=Adult 2=Child 3=Infant
            "Gender": p.gender,
            "Email":    p.email or "",
            "Mobile1":  p.mobile or "9999999999",
            "Mobile1CountryCode": p.mobile_country_code or "91",
            "Nationality": {
                "CountryCode": p.nationality_code or "IN",
                "CountryName": "India" if (p.nationality_code or "IN") == "IN" else p.nationality_code,
            },
            "PaxBaggage": [],
            "PaxMeal":    [],
            "PaxSeat":    None,
            "SavePaxDetails": True,
        }
        if p.id_number:
            pax["IdDetails"] = [
                {
                    "PaxId":     i,
                    "IdType":    1,
                    "IdNumber":  p.id_number,
                    "IssuedCountryCode": p.nationality_code or "IN",
                    "IssueDate":  None,
                    "ExpiryDate": f"{p.id_expiry}T00:00:00" if p.id_expiry else None,
                }
            ]
        result.append(pax)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# BookingManager
# ─────────────────────────────────────────────────────────────────────────────

class BookingManager:
    """
    Executes TBO booking flows.  All methods raise on API/auth errors
    and return the raw confirmation dict on success.
    """

    # ── Hotel Booking ─────────────────────────────────────────────────────────

    def prebook_hotel(self, booking_code: str) -> dict:
        """
        POST /PreBook — validates price and availability before committing.
        Returns the PreBook response dict.
        booking_code comes from HotelRecord.raw["BookingCode"].
        """
        body = {"BookingCode": booking_code, "PaymentMode": "Limit"}
        print(f"  [BookingManager] Hotel PreBook: {booking_code[:40]}...")
        return _hotel_post("PreBook", body)

    def book_hotel(
        self,
        booking_code: str,
        total_fare: float,
        passengers: list[PassengerDetails],
        email: str = "",
        phone: str = "919999999999",
        client_reference_id: str = "",
    ) -> dict:
        """
        Full hotel booking: PreBook first, then Book.
        Returns the Book confirmation response dict (contains ConfirmationNumber).
        """
        if not passengers:
            raise ValueError("At least one passenger is required for hotel booking.")

        # Step 1 — PreBook to lock price
        prebook_resp = self.prebook_hotel(booking_code)
        locked_code = (
            prebook_resp.get("HotelResult", {}).get("BookingCode")
            or booking_code
        )

        # Step 2 — Book
        ref_id = client_reference_id or str(uuid.uuid4().int)[:18]
        body = {
            "BookingCode":        locked_code,
            "CustomerDetails":    _hotel_customer_details(passengers),
            "ClientReferenceId":  ref_id,
            "BookingReferenceId": str(uuid.uuid4().int)[:15],
            "TotalFare":          total_fare,
            "EmailId":            email or (passengers[0].email if passengers else ""),
            "PhoneNumber":        phone,
            "BookingType":        "Voucher",
            "PaymentMode":        "Limit",
        }
        print(f"  [BookingManager] Hotel Book: fare={total_fare} pax={len(passengers)}")
        return _hotel_post("Book", body)

    # ── Flight Booking ────────────────────────────────────────────────────────

    def fare_quote(self, trace_id: str, result_index: str) -> dict:
        """POST /FareQuote/ — lock flight price before booking."""
        token = _get_air_token()
        body = {
            "EndUserIp":   "0.0.0.0",
            "TraceId":     trace_id,
            "TokenId":     token,
            "ResultIndex": result_index,
        }
        print(f"  [BookingManager] FareQuote: ResultIndex={result_index[:30]}...")
        return _air_post("FareQuote/", body)

    def fare_rule(self, trace_id: str, result_index: str) -> dict:
        """POST /FareRule/ — fetch cancellation / change rules."""
        token = _get_air_token()
        body = {
            "EndUserIp":   "0.0.0.0",
            "TraceId":     trace_id,
            "TokenId":     token,
            "ResultIndex": result_index,
        }
        return _air_post("FareRule/", body)

    def book_flight(
        self,
        result_index: str,
        trace_id: str,
        passengers: list[PassengerDetails],
        fare_data: dict,
        segments_data: list[dict],
        fare_rules: list[dict],
        mini_fare_rules: list[dict],
        is_domestic: bool = True,
        origin: str = "",
        destination: str = "",
        trip_name: str = "NextStep Trip",
        call_back_url: str = "",
    ) -> dict:
        """
        POST /Booking/Book — create PNR.
        fare_data, segments_data, fare_rules, mini_fare_rules come from FareQuote/FareRule responses.
        Returns booking response dict (contains PNR).
        """
        if not passengers:
            raise ValueError("At least one passenger is required for flight booking.")
        token = _get_air_token()

        body = {
            "ResultId": result_index,
            "Itinerary": {
                "TokenId":             token,
                "TrackingId":          trace_id,
                "IsDomestic":          is_domestic,
                "Origin":              origin,
                "Destination":         destination,
                "TripName":            trip_name,
                "Segments_BE":         segments_data,
                "Passenger":           _air_passenger_list(passengers),
                "FareRules":           fare_rules,
                "MiniFareRules":       mini_fare_rules,
                "PNR":                 "",
                "BookingMode":         1,
                "IsLcc":               False,
                "NonRefundable":       True,
                "SearchType":          1,
                "PaymentMode":         0,
                "FlightBookingSource": 72,
                "callBackUrl":         call_back_url,
                "FoidDetails":         {},
                "ResultType":          2,
            },
            "PNR":              "",
            "BookingId":        "",
            "TokenId":          token,
            "TrackingId":       trace_id,
            "IPAddress":        "0.0.0.0",
            "PointOfSale":      "IN",
            "ConfirmPriceChangeTicket": False,
        }
        print(f"  [BookingManager] Flight Book: pax={len(passengers)} domestic={is_domestic}")
        return _air_post("Booking/Book", body)

    def ticket_flight(
        self,
        pnr: str,
        result_index: str,
        trace_id: str,
        passengers: list[PassengerDetails],
        fare_data: dict,
        segments_data: list[dict],
        fare_rules: list[dict],
        mini_fare_rules: list[dict],
        is_domestic: bool = True,
        origin: str = "",
        destination: str = "",
    ) -> dict:
        """
        POST /Booking/Ticket — issue ticket (charges the traveller).
        Must be called after book_flight succeeds.
        """
        token = _get_air_token()
        body = {
            "ResultId": result_index,
            "Itinerary": {
                "TokenId":             token,
                "TrackingId":          trace_id,
                "IsDomestic":          is_domestic,
                "Origin":              origin,
                "Destination":         destination,
                "Segments_BE":         segments_data,
                "Passenger":           _air_passenger_list(passengers),
                "FareRules":           fare_rules,
                "MiniFareRules":       mini_fare_rules,
                "PNR":                 pnr,
                "BookingMode":         1,
                "IsLcc":               False,
                "NonRefundable":       True,
                "SearchType":          1,
                "PaymentMode":         0,
                "FlightBookingSource": 72,
                "FoidDetails":         {},
                "ResultType":          2,
            },
            "PNR":        pnr,
            "BookingId":  "",
            "TokenId":    token,
            "TrackingId": trace_id,
            "IPAddress":  "0.0.0.0",
            "PointOfSale": "IN",
            "ConfirmPriceChangeTicket": False,
        }
        print(f"  [BookingManager] Flight Ticket: PNR={pnr}")
        return _air_post("Booking/Ticket", body)

    # ── Convenience: Full flight flow ─────────────────────────────────────────

    def book_flight_full(
        self,
        result_index: str,
        trace_id: str,
        passengers: list[PassengerDetails],
        is_domestic: bool = True,
        origin: str = "",
        destination: str = "",
        trip_name: str = "NextStep Trip",
        issue_ticket: bool = True,
    ) -> dict:
        """
        End-to-end flight booking:
            FareQuote → FareRule → Book → (optionally) Ticket

        Returns a summary dict:
            {
              "pnr": "...",
              "fare_quote": {...},
              "book_response": {...},
              "ticket_response": {...},   # only if issue_ticket=True
            }
        """
        fq  = self.fare_quote(trace_id, result_index)
        fr  = self.fare_rule(trace_id, result_index)

        fare_data      = fq.get("Response", {}).get("Results", {}).get("Fare", {})
        segments_data  = fq.get("Response", {}).get("Results", {}).get("Segments", [[]])[0]
        fare_rules     = fr.get("Response", {}).get("FareRules", [])
        mini_fare_rules = fq.get("Response", {}).get("Results", {}).get("MiniFareRules", [])

        book_resp = self.book_flight(
            result_index=result_index,
            trace_id=trace_id,
            passengers=passengers,
            fare_data=fare_data,
            segments_data=segments_data,
            fare_rules=fare_rules,
            mini_fare_rules=mini_fare_rules,
            is_domestic=is_domestic,
            origin=origin,
            destination=destination,
            trip_name=trip_name,
        )

        pnr = book_resp.get("PNR", "")
        summary: dict[str, Any] = {
            "pnr":           pnr,
            "fare_quote":    fq,
            "book_response": book_resp,
        }

        if issue_ticket and pnr:
            ticket_resp = self.ticket_flight(
                pnr=pnr,
                result_index=result_index,
                trace_id=trace_id,
                passengers=passengers,
                fare_data=fare_data,
                segments_data=segments_data,
                fare_rules=fare_rules,
                mini_fare_rules=mini_fare_rules,
                is_domestic=is_domestic,
                origin=origin,
                destination=destination,
            )
            summary["ticket_response"] = ticket_resp

        return summary
