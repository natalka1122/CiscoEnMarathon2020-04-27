#!/usr/bin/env python3
# """Module docstring."""

#Imports
from netmiko import ConnectHandler
import csv
import logging
import datetime
import multiprocessing as mp
import difflib
import filecmp
import sys
import os
import textfsm
import socket

#Module 'Global' variables
DEVICE_FILE_PATH = 'devices.txt' # file should contain a list of devices in format: ip,username,password,device_type
BACKUP_DIR_PATH = 'backups' # path to backup directory
TEXTFSM_TEMPLATES_DIR="textfsm"
SHOW_CDP_NEI = open(os.path.join(TEXTFSM_TEMPLATES_DIR,"cisco_ios_show_cdp_neighbors.textfsm"), "r")
SHOW_VERS = open(os.path.join(TEXTFSM_TEMPLATES_DIR,"cisco_ios_show_version.textfsm"), "r")
NTP_SERVERS=["37.193.156.169","78.36.18.184","89.221.207.113","192.36.143.130"]

def enable_logging():
    # This function enables netmiko logging for reference

    logging.basicConfig(filename='test.log', level=logging.DEBUG)
    logger = logging.getLogger("netmiko")

def check_ntp_server(host):
        port = 123
        buf = 1024
        address = (host,port)
        msg = bytes('\x1b' + 47 * '\0',encoding = 'utf-8')
 
        try:
        # connect to server
            client = socket.socket( socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(1)
            client.sendto(msg, address)
            msg, address = client.recvfrom( buf )
        except Exception:
            print('Error:',host,'is not a corrent NTP server')
            return False
 
        return True

def get_devices_from_file(device_file):
    # This function takes a CSV file with inventory and creates a python list of dictionaries out of it
    # Each disctionary contains information about a single device

    # creating empty structures
    device_list = list()
    device = dict()

    # reading a CSV file with ',' as a delimeter
    with open(device_file, 'r') as f:
        reader = csv.DictReader(f, delimiter=';')

        # every device represented by single row which is a dictionary object with keys equal to column names.
        for row in reader:
            device_list.append(row)
    
    print ("Got the device list from inventory")
    print('-*-' * 10)
    print ()

    # returning a list of dictionaries
    return device_list

def get_current_date_and_time():
    # This function returns the current date and time
    now = datetime.datetime.now()

    print("Got a timestamp")
    print('-*-' * 10)
    print()

    # Returning a formatted date string
    # Format: yyyy_mm_dd-hh_mm_ss
    return now.strftime("%Y_%m_%d-%H_%M_%S")

def connect_to_device(device):
    # This function opens a connection to the device using Netmiko
    # Requires a device dictionary as an input

    connection = ConnectHandler(
        host = device['ip'],
        username = device['username'],
        password=device['password'],
        device_type=device['device_type'],
        secret=device['secret']
    )

    print ('Opened connection to '+device['ip'])
    print('-*-' * 10)
    print()

    # returns a "connection" object
    return connection

def disconnect_from_device(connection, hostname):
    #This function terminates the connection to the device

    connection.disconnect()
    print ('Connection to device {} terminated'.format(hostname))

def get_backup_file_path(hostname,timestamp):
    # This function creates a backup file name (a string)
    # backup file path structure is hostname/hostname-yyyy_mm_dd-hh_mm

    # checking if backup directory exists for the device, creating it if not present
    if not os.path.exists(os.path.join(BACKUP_DIR_PATH, hostname)):
        os.mkdir(os.path.join(BACKUP_DIR_PATH, hostname))

    # Merging a string to form a full backup file name
    backup_file_path = os.path.join(BACKUP_DIR_PATH, hostname, '{}-{}.txt'.format(hostname, timestamp))
    print('Backup file path will be '+backup_file_path)
    print('-*-' * 10)
    print()

    # returning backup file path
    return backup_file_path

def create_backup(connection, backup_file_path, hostname):
    # This function pulls running configuration from a device and writes it to the backup file
    # Requires connection object, backup file path and a device hostname as an input

    try:
        # sending a CLI command using Netmiko and printing an output
        connection.enable()
        output = connection.send_command('sh run')

        # creating a backup file and writing command output to it
        with open(backup_file_path, 'w') as file:
            file.write(output)
        print("Backup of " + hostname + " is complete!")
        print('-*-' * 10)
        print()

        # if successfully done
        return True

    except Error:
        # if there was an error
        print('Error! Unable to backup device ' + hostname)
        return False




def process_target(device,timestamp,config_commands):
    connection = connect_to_device(device)

    device_hostname=connection.find_prompt()[:-1]

    backup_file_path = get_backup_file_path(device_hostname, timestamp)
    backup_result = create_backup(connection, backup_file_path, device_hostname)

    sh_cdn_nei=connection.send_command('show cdp neighbors')
    if "CDP is not enabled" in sh_cdn_nei:
        cdp_enabled='CDP is OFF'
    else:
        cdp_enabled='CDP is ON'
    re_table = textfsm.TextFSM(SHOW_CDP_NEI)
    num_cdp_neighbors = len(re_table.ParseText(sh_cdn_nei))

    sh_vers = connection.send_command('show version')
    pe_or_npe='NPE' if 'NPE' in sh_vers else 'PE'
    re_table = textfsm.TextFSM(SHOW_VERS)
    version = re_table.ParseText(sh_vers)[0]
    
    connection.send_config_set(config_commands)

    sh_ntp_sta=connection.send_command('show ntp status')
    ntp_status='Clock not in Sync' if 'sh_ntp_sta' in sh_ntp_sta else 'Clock in Sync'

    print(device_hostname+"|"+",".join(version[6])+"|"+version[0]+"|"+pe_or_npe+"|"+cdp_enabled+","+str(num_cdp_neighbors)+" peers|"+ntp_status)
    disconnect_from_device(connection, device_hostname)

def main(*args):
    # This is a main function

    global DEVICE_FILE_PATH
    global BACKUP_DIR_PATH
    # Parse arguments
    if len(args)>2:
        print('Usage: device_check.py [device_file [backup_dir]]')
        sys.exit(1)
    elif len(args)==1:
        DEVICE_FILE_PATH=args[0]
    elif len(args)==2:
        DEVICE_FILE_PATH=args[0]
        BACKUP_DIR_PATH=args[1]

    # Enable logs
    enable_logging()

    # Create backup directory
    os.makedirs(BACKUP_DIR_PATH, exist_ok=True)

    # Create NTP list (common for all devices)
    config_commands=["clock timezone GMT 0 0"]
    for ntp_server in NTP_SERVERS:
        if check_ntp_server(ntp_server):
            config_commands.append("ntp server "+ntp_server)


    # getting the timestamp string
    timestamp = get_current_date_and_time()

    # getting a device list from the file in a python format
    device_list = get_devices_from_file(DEVICE_FILE_PATH)

    # creating a empty list
    processes=list()

    # Running workers to manage connections
    with mp.Pool(4) as pool:
        # Starting several processes...
        for device in device_list:
            processes.append(pool.apply_async(process_target, args=(device,timestamp,config_commands)))
        # Waiting for results...
        for process in processes:
            process.get()


if __name__ == '__main__':
    # checking if we run independently
    i, *script_args = sys.argv

    # the execution starts here
    main(*script_args)
