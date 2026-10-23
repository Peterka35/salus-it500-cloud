"""Salus iT500 (Arrayent) API payloads with made-up identifiers."""

USERNAME = "owner@example.com"
PASSWORD = "secret!pass"
DEVICE_ID = 201300001
# Second thermostat of the same account, a house of its own
SECOND_DEVICE_ID = 201300002
USER_ID = 1500001
SECURITY_TOKEN = "token-1"

# CH1 + hot water thermostat, heating zone off, hot water always on
DEVICE_ATTRIBUTES = {
    "S06": "2",
    "S07": "0",
    "S09": "500",
    "desc": "Apartmán A",
    "A84": "2050",
    "A85": "2100",
    "A86": "0",
    "A87": "0",
    "A88": "0",
    "A89": "1",
    "A90": "0",
    "A91": "0",
    "A92": "0",
    "A93": "2100",
    "A94": "2000",
    "C42": "2",
    "C43": "0",
    "C44": "0",
    "C45": "1",
    "C46": "0",
}


def device_attributes_xml(
    attributes: dict[str, str], reported_at: float | None = None, presence: str | None = None
) -> str:
    """Return getDeviceAttributesWithValues response.

    `reported_at` is when the gateway last uploaded the values, in epoch seconds; the API gives it
    per attribute as `updTime` in milliseconds. Left out, the attributes carry no time at all.
    `presence` is the cloud's `presenceInfo` for the gateway, "1" connected and "0" not; left out,
    the response has none.
    """

    upd_time = "" if reported_at is None else f"<updTime>{int(reported_at * 1000)}</updTime>"
    items = "".join(
        f"<attrList><id>{index}</id><name>{name}</name><value>{value}</value>{upd_time}</attrList>"
        for index, (name, value) in enumerate(attributes.items())
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ns1:getDeviceAttributesWithValuesResponse xmlns:ns1="http://arrayent.com/zamapi">'
        f"<totalAttrCount>{len(attributes)}</totalAttrCount>"
        + ("" if presence is None else f"<presenceInfo>{presence}</presenceInfo>")
        + f"{items}"
        "</ns1:getDeviceAttributesWithValuesResponse>"
    )


def set_attributes_xml(ret_code: int = 0) -> str:
    """Return setMultiDeviceAttributes2 response."""

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ns1:setMultiDeviceAttributes2Response xmlns:ns1="http://arrayent.com/zamapi">'
        f"<retCode>{ret_code}</retCode>"
        "</ns1:setMultiDeviceAttributes2Response>"
    )


def device_list_xml(*device_ids: int) -> str:
    """Return getDeviceList response with the given devices, DEVICE_ID alone by default."""

    items = "".join(
        f"<devList><devId>{device_id}</devId><devName>Salus iT500</devName><typeId>100</typeId>"
        f"<sleepMode>0</sleepMode><appID>2</appID><userID>{USER_ID}</userID></devList>"
        for device_id in device_ids or (DEVICE_ID,)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<ns1:getDeviceListResponse xmlns:ns1="http://arrayent.com/zamapi">{items}</ns1:getDeviceListResponse>'
    )
