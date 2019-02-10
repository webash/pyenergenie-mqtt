# Based upon:
# - https://github.com/jeremypoulter/pyenergenie/blob/master/src/switch.py
# - https://github.com/whaleygeek/pyenergenie/blob/master/src/mihome_energy_monitor.py
import sys
import time
sys.path.insert(0, '/shared/pyenergenie-master/src')
import energenie
import paho.mqtt.client as mqtt
import Queue
import threading

mqtt_hostname = "localhost"
mqtt_port = 1883
mqtt_keepalive = 60
mqtt_username = ""
mqtt_password = ""
mqtt_client_id = "agn-sensor01-lon_energenie"
mqtt_clean_session = True
mqtt_publish_topic = "emon"
mqtt_subscribe_topic = "energenie"

txq = Queue.Queue()
rxq = Queue.Queue()

def mqtt_tx_energenie():
	global txq

	while True:
		try:
			msg = txq.get()
			print(msg.topic+" "+str(msg.payload))
			name = msg.topic.split("/", 2)[1]
			device = energenie.registry.get(name)
			if str(msg.payload) == "1":
				print(name+" on")
				for x in range(0, 5):
					device.turn_on()
					time.sleep(0.1)
			else:
				print(name+" off")
				for x in range(0, 5):
					device.turn_off()
					time.sleep(0.1)
		except:
			print("Got exception")
		finally:
			txq.task_done()
			
def rx_energenie():
	global rxq

	while True:
		energenie.loop()
		
		for d in energenie.registry.devices():
			print(d)
			print( str(dir(d)) )
			if d.get_product_id() == "PRODUCTID_MIHO006":
				try:
					p = d.get_power()
					print("Power MIHO005: %s" % str(p))
					item = {'DeviceName': "powerfeed", 'data': {"power": str(p)}}
					rxq.put(item)
				except:
					print("Exception getting power")
			elif d.get_product_id() == "PRODUCTID_MIHO005":
				try:
					p = d.get_power()
					print("Power MIHO005: %s" % str(p))
					item = {'DeviceName': "washingmachine", 'data': {"power": str(p)}}
					rxq.put(item)
				except:
					print("Exception getting power")


			
def energenie_tx_mqtt():
	global mqtt_hostname
	global mqtt_port
	global mqtt_keepalive
	global mqtt_username
	global mqtt_password
	global mqtt_client_id
	global mqtt_clean_session
	global mqtt_publish_topic
	global rxq

	print("energenie_tx_mqtt: creating mqtt.client...")
	toMqtt = mqtt.Client(client_id=mqtt_client_id, clean_session=mqtt_clean_session)

	if mqtt_username <> "":
		print("energenie_tx_mqtt: using username and password...")
		toMqtt.username_pw_set(mqtt_username, mqtt_password)
	print("energenie_tx_mqtt: connecting to mqtt broker...")
	toMqtt.connect(mqtt_hostname, mqtt_port, mqtt_keepalive)
	
	while True:
		print("energenie_tx_mqtt: awaiting item in rxq...")
		item = rxq.get()
		print("energenie_tx_mqtt: item for" + item['DeviceName'] + " found on queue...")
		print(str(item))
		data = item['data']
		for metric, value in data:
			publish_topic = mqtt_publish_topic + "/" + item['DeviceName'] + "/" + metric
			print("energenie_tx_mqtt: publishing " + str(value) + " to topic " + publish_topic)
			toMqtt.publish(publish_topic, value)
		rxq.task_done()

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
	global mqtt_subscribe_topic
	print("Connected with result code "+str(rc))

	# Subscribing in on_connect() means that if we lose the connection and
	# reconnect then subscriptions will be renewed.
	print("Subscribing to "+mqtt_subscribe_topic+"/#")
	client.subscribe(mqtt_subscribe_topic + "/#")

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
	txq.put(msg)

def main():
	global mqtt_hostname
	global mqtt_port
	global mqtt_keepalive
	global mqtt_username
	global mqtt_password
	global mqtt_client_id
	global mqtt_clean_session

	# Start a thread to process the key presses
	#thread_txToEnergenie = threading.Thread(target=mqtt_tx_energenie)
	#thread_txToEnergenie.daemon = True
	#thread_txToEnergenie.start()
	
	# Start thread for receiving inbound energenie messages
	print("Starting rxFromEnergenie thread...")
	thread_rxFromEnergenie = threading.Thread(target=rx_energenie)
	thread_rxFromEnergenie.daemon = True
	thread_rxFromEnergenie.start()
	
	print("Starting rxProcessor thread...")
	# Start thread for processing received inbound energenie, then sending to mqtt
	thread_rxProcessor = threading.Thread(target=energenie_tx_mqtt)
	thread_rxProcessor.daemon = True
	thread_rxProcessor.start()
	
	print("Starting main while loop...")
	while True:
		try:
			client = mqtt.Client(client_id=mqtt_client_id, clean_session=mqtt_clean_session)
			client.on_connect = on_connect
			client.on_message = on_message

			if mqtt_username != "":
				client.username_pw_set(mqtt_username, mqtt_password)
			client.connect(mqtt_hostname, mqtt_port, mqtt_keepalive)

			# Blocking call that processes network traffic, dispatches callbacks and
			# handles reconnecting.
			# Other loop*() functions are available that give a threaded interface and a
			# manual interface.
			client.loop_forever()
		finally:
			print("Restarting...")

if __name__ == "__main__":
	energenie.init()

	try:
		main()
	finally:
		energenie.finished()