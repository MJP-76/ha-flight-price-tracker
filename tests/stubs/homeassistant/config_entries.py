"""Config entry stubs."""

SOURCE_REAUTH = "reauth"


class ConfigEntry:
    def __init__(self, entry_id="", title="", data=None, options=None, state=None):
        self.entry_id = entry_id
        self.title = title
        self.data = data or {}
        self.options = options or {}
        self.state = state

    def add_update_listener(self, listener):
        return listener


class ConfigFlowResult(dict):
    pass


class ConfigFlow:
    domain = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if "domain" in kwargs:
            cls.domain = kwargs["domain"]


class OptionsFlow:
    pass
