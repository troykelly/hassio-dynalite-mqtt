class AreaPreset:
    area = None
    preset = None

    def __init__(self, area, preset, dynet):
        self.area = area
        self.preset = preset
        self._state = False

    def turn_on(self):
        dynet.setPreset(self.area, self.preset)
        self._state = True
        return True

    def turn_off(self):
        self._state = False
        return True

    def ison(self):
        return self._state

    def update(self):
        dynet.reqPreset(self.area)

    def setState(self, state):
        self._state = state

    def __repr__(self):
        return str(self.__dict__)
