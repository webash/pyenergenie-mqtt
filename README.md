# pyenergenie-mqtt
Mashing together pyenergenie and mqtt.

I really like the [OpenEnergyMonitor](https://openenergymonitor.org)'s [emonCMS](https://github.com/emoncms/emoncms) project for ingesting and display energy (gas/eletricity) information. BUT their open hardware was overkill for my residential setup which only has one feed [and no solar]. I also liked Energenie's hardware, but their mihome4u.co.uk site/software was lacking in features and extensibility. So, with this project I was able to merge the hardware of Energenie mi|home with OpenEnergyMonitor's emonCMS. It takes the pyenergenie Python module and mashes it up with MQTT, where the emonCMS mqtt_input service picks up the input data to use in the feeds. I can also then use Node Red to further mash-up the MQTT data feeds.

Requirements:
 - ~[whaleygeek/pyenergenie](https://github.com/whaleygeek/pyenergenie/)~ Now included in this project as a submodule.
 - MQTT broker

Installation:
 1. Use `git clone https://github.com/webash/pyenergenie-mqtt` to copy the repo onto your machine. I use somewhere like `/shared/` to do so.
 2. Change into the directory of the `pyenergenie-mqtt` repo, and run `git submodule init` then `git submodule update`
 3. Use the `setup_tool.py` in `pyenergenie\src` to update/produce your registry.kvs, and put it in the working diretory that you'll be running pyenergenie-mqtt from. If you're going to use the default, it will be `/shared/pyenergenie-mqtt/`
 4. Check the configuration at the top of the python is as you like it (this will be moved to a configuration file at some point)
 5. Run the python interactively first, to make sure it works - you should see things landing in MQTT/emonCMS if all is going well
 6. Follow the systemd installation instructions in the top of the .service file
 7. Boom! Energenie/MQTT middleware!
 
 Not yet implemented properly:
  - Receiving messages from MQTT to push back to the energenie devices
