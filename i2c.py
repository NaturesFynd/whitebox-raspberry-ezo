#!/usr/bin/python

import io
import sys
import fcntl
import time
from datetime import datetime
from pathlib import Path
import copy
import string
import csv
import gcsfs

from AtlasI2C import (
	 AtlasI2C
)

def print_devices(device_list, device):
    for i in device_list:
        if(i == device):
            print("--> " + i.get_device_info())
        else:
            print(" - " + i.get_device_info())
    #print("")

def get_devices():
    device = AtlasI2C()
    device_address_list = device.list_i2c_devices()
    device_list = []

    for i in device_address_list:
        device.set_i2c_address(i)
        response = device.query("i")
        
        # check if the device is an EZO device
        checkEzo = response.split(",")
        if len(checkEzo) > 0:
            if checkEzo[0].endswith("?I"):
                # yes - this is an EZO device
                moduletype = checkEzo[1]
                response = device.query("name,?").split(",")[1]
                device_list.append(AtlasI2C(address = i, moduletype = moduletype, name = response))
    return device_list

def print_help_text():
    print('''
>> Atlas Scientific I2C sample code
>> Any commands entered are passed to the default target device via I2C except:
  - Help
      brings up this menu
  - List
      lists the available I2C circuits.
      the --> indicates the target device that will receive individual commands
  - xxx:[command]
      sends the command to the device at I2C address xxx
      and sets future communications to that address
      Ex: "102:status" will send the command status to address 102
  - all:[command]
      sends the command to all devices
  - Poll[,x.xx]
      command continuously polls all devices
      the optional argument [,x.xx] lets you set a polling time
      where x.xx is greater than the minimum %0.2f second timeout.
      by default it will poll every %0.2f seconds
  - Log[,x.xx,hh]
      continuously polls all devices at polling rate x.xx seconds
      logs values to csv file YYYY-MM-DD-HH:MM_octopi.csv
      terminates logging after hh hours, or defaults to 80 hrs
>> Pressing ctrl-c will stop the polling
    ''' % (AtlasI2C.LONG_TIMEOUT, AtlasI2C.LONG_TIMEOUT))

def main():

    device_list = get_devices()

    if len(device_list) == 0:
        print ("No EZO devices found")
        exit()

    device = device_list[0]

    print_help_text()

    print_devices(device_list, device)

    real_raw_input = vars(__builtins__).get('raw_input', input)

    while True:

        user_cmd = real_raw_input(">> Enter command: ")

        # show all the available devices
        if user_cmd.upper().strip().startswith("LIST"):
            print_devices(device_list, device)

        # print the help text
        elif user_cmd.upper().startswith("HELP"):
            print_help_text()

        # continuous polling command automatically polls the board
        elif user_cmd.upper().strip().startswith("POLL"):
            cmd_list = user_cmd.split(',')
            if len(cmd_list) > 1:
                delaytime = float(cmd_list[1])
            else:
                delaytime = device.long_timeout

            # check for polling time being too short, change it to the minimum timeout if too short
            if delaytime < device.long_timeout:
                print("Polling time is shorter than timeout, setting polling time to %0.2f" % device.long_timeout)
                delaytime = device.long_timeout
            try:
                while True:
                    print("-------press ctrl-c to stop the polling")
                    for dev in device_list:
                        dev.write("R")
                    time.sleep(delaytime)
                    for dev in device_list:
                        print(dev.read())

            except KeyboardInterrupt:       # catches the ctrl-c command, which breaks the loop above
                print("Continuous polling stopped")
                print_devices(device_list, device)

        # continuous polling command automatically polls the board
        elif user_cmd.upper().strip().startswith("LOG"):
            
            header = ['t_stamp', 't_rel (min)', 'ORP', 'pH', 'RTD']
            csv_file = "data/" + datetime.now().strftime("%Y-%m-%d-%H:%M:%S") + "_octopi.csv"
            Path(csv_file).touch(exist_ok=True)
            with open(csv_file, 'a', encoding='UTF8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(header)
            
            cmd_list = user_cmd.split(',')
            if len(cmd_list) > 1:
                delaytime = float(cmd_list[1])
            else:
                delaytime = device.long_timeout

            if len(cmd_list) > 2:
                maxtime = float(cmd_list[2])
            else:
                maxtime = 80

            # check for polling time being too short, change it to the minimum timeout if too short
            if delaytime < device.long_timeout:
                print("Polling time is shorter than timeout, setting polling time to %0.2f" % device.long_timeout)
                delaytime = device.long_timeout
            
            start_time = time.time()

            try:
                while True:
                    print("-------press ctrl-c to stop the run")
                    data = []
                    for dev in device_list:
                        dev.write("R")
                    time.sleep(delaytime)
                    data.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    t_rel = (time.time() - start_time) / 60
                    data.append(t_rel)
                    for dev in device_list:
                        reading = dev.read()
                        data.append(float(reading.split(": ")[-1].replace("\x00","")))
                        print(reading)
                    with open(csv_file, 'a', encoding='UTF8', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow(data)
                    if (t_rel / 60) > maxtime:
                        print("Uploading file...")
                        fs = gcsfs.GCSFileSystem(project='production-data-infra')
                        fs.put_file(csv_file, f"nf_data_lake_prod/iot/octopi/{csv_file}")
                        break

            except KeyboardInterrupt:       # catches the ctrl-c command, which breaks the loop above
                print("Uploading file...")
                fs = gcsfs.GCSFileSystem(project='production-data-infra')
                fs.put_file(csv_file, f"nf_data_lake_prod/iot/octopi/{csv_file}")
                print("Continuous polling stopped")
                print_devices(device_list, device)

        # send a command to all the available devices
        elif user_cmd.upper().strip().startswith("ALL:"):
            cmd_list = user_cmd.split(":")
            for dev in device_list:
                dev.write(cmd_list[1])

            # figure out how long to wait before reading the response
            timeout = device_list[0].get_command_timeout(cmd_list[1].strip())
            # if we dont have a timeout, dont try to read, since it means we issued a sleep command
            if(timeout):
                time.sleep(timeout)
                for dev in device_list:
                    print(dev.read())

        # if not a special keyword, see if we change the address, and communicate with that device
        else:
            try:
                cmd_list = user_cmd.split(":")
                if(len(cmd_list) > 1):
                    addr = cmd_list[0]

                    # go through the devices to figure out if its available
                    # and swith to it if it is
                    switched = False
                    for i in device_list:
                        if(i.address == int(addr)):
                            device = i
                            switched = True
                    if(switched):
                        print(device.query(cmd_list[1]))
                    else:
                        print("No device found at address " + addr)
                else:
                    # if no address change, just send the command to the device
                    print(device.query(user_cmd))
            except IOError:
                print("Query failed \n - Address may be invalid, use list command to see available addresses")


if __name__ == '__main__':
    main()
