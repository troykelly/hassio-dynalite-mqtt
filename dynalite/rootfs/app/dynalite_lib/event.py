class DynaliteEvent:
    type = 'unknown'
    area = None
    preset = None
    status = None
    host = None
    port = None
    fade = None
    dim = None
    msg = None
    object = None

    def __init__(self, msg=None):
        self.msg = msg

    def __repr__(self):
        return str(self.__dict__)
