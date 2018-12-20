import asyncio
import socket
import time
import logging
from functools import partial
from .proto import Connection
from .event import DynaliteEvent

LOG = logging.getLogger(__name__)

def get_dynet_sync(msg):
    """Return the sync code in the message."""
    if len(msg) < 8:
        return False
    return msg[0]

def get_dynet_command(msg):
    """Return the opcode in the message."""
    if len(msg) < 8:
        return False
    return msg[3]

def get_dynet_area(msg):
    """Return area the message is intended for."""
    if len(msg) < 8:
        return False
    return msg[1]

def get_dynet_data(msg):
    """Return the three data bytes from a dynet message."""
    if len(msg) < 8:
        return False
    return bytearray([msg[2], msg[4], msg[5]])

def get_dynet_join(msg):
    """Return the join mask of a dynet message."""
    if len(msg) < 8:
        return False
    return msg[6]

def get_dynet_checksum(msg):
    """Return the checksum of a dynet message."""
    if len(msg) < 8:
        return False
    return msg[7]

def opcodebank_to_preset(opcode, bank):
    if opcode > 3:
        opcode = opcode - 6
    return (opcode + (bank * 8)) + 1

def fadeLowHigh256_to_seconds(fadeLow, fadeHigh):
    return (fadeLow + (fadeHigh * 256)) * 0.02


class Dynalite:

    def __init__(self, config, loop=None):
        ''' Constructor for this class. '''
        self.loop = loop if loop else asyncio.get_event_loop()
        self._config = config
        self._conn = None
        self._transport = None
        self.connection_lost_callbk = None
        self._connection_retry_timer = 1

        self._event_handlers = {}

        self._heartbeat = None

        # How many bytes in a message (not including checksum)
        self.messagesize = 7
        self.template = bytearray([28, 0, 0, 0, 0, 0, 0])
        self.connected = False
        self.timeout = 900
        self.areaPresets = {}

    async def _connect(self, connection_lost_callbk=None):
        """Asyncio connection to Dynalite."""
        self.connection_lost_callbk = connection_lost_callbk
        host = self._config['host']
        port = self._config['port']
        LOG.info("Connecting to Dynalite at %s", host)
        conn = partial(Connection, self.loop, self._connected,
                       self._disconnected, self._got_data)
        try:
            await asyncio.wait_for(self.loop.create_connection(
                conn, host=host, port=port), timeout=30)
        except (ValueError, OSError, asyncio.TimeoutError) as err:
            LOG.warning("Could not connect to Dynalite (%s). Retrying in %d seconds",
                        err, self._connection_retry_timer)
            self.loop.call_later(self._connection_retry_timer, self.connect)
            self._connection_retry_timer = 2 * self._connection_retry_timer \
                if self._connection_retry_timer < 32 else 60

    def _connected(self, transport, conn):
        """Connected to Dynalite"""
        LOG.info("Connected to Dynalite")
        self._conn = conn
        self._transport = transport
        self._connection_retry_timer = 1
        self._heartbeat = self.loop.call_later(120, self._reset_connection)

    def _reset_connection(self):
        LOG.warning("Dynalite connection heartbeat timed out, disconnecting")
        self._transport.close()
        self._heartbeat = None

    def _disconnected(self):
        LOG.warning("Dynalite disconnected")
        self._conn = None
        self.loop.call_later(self._connection_retry_timer, self.connect)
        if self._heartbeat:
            self._heartbeat.cancel()
            self._heartbeat = None

    def _got_data(self, data):  # pylint: disable=no-self-use

        if self._heartbeat:
            self._heartbeat.cancel()
            self._heartbeat = self.loop.call_later(120, self._reset_connection)
        try:
            LOG.debug("got_data '%s'", data)
            self.loop.create_task(self.process_message(data))
        except ValueError as err:
            LOG.debug(err)

    def connect(self):
        """Connect to the Dynalite"""
        asyncio.ensure_future(self._connect())

    def run(self):
        """Enter the asyncio loop."""
        self.loop.run_forever()

    def addHandler(self, handlerName, handlerFn):
        """Add a handler"""
        self._event_handlers[handlerName] = handlerFn

    def delHandler(self, handlerName):
        """Add a handler"""
        self._event_handlers[handlerName] = None

    def getAreaPresets(self, area):
        if area not in self.areaPresets:
            self.areaPresets[area] = {}
        return self.areaPresets[area]

    def setAreaPreset(self, area, preset, state=None):
        if area not in self.areaPresets:
            self.areaPresets[area] = {}
            event = DynaliteEvent()
            event.type = 'newarea'
            event.area = area
            self.loop.create_task(self.handler(event))
        if preset not in self.areaPresets[area]:
            self.areaPresets[area][preset] = AreaPreset(area, preset, self)
            event = DynaliteEvent()
            event.type = 'newpreset'
            event.area = area
            event.preset = preset
            event.object = self.areaPresets[area][preset]
            self.loop.create_task(self.handler(event))
        if state is not None:
            self.areaPresets[area][preset].setState(state)
            if state is True:
                self.areaPresets[area]['_current'] = preset
                for p in self.areaPresets[area]:
                    if p != preset and p != '_current':
                        self.areaPresets[area][p].setState(state)

    def handler(self, event):
        if(event):
            for fnName in self._event_handlers:
                try:
                    LOG.debug("Calling event handler %s" % fnName)
                    yield from self._event_handlers[fnName](event)
                except Exception as e:
                    LOG.error("Couldn't call handler function %s (%s)" %
                              (fnName, e))
                    raise

    @asyncio.coroutine
    def process_message(self, msg):
        LOG.debug("Processing message %s" % msg)
        if self.valid_checksum(msg) is not True:
            return False
        sync = msg[0]
        area = msg[1]
        data1 = msg[2]
        opcode = msg[3]
        data2 = msg[4]
        data3 = msg[5]
        join = msg[6]
        chk = msg[7]

        if sync != 28:
            event = DynaliteEvent(data)
            event.type = 'in'
            event.error = 'Not a logical message'
            self.loop.create_task(self.handler(event))
            return False

        if opcode < 4 or (opcode > 9 and opcode < 14):
            presetChange = PresetOpcode()
            presetChange.fromMsg(msg=msg)
            event = DynaliteEvent()
            event.type = 'preset'
            event.area = presetChange.area
            event.preset = presetChange.preset
            event.fade = presetChange.fade
            event.join = presetChange.join
            event.msg = msg
        elif opcode == 72:
            event = self.process_indicatorled(area, data1, data2, data3, join)
            event.msg = msg
        elif opcode == 98:
            event = self.process_areastatus(area, data1)
            event.msg = msg
        elif opcode == 99:
            event = self.process_reqareastatus(area)
            event.msg = msg
        elif opcode == 101:
            event = self.process_linearpreset(area, data1, data2, data3, join)
            event.msg = msg
        else:
            event = DynaliteEvent(msg)
            event.type = 'unknown'
            event.area = area

        self.loop.create_task(self.handler(event))

        if len(msg) > self.messagesize + 1:
            LOG.info("Extra %s bytes:\t%s" %
                     (len(msg) - self.messagesize + 1, msg[self.messagesize + 1:]))
            self.loop.create_task(
                self.process_message(msg[self.messagesize + 1:]))

    def valid_checksum(self, msg):
        if len(msg) < self.messagesize + 1:
            return False
        tocheck = bytearray(
            [msg[0], msg[1], msg[2], msg[3], msg[4], msg[5], msg[6]])
        chk = int(self.calc_checksum(tocheck), 16)
        if msg[7] != chk:
            return False
        return True

    def calc_checksum(self, s):
        """
        Calculates checksum for sending commands to the ELKM1.
        Sums the ASCII character values mod256 and returns
        the lower byte of the two's complement of that value.
        """
        return '%2X' % (-(sum(ord(c) for c in "".join(map(chr, s))) % 256) & 0xFF)

    def send(self, data):
        """Send a message to Dynalite panel."""
        if self._conn:
            data.append(int(self.calc_checksum(data), 16))
            self.loop.create_task(self._send(data))

    @asyncio.coroutine
    def _send(self, message=None):
        if self._conn:
            LOG.info("Dynalite Send: %s" % message)
            self._conn.write_data(message)

    def _sendResponse(response=None):
        LOG.info(response)
        # event = DynaliteEvent(data)
        # event.type = 'out'
        # self.loop.create_task(self.handler(event))
        # self.loop.create_task(self.process_message(data))

    def process_preset(self, area, opcode, fadeLow, fadeHigh, bank, join):
        preset = (opcode + (bank * 8)) + 1
        fade = (fadeLow + (fadeHigh * 256)) * 0.02
        event = DynaliteEvent()
        event.type = 'preset'
        event.area = area
        event.preset = preset
        event.fade = fade
        return event

    def preset_to_opcodebank(self, preset):
        """Convert a Preset to a OpCode / Bank Pair"""
        bank = int((preset - 1) / 8)
        opcode = int(preset - (bank * 8)) - 1
        if opcode > 3:
            opcode = opcode + 6
        return bytearray([opcode, bank])

    def process_linearpreset(self, area, preset, fadeLow, fadeHigh, join):
        preset = preset + 1
        fade = (fadeLow + (fadeHigh * 256)) * 0.02
        event = DynaliteEvent()
        event.type = 'preset'
        event.area = area
        event.preset = preset
        event.fade = fade
        return event

    def process_indicatorled(self, area, type, dimming, fadeVal, join):
        if type == 1:
            typeName = 'indicator'
        elif type == 2:
            typeName = 'backlight'
        else:
            typeName = 'unknown'

        if fadeVal > 0:
            fade = fadeVal / 50
        else:
            fade = 0

        dimpc = round((256 - dimming) / 255, 2) * 100

        event = DynaliteEvent()
        event.type = 'indicator_' + typeName
        event.area = area
        event.dim = dimpc
        event.fade = fade
        return event

    def process_areastatus(self, area, preset):
        preset = preset + 1
        event = DynaliteEvent()
        event.type = 'presetupdate'
        event.area = area
        event.preset = preset
        return event

    def process_reqareastatus(self, area):
        event = DynaliteEvent()
        event.type = 'presetrequest'
        event.area = area
        return event

    def reqPreset(self, area):
        cmd = self.template[:]
        cmd[1] = area
        cmd[3] = 99
        cmd[6] = 255
        self.send(cmd)
        return True

    def setPreset(self, area, preset, fade=2, join=255):
        cmd = self.template[:]
        cmd[1] = area
        if fade == 0:
            cmd[2] = 0
            cmd[4] = 0
        else:
            cmd[2] = int(fade / 0.02) - (int((fade / 0.02) / 256) * 256)
            cmd[4] = int((fade / 0.02) / 256)

        cmd[6] = join

        if preset < 1:
            return False
        elif preset > 64:
            return False

        bank = int((preset - 1) / 8)
        opcode = int(preset - (bank * 8)) - 1

        if opcode > 3:
            opcode = opcode + 6

        cmd[3] = opcode
        cmd[5] = bank

        self.send(cmd)
        return True

    def setIndicatorLED(self, area, type, dimpc, fadeVal=2, join=255):
        cmd = self.template[:]
        cmd[1] = area
        cmd[2] = type
        cmd[3] = 72

        if dimpc == 0:
            cmd[4] = 255
        elif dimpc == 1:
            cmd[4] = 255
        elif dimpc < 0:
            cmd[4] = 255
        elif dimpc > 100:
            cmd[4] = 1
        else:
            cmd[4] = int(256 - (dimpc / 100 * 255))

        if fadeVal < 0:
            cmd[5] = 0
        elif fadeVal > 5:
            cmd[5] = 255
        else:
            cmd[5] = int(fadeVal * 50)

        cmd[6] = join
        self.send(cmd)
        return True


class PresetOpcode:

    def __init__(self):
        self.area = None
        self.preset = None
        self.fade = None
        self.join = None

    def fromMsg(self,msg=None):
        if msg is None:
            return
        opcode = get_dynet_command(msg)
        data = get_dynet_data(msg)
        self.area = get_dynet_area(msg)
        self.preset = opcodebank_to_preset(opcode, data[2])
        self.fade = fadeLowHigh256_to_seconds(data[0], data[1])
        self.join = get_dynet_join(msg)
