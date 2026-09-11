"""Module to parse Salus iT500 API responses"""

from typing import Any
from xml.parsers.expat import ExpatError

import xmltodict

from .exceptions import SalusConnectionError


def parse_response(text: str, root: str, **kwargs: Any) -> Any:
    """Return the root element of an XML API response."""
    try:
        return xmltodict.parse(text, xml_attribs=False, **kwargs)[root]
    except (ExpatError, KeyError, TypeError) as err:
        raise SalusConnectionError(f"Unexpected Salus API response ({type(err).__name__})") from err
