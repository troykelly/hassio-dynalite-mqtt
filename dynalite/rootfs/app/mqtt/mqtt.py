import logging
import asyncio

from hbmqtt.client import MQTTClient, ConnectException, ClientException
from hbmqtt.mqtt.constants import QOS_0, QOS_1, QOS_2

LOG = logging.getLogger(__name__)


class DynMQTT:

    def __init__(self, config=None, loop=None):
        self.loop = loop if loop else asyncio.get_event_loop()
        self._config = config
        self._conn = None
        self._client = MQTTClient(
            client_id=self._config['client_id'], loop=self.loop)

    def connect(self):
        self.loop.run_until_complete(self._connect())

    @asyncio.coroutine
    def _connect(self):
        try:
            yield from self._client.connect(self._config['uri'])
        except ConnectException as ce:
            LOG.error("Connect exception: %s" % ce)
            exit(1)

    def publish(self, topic=None, payload=None, qos=0, retain=False):
        self.loop.create_task(self._publish(topic, payload, qos, retain))

    @asyncio.coroutine
    def _publish(self, topic=None, payload=None, qos=0, retain=False):
        LOG.info("Publishing to topic %s: %s" % (topic, payload))
        try:
            yield from self._client.publish(topic, payload, qos=qos, retain=retain)
        except Exception as e:
            LOG.error("Failed to publish: %s" % e)

    def subscribe(self, topic, handler=None):
        self.loop.create_task(self._subscribe(topic, handler))

    @asyncio.coroutine
    def _subscribe(self, topic, handler=None):
        yield from self._client.subscribe([
            (topic, QOS_0)
        ])
        LOG.info("MQTT Subscribed to %s" % topic)
        while True:
            try:
                message = yield from self._client.deliver_message()
                if message:
                    packet = message.publish_packet
                    yield from self.processInbound(packet, handler)
            except ClientException as ce:
                LOG.error("Client exception: %s" % ce)
                exit(1)

    @asyncio.coroutine
    def unsubscribe(self, topic):
        try:
            yield from self._client.unsubscribe([topic])
            LOG.info("MQTT Subscribed to %s" % topic)
        except ClientException as ce:
            LOG.error("Client exception: %s" % ce)

    @asyncio.coroutine
    def disconnect(self):
        try:
            yield from self._client.disconnect()
            LOG.info("MQTT Disconnected")
        except ClientException as ce:
            LOG.error("Client exception: %s" % ce)

    @asyncio.coroutine
    def processInbound(self, packet, handler):
        if handler is None:
            LOG.debug("No MQTT Handler for %s => %s" %
                  (packet.variable_header.topic_name, str(packet.payload.data)))
        else:
            if not packet.variable_header.topic_name.startswith(self._config['topic'] + '/'):
                LOG.error("Ignoring topic %s" % packet.variable_header.topic_name)
                return
            event = packet.variable_header.topic_name[len(self._config['topic'])+1:].split('/')
            if len(event) != 2:
                LOG.error("Unknown MQTT Topic: %s (%s)" % (packet.variable_header.topic_name, event))
                return
            try:
                payload = packet.payload.data.decode("utf-8")
            except:
                payload = packet.payload.data

            try:
                payload = json.loads(payload)
            except:
                pass
            yield from handler(device=event[0], eventType=event[1],
                               payload=payload)
