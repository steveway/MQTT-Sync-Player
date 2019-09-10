#
# PyQt5-based video-sync example for VLC Python bindings
# Copyright (C) 2009-2010 the VideoLAN team
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston MA 02110-1301, USA.
#
"""
Based on the vlc videosync example from Saveliy Yusufov
Author: Stefan Murawski | @steveway
"""

import logging
import threading

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

logger.setLevel(logging.DEBUG)

# create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# create formatter
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)


class Server:
    """Data sender server"""

    def __init__(self, client_id, host, port, topic, data_queue):
        self.data_queue = data_queue
        self.client = mqtt.Client(client_id, clean_session=True, protocol=mqtt.MQTTv31)  # create new instance
        self.client.connect(host, port, 300)
        self.topic = "$" + topic
        self.client.on_connect = self.on_connect
        self.is_connected = False
        self.client.loop(.05)
        t = threading.Thread(target=self.data_sender, args=())
        t.daemon = True
        t.start()

    def on_connect(self, client, userdata, flags, rc):
        print("connect: " + str(rc))
        self.is_connected = True

    def data_sender(self):
        while True:
            self.client.loop(.05)
            if self.is_connected:
                data = "{},".format(self.data_queue.get())
                self.client.publish(self.topic, data.encode())

    def disconnect(self):
        self.client.disconnect()


class Client:
    """Data receiver client"""

    def __init__(self, client_id, host, port, topic, data_queue):
        self.data_queue = data_queue

        self.client = mqtt.Client(client_id, clean_session=True, protocol=mqtt.MQTTv31)  # create new instance
        self.client.connect(host, port, 300)
        self.is_connected = False
        self.client.subscribe("$" + topic + "/#")
        self.client.on_message = self.data_receiver
        self.client.on_subscribe = self.on_subscribe
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, rc):
        print("connect: " + str(rc))
        self.is_connected = True

    def data_receiver(self, client, userdata, message):
        """Handles receiving, parsing, and queueing data"""

        data = str(message.payload.decode())
        print("Received: ")
        print(data)
        if data:
            for chara in data.split(','):
                if chara:
                    if chara == 'd':
                        self.data_queue.queue.clear()
                    else:
                        self.data_queue.put(chara)

    def on_subscribe(self, mqttc, obj, mid, granted_qos):
        print("Subscribed: " + str(mid) + " " + str(granted_qos))

    def disconnect(self):
        self.client.disconnect()
