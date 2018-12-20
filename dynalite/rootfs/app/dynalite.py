#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import asyncio
import json
import string
import random
from urllib.parse import quote

from mqtt import DynMQTT
from dynalite_lib import Dynalite
from processor import Processor

logger = logging.getLogger(__name__)

with open('/data/options.json', 'r') as f:
        cfg = json.load(f)

def validateConfig():
    if not 'mqtt' in cfg:
        cfg['mqtt'] = {}
    if not 'host' in cfg['mqtt']:
        cfg['mqtt']['host'] = 'localhost'
    if not 'port' in cfg['mqtt']:
        cfg['mqtt']['port'] = 1833
    if not 'protocol' in cfg['mqtt']:
        cfg['mqtt']['protocol'] = 'mqtt'
    if not 'topic' in cfg['mqtt']:
        cfg['mqtt']['topic'] = 'dynalite'
    if not 'discovery_topic' in cfg['mqtt']:
        cfg['mqtt']['discovery_topic'] = 'homeassistant'
    if not 'client_id' in cfg['mqtt']:
        cfg['mqtt']['client_id'] = cfg['mqtt']['topic'] + '/' + \
            ''.join(random.sample(string.ascii_lowercase, 16))
    if not 'discovery' in cfg['mqtt']:
        cfg['mqtt']['discovery'] = True

    if not 'uri' in cfg['mqtt']:
        cfg['mqtt']['uri'] = cfg['mqtt']['protocol'] + '://'
        if 'username' in cfg['mqtt']:
            cfg['mqtt']['uri'] += quote(cfg['mqtt']['username'])
            if 'password' in cfg['mqtt']:
                cfg['mqtt']['uri'] += ':' + quote(cfg['mqtt']['password'])
            cfg['mqtt']['uri'] += '@'
        cfg['mqtt']['uri'] += cfg['mqtt']['host'] + \
            ":" + str(cfg['mqtt']['port'])

    if not 'dynalite' in cfg:
        cfg['dynalite'] = {}
    if not 'host' in cfg['dynalite']:
        cfg['dynalite']['host'] = 'localhost'
    if not 'port' in cfg['dynalite']:
        cfg['dynalite']['port'] = 12345


if __name__ == '__main__':
    formatter = "[%(asctime)s] %(name)s {%(filename)s:%(lineno)d} %(levelname)s - %(message)s"
    logging.basicConfig(level=logging.INFO, format=formatter)
    validateConfig()
    loop = asyncio.get_event_loop()
    mq = DynMQTT(cfg['mqtt'], loop)
    dynet = Dynalite(cfg['dynalite'], loop)
    processor = Processor(config=cfg, loop=loop)
    mq.connect()
    dynet.connect()
    processor.registerMQTT(mqtt=mq)
    processor.registerDynet(dynet=dynet)
    mq.subscribe(cfg['mqtt']['topic'] + '/#', processor.inboundMQTT)
    dynet.addHandler('dynetToMQTT', processor.inboundDynalite)
    loop.run_forever()
