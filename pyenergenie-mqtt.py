# Based upon:
# - https://github.com/jeremypoulter/pyenergenie/blob/master/src/switch.py
# - https://github.com/whaleygeek/pyenergenie/blob/master/src/mihome_energy_monitor.py
import sys
import time
import signal
sys.path.insert(1, './pyenergenie/src')
import energenie as energenie
import energenie.Devices as energenieDevices
import paho.mqtt.client as mqtt
import Queue
import threading

# TODO: Make logging configurably verbose
# TODO: Log errors to separate output, so they can more easily be discovered
# TODO: Configure last_will on energenie_tx_mqtt so that we know when it has disappeared
# TODO: Move configuration into configuration file
#	https://martin-thoma.com/configuration-files-in-python/
# TODO: Use a single mqtt client to better handle shutdowns gracefully

mqtt_hostname = "localhost"
mqtt_port = 1883
mqtt_keepalive = 10
mqtt_username = ""
mqtt_password = ""
mqtt_client_id = "agn-sensor01-lon_energenie"
mqtt_subscribe_client_id = "agn-sensor01-lon_pyenergenie_subscribe"
mqtt_clean_session = True
mqtt_publish_topic = "emon"
mqtt_subscribe_topic = "energenie"

mqtt_status_topic_suffix = "status"
mqtt_status_topic = mqtt_publish_topic + "/" + mqtt_client_id + "/" + mqtt_status_topic_suffix
mqtt_status_topic_subscribe = mqtt_publish_topic + "/" + mqtt_subscribe_client_id + "/" + mqtt_status_topic_suffix
mqtt_status_msg_connected = "connected"
mqtt_status_msg_disconnected = "disconnected"
mqtt_status_msg_lastwill = "unexpected_outage"

# TODO: Figure out how not to have these copied from the other file
MFRID_ENERGENIE                  = 0x04
PRODUCTID_MIHO004                = 0x01   #         Monitor only
PRODUCTID_MIHO005                = 0x02   #         Adaptor Plus
PRODUCTID_MIHO006                = 0x05   #         House Monitor
PRODUCTID_MIHO032                 = 0x0C  # FSK motion sensor
PRODUCTID_MIHO033                 = 0x0D    # FSK open sensor
ENERGENIE_SLEEP_WAIT = 2
MQTT_SLEEP_WAIT = 0.2

q_rx_mqtt = Queue.Queue()
q_rx_energenie = Queue.Queue()
q_tx_mqtt = Queue.Queue()
q_tx_energenie = Queue.Queue()

rx_mqtt_client_connected = False

# Helping with graceful quit https://stackoverflow.com/a/31464349/443588
class GracefulKiller:
	kill_now = False
	def __init__(self):
		signal.signal(signal.SIGINT, self.exit_gracefully)
		signal.signal(signal.SIGTERM, self.exit_gracefully)

	def exit_gracefully(self,signum, frame):
		self.kill_now = True

programkiller = GracefulKiller()


# The callback for when the client receives a CONNACK response from the server.
def rx_mqtt_on_connect(client, userdata, flags, rc):
	global mqtt_subscribe_topic
	global rx_mqtt_client_connected

	print("rx_mqtt: Connected to %s:%s with result code %s" % (client._host, client._port, rc))
	rx_mqtt_client_connected = True
	print("rx_mqtt: Set rx_mqtt_client_connected as True = " + str(rx_mqtt_client_connected))

	# Subscribing in on_connect() means that if we lose the connection and
	# reconnect then subscriptions will be renewed.
	print("rx_mqtt: Subscribing to " + mqtt_subscribe_topic + "/#")
	client.subscribe(mqtt_subscribe_topic + "/#")

	print("rx_mqtt: Publishing '" + mqtt_status_msg_connected + "' to '" + mqtt_status_topic_subscribe + "' and setting last will to '" + mqtt_status_msg_lastwill + "'")
	# Send a status message so that watchers know what's going on
	client.publish(topic=mqtt_status_topic_subscribe, payload=mqtt_status_msg_connected, qos=1, retain=True)

	# Set last will message, so if connection is lost watchers will know
	client.will_set(topic=mqtt_status_topic_subscribe, payload=mqtt_status_msg_lastwill, qos=1, retain=True)

def rx_mqtt_on_disconnect(client, userdata, flags, rc):
	global rx_mqtt_client_connected
	rx_mqtt_client_connected = False
	print("rx_mqtt: Disconnected with result code " + str(rc))
	print("rx_mqtt: Stopping mqtt subscribe client loop...")
	client.loop_stop()

def rx_mqtt_on_subscribe(client, userdata, mid, granted_qos):
	print("rx_mqtt_on_subscribe: Subcribed for receiving mqtt - " + str(mid) + " with QoS="+str(granted_qos))

# The callback for when a PUBLISH message is received from the server.
def rx_mqtt_on_message(client, userdata, msg):
	global q_rx_mqtt
	q_rx_mqtt.put(msg)



def rx_mqtt():
	global mqtt_hostname
	global mqtt_port
	global mqtt_keepalive
	global mqtt_username
	global mqtt_password
	global mqtt_subscribe_client_id
	global mqtt_clean_session
	global mqtt_subscribe_topic
	global q_rx_mqtt
	global rx_mqtt_client_connected

	fromMqtt = mqtt.Client(client_id=mqtt_subscribe_client_id, clean_session=mqtt_clean_session)

	print("rx_mqtt: Starting mqtt subscribing loop...")
	while not programkiller.kill_now:
		try:
			fromMqtt.on_connect = rx_mqtt_on_connect
			fromMqtt.on_disconnect = rx_mqtt_on_disconnect
			fromMqtt.on_subscribe = rx_mqtt_on_subscribe
			fromMqtt.on_message = rx_mqtt_on_message

			if mqtt_username != "":
				fromMqtt.username_pw_set(mqtt_username, mqtt_password)
			
			print("rx_mqtt: Connecting after this...")
			fromMqtt.connect(mqtt_hostname, mqtt_port, mqtt_keepalive)

			# Blocking call that processes network traffic, dispatches callbacks and
			# handles reconnecting.
			# Other loop*() functions are available that give a threaded interface and a
			# manual interface.
			print("rx_mqtt: Looping forever after this...")
			while not programkiller.kill_now:
				fromMqtt.loop(timeout=MQTT_SLEEP_WAIT)
		except Exception as e:
			print("rx_mqtt: exception occurred")
			print(e)
		finally:
			if not programkiller.kill_now:
				print("rx_mqtt: Restarting...")
	
	print("rx_mqtt: Asked to terminate, sending '" + mqtt_status_msg_disconnected + "' to mqtt '" + mqtt_status_topic_subscribe + "' then disconnecting...")
	fromMqtt.publish(topic=mqtt_status_topic_subscribe, payload=mqtt_status_msg_disconnected, qos=1, retain=True)
	fromMqtt.disconnect()


def mqtt_tx_energenie(msg):
	try:
		print("mqtt_tx_energenie: " + msg.topic + " " + str(msg.payload))

		topic_parts = msg.topic.split("/", 3)
		name = topic_parts[1]
		action = topic_parts[2]
		device = energenie.registry.get(name)
		
		if len(topic_parts) == 2 or action == "switch" or action == "":
			if str(msg.payload) == "1" or (str(msg.payload)).lower() == "true" or (str(msg.payload)).lower() == "on":
				print("mqtt_tx_energenie: " + name + " - switch - " + str(msg.payload) + "/on")
				device.turn_on()
			else:
				print("mqtt_tx_energenie: " + name + " - switch - " + str(msg.payload) + "/off")
				device.turn_off()
		#elif action == "otheractionnamehere":
		#	print("mqtt_tx_energenie: action '" + action + "' for '" + name + "' containing '" + msg.payload + "'" )
		else:
			# Action not found
			print("mqtt_tx_energenie: action '" + action + "' unknown, nothing sent")
	except Exception as e:
		print("mqtt_tx_energenie: Exception occurred")
		print(e)


def rx_energenie(address, message):
	global q_rx_energenie

	#print("rx_energenie: new message from " + str(address) )

	if address[0] == MFRID_ENERGENIE:
		# Retrieve list of names from the registry, so we can refer to the name of the device
		for devicename in energenie.registry.names():
			#print("rx_energenie: checking if message from " + devicename)

			# Using the name, retrieve the device
			d = energenie.registry.get(devicename)

			# Check if the message is from the current device of this iteration
			if address[2] == d.get_device_id():
				# Yes we found the device, so add to processing queue
				#print("rx_energenie: Queuing message from " + str(address) + " - " + devicename)
				newQueueEntry = {'DeviceName': devicename, 'DeviceType': address[1]}
				q_rx_energenie.put(newQueueEntry)
				# The device was found, so break from the for loop
				break
	else:
		print("rx_energenie: Not an energenie device " + str(address))



def rx_energenie_process():
	global q_rx_energenie

	while True:
		try:
			#print("rx_energenie_process: awaiting item in q_rx_energenie...")
			refreshed_device = q_rx_energenie.get()
			d = energenie.registry.get( refreshed_device['DeviceName'] )

			item = {'DeviceName': refreshed_device['DeviceName'], 'DeviceType': refreshed_device['DeviceType'], 'data': {}}
			for metric_name in dir(d.readings):
				if not metric_name.startswith("__"):
					value = getattr(d.readings, metric_name)
					item['data'][metric_name] = value
			q_tx_mqtt.put(item)

			q_rx_energenie.task_done()
		except Exception as e:
			print("rx_energenie_process: exception occurred")
			print(e)


			
def energenie_tx_mqtt():
	global mqtt_hostname
	global mqtt_port
	global mqtt_keepalive
	global mqtt_username
	global mqtt_password
	global mqtt_client_id
	global mqtt_clean_session
	global mqtt_publish_topic
	global q_tx_mqtt

	energenie_tx_mqtt_client_connected = False

	def energenie_tx_mqtt_on_connect(client, userdata, flags, rc):
		global energenie_tx_mqtt_client_connected
		if rc == 0:
			#print("energenie_tx_mqtt: client connected")
			client.is_connected = True
			energenie_tx_mqtt_client_connected = True

			print("rx_mqtt: Publishing '" + mqtt_status_msg_connected + "' to '" + mqtt_status_topic + "' and setting last will to '" + mqtt_status_msg_lastwill + "'")
			# Send a status message so that watchers know what's going on
			client.publish(topic=mqtt_status_topic, payload=mqtt_status_msg_connected, qos=1, retain=True)

			# Set last will message, so if connection is lost watchers will know
			client.will_set(topic=mqtt_status_topic_subscribe, payload=mqtt_status_msg_lastwill, qos=1, retain=True)
		else:
			print("energenie_tx_mqtt: Bad connection; rc = "+str(rc))
	
	def energenie_tx_mqtt_on_disconnect(client, userdata, rc):
		global energenie_tx_mqtt_client_connected
		#print("energenie_tx_mqtt: client disconnected " + str(rc))
		client.is_connected = False
		energenie_tx_mqtt_client_connected = False
		#client.loop_stop()
	
	def energenie_tx_mqtt_on_publish(client, userdata, mid):
		#print("energenie_tx_mqtt: publish of " + str(mid) + " successful")
		pass

	#TODO: Move client instantiation outside of loop, manage connection status with single object
	while True:
		print("energenie_tx_mqtt: creating mqtt.client...")
		toMqtt = mqtt.Client(client_id=mqtt_client_id, clean_session=mqtt_clean_session)
		toMqtt.is_connected = False
		toMqtt.on_connect = energenie_tx_mqtt_on_connect
		toMqtt.on_disconnect = energenie_tx_mqtt_on_disconnect
		toMqtt.on_publish = energenie_tx_mqtt_on_publish

		if mqtt_username <> "":
			print("energenie_tx_mqtt: using username and password...")
			toMqtt.username_pw_set(mqtt_username, mqtt_password)
		print("energenie_tx_mqtt: connecting to mqtt broker...")
		toMqtt.connect(mqtt_hostname, mqtt_port, mqtt_keepalive)
		print("energenie_tx_mqtt: toMqtt.loop_start() thread starting...")
		toMqtt.loop_start()

		#while not toMqtt.is_connected:
		#	print("energenie_tx_mqtt: waiting to ensure connection...")
		#	time.sleep(0.5)
		
		while not programkiller.kill_now:
			try:
				#print("energenie_tx_mqtt: awaiting item in q_tx_mqtt...")
				item = q_tx_mqtt.get(block=False, timeout=MQTT_SLEEP_WAIT)

				#print("energenie_tx_mqtt: publishing item for " + item['DeviceName'] + " (" + str(item['DeviceType']) + ") found on queue...")
				#print(str(item))

				data = item['data']

				for metric in data.keys():
					value = data[metric]
					if value == True and type(value) == type(True):
						value = 1
					elif data[metric] == None:
						value = ""

					publish_topic = mqtt_publish_topic + "/" + item['DeviceName'] + "/" + metric
					#print("energenie_tx_mqtt: publishing '" + str( value ) + "' to topic " + publish_topic)
					publish_result = toMqtt.publish(publish_topic, value)
					#print("energenie_tx_mqtt: publish returned " + str(publish_result[1]))
				q_tx_mqtt.task_done()
			except Queue.Empty as e:
				# Empty queue means no payloads pending to be sent, so just loop again
				pass
			except Exception as e:
				print("energenie_tx_mqtt: exception occurred")
				print(e)
				if not toMqtt.is_connected:
					print("energenie_tx_mqtt: mqtt client no longer connected, breaking processing loop")
					break
		
		print("energenie_tx_mqtt: toMqtt.is_connected == " + str(toMqtt.is_connected))
		print("energenie_tx_mqtt: toMqtt.loop_stop()")
		toMqtt.loop_stop()
		if not programkiller.kill_now:
			print("energenie_tx_mqtt: sleeping for 5 seconds before restarting thread")
			time.sleep(5)
		else:
			print("rx_mqtt: Asked to terminate, sending '" + mqtt_status_msg_disconnected + "' to mqtt '" + mqtt_status_topic + "' then disconnecting...")
			toMqtt.publish(topic=mqtt_status_topic, payload=mqtt_status_msg_disconnected, qos=1, retain=True)
			toMqtt.disconnect()
			break

			

def main():
	global mqtt_hostname
	global mqtt_port
	global mqtt_keepalive
	global mqtt_username
	global mqtt_password
	global mqtt_client_id
	global mqtt_clean_session
	
	# Bind event receiver for inbound energenie messages
	print("Binding fsk_router.when_incoming to rx_energenie...")
	#energenie.fsk_router.when_incoming(rx_energenie)

	# Start thread for processing received inbound energenie, then sending to mqtt
	print("Starting rx_energenie_process thread...")
	thread_rxEnergenie = threading.Thread(target=rx_energenie_process, name="rx_energenie_process")
	thread_rxEnergenie.daemon = True
	thread_rxEnergenie.start()
	
	# Start thread for processing received inbound energenie, then sending to mqtt
	print("Starting energenie_tx_mqtt thread...")
	thread_energenieTxMqtt = threading.Thread(target=energenie_tx_mqtt, name="energenie_tx_mqtt")
	thread_energenieTxMqtt.daemon = True
	thread_energenieTxMqtt.start()

	# Start thread for receiving inbound mqtt messages, which will queue them for the other thread
	print("Starting rxFromMqtt thread...")
	thread_rxFromMqtt = threading.Thread(target=rx_mqtt, name="rx_mqtt")
	thread_rxFromMqtt.daemon = True
	thread_rxFromMqtt.start()

	print("These are devices in the registry...")
	names = energenie.registry.names()
	for name in names:
		print(name)
		device = energenie.registry.get(name)

	# Main processing loop for the energenie radio; loop command checks receive threads
	while not programkiller.kill_now:
		energenie.loop()
		try:
			msg = q_rx_mqtt.get(block=False)
		except Queue.Empty as e:
			# Empty queue means do nothing, just keep trying to receive
			pass
		else:
			mqtt_tx_energenie(msg=msg)

			q_rx_mqtt.task_done()

		time.sleep(ENERGENIE_SLEEP_WAIT)


if __name__ == "__main__":
	energenie.init()

	try:
		main()
	finally:
		energenie.finished()
