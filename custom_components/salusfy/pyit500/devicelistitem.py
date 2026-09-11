"""Module to provide the DeviceListItem class"""

from .auth import Auth
from .parsing import parse_response


class DeviceListItem:
    """Class that represents a Device as represented in the Device List in the Salus iT500 API."""

    # Constructor
    def __init__(self, raw_data: dict, auth: Auth):
        """Initialise a device list item object."""
        self.raw_data = raw_data
        self.auth = auth

    # Device Class Methods
    @classmethod
    async def async_get_device_list(cls, auth) -> list["DeviceListItem"]:
        """Return a list of Device List Items."""
        response = parse_response(
            await auth.request("post", "getDeviceList"),
            "ns1:getDeviceListResponse",
            force_list=("devList",),
        )
        return [DeviceListItem(device_list_item, auth) for device_list_item in (response or {}).get("devList", [])]

    @property
    def device_id(self) -> int:
        """Return the ID of the device."""
        return self.raw_data["devId"]

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self.raw_data["devName"]

    @property
    def type_id(self) -> int:
        """Return the type ID of the device."""
        return self.raw_data["typeId"]

    @property
    def sleep_mode(self) -> str:
        """Return the sleep mode of the device."""
        return self.raw_data["sleepMode"]

    @property
    def app_id(self) -> int:
        """Return the app ID of the device."""
        return self.raw_data["appID"]

    @property
    def user_id(self) -> int:
        """Return the user ID of the device."""
        return self.raw_data["userID"]
