import logging
import asyncio
import json
import re


LOG = logging.getLogger(__name__)


class Processor:

    def __init__(self, config=None, loop=None):
        self.loop = loop if loop else asyncio.get_event_loop()
        self._mqtt = None
        self._dynet = None
        self._state = {}
        self._config = config

    def registerMQTT(self, mqtt=None):
        self._mqtt = mqtt

    def registerDynet(self, dynet=None):
        self._dynet = dynet

    @asyncio.coroutine
    def inboundMQTT(self, device=None, eventType=None, payload=None):
        if eventType is None or device is None:
            return
        if eventType == 'switch':
            areaPreset = self.MQTTNameToAreaPreset(mqttName=device)
            if not areaPreset:
                return
            if payload.upper() == 'ON':
                presetOn = True
            else:
                presetOn = False
            if presetOn:
                # Need to get default fade later
                if self._dynet:
                    self._dynet.setPreset(
                        area=areaPreset['area'], preset=areaPreset['preset'])
            updateData = self.updateState(
                area=areaPreset['area'], preset=areaPreset['preset'], presetOn=presetOn)
            if 'discoveryPayload' in updateData and 'discoveryMQTTName' in updateData:
                self.sendDiscovery(
                    discoveryMQTTName=updateData['discoveryMQTTName'], discoveryPayload=updateData['discoveryPayload'])
            presetChanges = self.sendPresetChange(
                area=areaPreset['area'], activePreset=areaPreset['preset'])
        elif eventType == 'status':
            areaPreset = self.MQTTNameToAreaPreset(mqttName=device)
            if not areaPreset:
                return
            LOG.debug("Ignoring status for %s: %s (%s)" %
                     (device, eventType, payload))
        else:
            # Unknown for now
            LOG.info("Unknown MQTT for %s: %s (%s)" %
                     (device, eventType, payload))

    @asyncio.coroutine
    def inboundDynalite(self, event=None):
        if event is None:
            return
        if event is not None and event.type == 'preset':
            updateData = self.updateState(area=event.area, preset=event.preset)
            if 'discoveryPayload' in updateData and 'discoveryMQTTName' in updateData:
                self.sendDiscovery(
                    discoveryMQTTName=updateData['discoveryMQTTName'], discoveryPayload=updateData['discoveryPayload'])
            presetChanges = self.sendPresetChange(
                area=event.area, activePreset=event.preset)
        else:
            LOG.error(event)

    def getMQTTName(self, area=None, preset=None):
        if area is None or preset is None:
            return
        return 'dyn_area_' + str(area) + '_preset_' + str(preset)

    def MQTTNameToAreaPreset(self, mqttName=None):
        if mqttName is None:
            return
        rx = r"^.*_area_(?P<area>\d+).*_preset_(?P<preset>\d+).*"
        m = re.search(rx, mqttName)
        if not m:
            return
        areaPreset = m.groupdict()
        if (areaPreset['area'] and areaPreset['preset']):
            areaPreset['area'] = int(areaPreset['area'])
            areaPreset['preset'] = int(areaPreset['preset'])
            return areaPreset

    def getLightName(self, area=None, preset=None):
        if area == None and preset == None:
            return None
        name = ''
        areaData = {}
        presetData = {}

        if area is not None:
            area = str(area)
            if 'area' in self._config and area in self._config['area']:
                areaData = self._config['area'][area]

            if not 'name' in areaData:
                areaData['name'] = 'Area ' + area

        if preset is not None:
            preset = str(preset)
            if areaData is not None and 'preset' in areaData and preset in areaData['preset']:
                presetData = areaData['preset'][preset]
            elif 'preset' in self._config and preset in self._config['preset']:
                presetData = self._config['preset'][preset]

            if not 'name' in presetData:
                presetData['name'] = 'Preset ' + area

        if areaData and 'name' in areaData:
            name = areaData['name']

        if presetData and 'name' in presetData:
            if len(name) > 0:
                name += ' '
            name += presetData['name']

        return name

    def updateState(self, area=None, preset=None, presetOn=True):
        if area is None or preset is None:
            return
        returnData = {}
        sendDiscovery = False
        if area in self._state:
            returnData['areaName'] = self._state[area]['name']
        else:
            sendDiscovery = True
            self._state[area] = {
                'name': self.getLightName(area=area),
                'preset': {},
                'state': {
                    'preset': preset,
                    'on': presetOn
                }
            }

        if preset in self._state[area]['preset']:
            self._state[area]['state']['preset'] = preset
            self._state[area]['state']['on'] = presetOn
        else:
            sendDiscovery = True
            self._state[area]['preset'][preset] = {
                'name': self.getLightName(area=area, preset=preset),
                'mqtt': self.getMQTTName(area=area, preset=preset)
            }

        if sendDiscovery:
            returnData['discoveryPayload'] = DiscoveryPayload(
                topic=self._config['mqtt']['topic'], mqttName=self._state[area]['preset'][preset]['mqtt'], lightName=self._state[area]['preset'][preset]['name']).getPayload()
            returnData['discoveryMQTTName'] = self._state[area]['preset'][preset]['mqtt']

        returnData['area'] = self._state[area]
        return returnData

    def sendPresetChange(self, area=None, activePreset=None):
        if area is None:
            return
        returnData = []
        if 'topic' in self._config['mqtt']:
            topicBase = self._config['mqtt']['topic'] + '/'
        else:
            topicBase = 'dynalite/'
        for preset in self._state[area]['preset']:
            newState = 'OFF'
            if preset == activePreset:
                newState = 'ON'
            topic = topicBase + \
                self._state[area]['preset'][preset]['mqtt'] + '/status'
            payloadBytes = str.encode(newState)
            if self._mqtt:
                returnData.append(self._mqtt.publish(
                    topic, payloadBytes, qos=0, retain=False))
        return returnData

    def sendDiscovery(self, discoveryMQTTName=None, discoveryPayload=None):
        if discoveryMQTTName is not None and discoveryPayload is not None and 'mqtt' in self._config and 'host' in self._config['mqtt'] and 'port' in self._config['mqtt'] and 'discovery' in self._config['mqtt'] and 'discovery_topic' in self._config['mqtt'] and self._config['mqtt']['discovery'] and self._config['mqtt']['discovery_topic'] is not None:
            discoveryTopic = self._config['mqtt']['discovery_topic'] + \
                '/light/' + discoveryMQTTName + '/config'
            payloadBytes = str.encode(discoveryPayload)
            if self._mqtt:
                return self._mqtt.publish(discoveryTopic, payloadBytes, qos=0, retain=False)


class DiscoveryPayload:

    def __init__(self, topic=None, mqttName=None, lightName=None):
        self.platform = 'mqtt'
        self.name = None
        self.qos = 0
        self.payload_on = 'ON'
        self.payload_off = 'OFF'
        self.optimistic = False

        if topic is not None:
            self.state_topic = topic + '/'
            self.command_topic = topic + '/'
            self.brightness_state_topic = topic + '/'
            self.brightness_command_topic = topic + '/'
        else:
            self.state_topic = 'dynalite/'
            self.command_topic = 'dynalite/'
            self.brightness_state_topic = 'dynalite/'
            self.brightness_command_topic = 'dynalite/'

        if mqttName is None and lightName is None:
            mqttName = 'dyn_unknown'
        elif mqttName is None and lightName is not None:
            mqttName = lightName.replace(" ", "_").lower()

        if lightName is not None:
            self.friendly_name = lightName
        else:
            self.friendly_name = "Unknown Light"

        self.name = self.friendly_name

        self.state_topic += mqttName + '/status'
        self.command_topic += mqttName + '/switch'
        self.brightness_state_topic += mqttName + '/brightness'
        self.brightness_command_topic += mqttName + '/brightness/set'

    def getPayload(self):
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=True)

    def __repr__(self):
        return str(self.__dict__)
