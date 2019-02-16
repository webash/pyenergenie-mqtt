# pyenergenie-mqtt
Mashing together pyenergenie and mqtt

Requirements:
 - [whaleygeek/pyenergenie](https://github.com/whaleygeek/pyenergenie/)
 - MQTT broker

Installation:
 1. Either download the whole repo as a zip file and extract to where you want it OR use `git clone https://github.com/webash/pyenergenie-mqtt`
 2. Use the `setup_tool.py` in `pyenergenie` to update/produce your registry.kvs, and put it in the working diretory that you'll be running pyenergenie-mqtt from. If you're going to use the default, it will be /shared/pyenergenie-mqtt/
 3. Check the configuration at the top of the python is as you like it
 4. Run the python interactively first, to make sure it works - you should see things landing in MQTT/emonCMS if all is going well
 5. Follow the systemd installation instructions in the top of the .service file
 6. Boom! Energenie/MQTT middleware!
 
 Not yet implemented properly:
  - Receiving messages from MQTT to push back to the energenie devices
