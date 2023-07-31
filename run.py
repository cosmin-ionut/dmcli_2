from datetime import datetime
import logging
from sys import modules
from time import sleep
from pieces.monitor_utils import environment_check
from importlib import import_module
from collections import defaultdict
from pieces.snmp_monitor import snmp_monitor


class dut_monitor():
    """ the main monitoring process.
        creates and manages worker objects.
    """

    def __init__(self, monitor_map: tuple):
        
        # the type of monitoring
        #self.worker_type = function # the type of the worker 
        '''
        passed, message = environment_check(function = self.worker_type)
        if not passed:
            print(f'Environment check failed with error: {message}')
            exit(1)
        self.function = import_module(f'pieces.{self.worker_type}')
        '''
        # define what will be monitored
        #self.dut_list = dut_list # the list of devices under monitoring
        #self.item_list = item_list # the list of items (oids/mibs/cli commands) from which information will be retrieved (monitored).
        # when dut_list and item_list are used, each item from the item_list will be monitored for each DUT in dut_list.
        self.monitor_map = monitor_map # dictionary. a user-defined mapping between DUTs and items to be monitored
                                       # allows separate items to be monitored for each individual DUT, as desired
                                       # if monitor_map is anything else than an empty dictionary, dut_list and item_list have no effect.
                                       # format: {'dut_ip':['item_1', 'item_2', 'item_3'], 'dut2_ip':['item_1', 'item_4', 'item_5']}
        # manage the monitoring process
        self.workers = {} # the dictionary of workers
                          # each instance of dut_monitor will create one TYPE of workers only.
                          # one worker will be created for each DUT. For instance, a dut_monitor object which monitors 3 DUTs via snmp, will create and manage 3 snmp workers, one for each DUT
                          # format: {'dut_1_ip' : worker1, 'dut_2_ip':worker2, 'dut_3_ip':worker3}
        # use a separate crash_item for each dut
        #self.detect_crashes = defaultdict(lambda: False)
        #for dut, uptime_item in detect_crashes.items(): self.detect_crashes[dut] = uptime_item
        # kwargs is a dictionary of arguments which will be passed, or not, to the worker classes based on their implementation.
        #self.kwargs = kwargs # a set of arguments which may or may not be passed to dut monitor. Used to provide worker-specific arguments.
    '''
    def dut_to_item_mapper(self):
        """ self.monitor_map is used to create workers.
            this function takes the dut_list and item_list lists and parses them into self.monitor_map dictionary
        """
        # if self.map is already passed by the user, just skip the execution.
        if not self.monitor_map:
            if not isinstance(self.dut_list, list):
                self.dut_monitor_logger.critical(f"'dut_list' must be a list", extra={'entity': "DUT-MONITOR : dut_to_item_mapper()"})
                raise TypeError()
            if not isinstance(self.item_list, list):
                self.dut_monitor_logger.critical(f"'item_list' must be a list", extra={'entity': "DUT-MONITOR : dut_to_item_mapper()"})
                raise TypeError()
            for dut in self.dut_list:
                self.monitor_map[dut] = self.item_list
        self.dut_monitor_logger.info(f"Mapper operation successful", extra={'entity': "DUT-MONITOR : dut_to_item_mapper()"})
    '''
    def stop_workers(self):
        '''
        stop all workers.
        '''
        for dut in self.workers:
            self.dut_monitor_logger.info(f"Now stopping {dut}'s worker", extra={'entity': "DUT-MONITOR : stop_workers()"})
            self.workers[dut].stop()
            self.dut_monitor_logger.info(f"Stop command sent to DUT {dut} {self.worker_type.upper()} worker", extra={'entity': "DUT-MONITOR : stop_workers()"})
        for dut in self.workers:
            if self.workers[dut].is_alive():
                self.workers[dut].stopped.wait()
            self.dut_monitor_logger.info(f"DUT {dut} {self.worker_type.upper()} worker finished execution.", extra={'entity': "DUT-MONITOR : stop_workers()"})

    def init_worker(self, profile: dict) -> None:
        try:
            self.dut_monitor_logger.info(f"Trying to create {profile['function']} type worker for DUT {profile['dut']}", extra={'entity': "DUT-MONITOR : init_worker()"})
            if profile['dut'] in self.workers:
                self.dut_monitor_logger.warning(f"A worker for DUT {profile['dut']} already exists. Skip the initialization process.", extra={'entity': "DUT-MONITOR : init_worker()"})
                return None
            self.workers[profile['dut']] = getattr(modules[__name__], profile['function'])(profile)
            self.workers[profile['dut']].start()
            self.dut_monitor_logger.info(f"{profile['function']} worker for DUT {profile['dut']} created and started", extra={'entity': "DUT-MONITOR : init_worker()"})
        except Exception as e:
            self.dut_monitor_logger.critical(f"Error: {e} occurred while trying to initialize {profile['function']} worker for DUT {profile['dut']}", extra={'entity': "DUT-MONITOR : init_worker()"})
            
    def logger_configurator(self) -> None:
        try:
            # initialize the logger object
            self.dut_monitor_logger = logging.getLogger('dut_monitor')
            self.dut_monitor_logger.setLevel(logging.DEBUG)
            # initialize the file handler object
            logfile_handler = logging.FileHandler(f"logfile_dut_monitor_{self.start_time.strftime('%d_%b_%Y_%H_%M_%S')}.log")
            # define a log message format
            formatter = logging.Formatter('[ %(asctime)s ::: %(levelname)s ::: %(entity)s ] - %(message)s ')
            # add the formatter to the file handler
            logfile_handler.setFormatter(formatter)
            # add the file handler to dut monitor's logger
            self.dut_monitor_logger.addHandler(logfile_handler)
            self.dut_monitor_logger.info('Logger object initialized successfully', extra={'entity': "DUT-MONITOR : logger_configurator()"})
        except Exception as e:
            print(f"[ {datetime.now().strftime('%d/%b/%Y %H:%M:%S')} ::: CRITICAL ::: DUT-MONITOR : logger_configurator() ] {e} OCCURRED DURING LOGGER OBJECT INITIALIZATION. CANNOT CONTINUE SCRIPT EXECUTION")
            exit(1)
            
    def join_workers(self) -> None:
        '''method used to make sure that a script will finish when all the workers finish due to time limit/error count.
        '''
        for dut in self.workers:
            self.dut_monitor_logger.info(f"Now joining {self.worker_type.upper()} worker of DUT {dut}", extra={'entity': "DUT-MONITOR : join_workers()"})
            self.workers[dut].join()
            self.dut_monitor_logger.info(f"DUT {dut} {self.worker_type.upper()} worker finished its activity.", extra={'entity': "DUT-MONITOR : join_workers()"})
            
    def run(self) -> None:
        '''
        Method called to start the all the workers configured in monitor_map.
        Basically, this is the method that starts the monitor app.
        '''
        self.start_time = datetime.now()
        self.logger_configurator()
        self.dut_monitor_logger.info(f"Operation started", extra={'entity': "DUT-MONITOR : run()"})
        try:
            for profile in self.monitor_map:
                # pass the start time to all types of workers for synchronization purposes
                profile['start_time'] = self.start_time
                self.init_worker(profile=profile)
                sleep(1)
        except KeyboardInterrupt:
            self.dut_monitor_logger.critical(f"DUT Monitor script closing with error.", extra={'entity': "DUT-MONITOR : run()"})
            self.stop_workers()
            exit(1)

e = dut_monitor(monitor_map=({'dut':'192.168.1.1', 
                              'function':'snmp_monitor',
                              'items':['sysUpTime.0','hm2SfpInfoPartId.1'],
                              'interval':5,
                              'timeout':10000,
                              'statistics':True,
                              'detect_crashes':'sysUpTime.0'},
                              {'dut':'10.14.211.2', 
                              'function':'snmp_monitor',
                              'items':['sysUpTime.0','hm2SfpInfoPartId.1','.1.3.6.1.4.1.248.11.22.1.8.10.1.0'],
                              'interval':145,
                              'timeout':80,
                              'statistics':False,
                              'detect_crashes':'hm2SfpInfoPartId.1'}))
#e.run()

'''   
e = dut_monitor(monitor_map = {'telnet 10.2.36.236 5042':[('show sysinfo','Backplane Hardware Description'),('show sysinfo','System Up Time'),('show sysinfo','CPU Utilization'), ('show temperature','Lower Temperature Limit for Trap')],
                               'telnet localhost 30001':[('show system info','System uptime')],
                               'telnet 10.2.36.236 5037':[('show system info','Serial number'),('show system info','Power Supply P1, state'),('show system info','System uptime'), ('show sfp 1/1','RxPwr high alarm threshold   [mW]')]
                               },
                function='console_monitor', #the function I want to use
                interval=5, # waiting interval. Depending on how much time it takes to query all items, the actual interval between two iterations may be higher.
                seconds = 90000, # time limit for the script
                #dut_list=['15.1.1.50'], # devices monitored
                #item_list=['.1.3.6.1.4.1.248.11.22.1.8.11.2.0','.1.3.6.1.4.1.248.11.22.1.8.10.1.0','.1.3.6.1.2.1.1.3.0', 'sysUpTime.0','hm2SfpInfoPartId.1'], # items monitored
                statistics = True, # calculate min max and avg for each item monitored
                detect_crashes=['System Up Time', 'System uptime']) # try to detect DUT crashes. the item passed MUST be a DUT uptime item for this to work.
e.run()
x = input('Press any key to stop') # the script stays blocked here until the user presses a key
e.stop_workers() # I stop all workers ahead of time.

the format of dut_monitor must be:
dut_monitor(monitor_map = {dut:dut1, function:, profile:{'items':[],
                                'function':'function',
                                'interval':'interval',
                                'timeout':'timeout',
                                kwargs:{detect_crashes:{},statistics:bool}
                                },
                           dut2:{'items':[],
                                'function':'function',
                                'interval':'interval',
                                'timeout':'timeout',
                                kwargs:{detect_crashes:{},statistics:bool}
                                }})
            

e = dut_monitor(monitor_map = {'10.10.255.98':['sysUpTime.0','hm2DiagCpuAverageUtilization.0','hm2DiagMemoryRamFree.0'],
                               '10.10.255.37':['sysUpTime.0','hm2DiagCpuAverageUtilization.0','hm2DiagMemoryRamFree.0'],
                               '10.10.255.124':['sysUpTime.0','hm2DiagCpuAverageUtilization.0','hm2DiagMemoryRamFree.0'],
                               '10.10.255.100':['sysUpTime.0','hm2DiagCpuAverageUtilization.0','hm2DiagMemoryRamFree.0'],
                               '10.10.255.36':['sysUpTime.0','hm2DiagCpuAverageUtilization.0','hm2DiagMemoryRamFree.0'],
                               '10.10.255.35':['sysUpTime.0','hm2DiagCpuAverageUtilization.0','hm2DiagMemoryRamFree.0'],
                               '10.10.255.12':['sysUpTime.0','hm2DiagCpuAverageUtilization.0','hm2DiagMemoryRamFree.0'],
                               '10.10.255.39':['sysUpTime.0','hm2DiagCpuAverageUtilization.0','hm2DiagMemoryRamFree.0'],
                               '10.10.255.40':['sysUpTime.0','hm2DiagCpuAverageUtilization.0','hm2DiagMemoryRamFree.0'],
                               '10.10.255.42':['hmMemoryFree.0','hmCpuAverageUtilization.0','.1.3.6.1.2.1.1.3.0'],
                               '10.10.255.41':['hmMemoryFree.0','hmCpuAverageUtilization.0','.1.3.6.1.2.1.1.3.0'],
                               '10.10.255.43':['hmMemoryFree.0','hmCpuAverageUtilization.0','.1.3.6.1.2.1.1.3.0'],
                               '10.10.255.44':['hmMemoryFree.0','hmCpuAverageUtilization.0','.1.3.6.1.2.1.1.3.0']
                               },
                function='snmp_monitor', #the function I want to use
                interval=2, # waiting interval. Depending on how much time it takes to query all items, the actual interval between two iterations may be higher.
                seconds = 90000, # time limit for the script
                #dut_list=['15.1.1.50'], # devices monitored
                #item_list=['.1.3.6.1.4.1.248.11.22.1.8.11.2.0','.1.3.6.1.4.1.248.11.22.1.8.10.1.0','.1.3.6.1.2.1.1.3.0', 'sysUpTime.0','hm2SfpInfoPartId.1'], # items monitored
                statistics = True, # calculate min max and avg for each item monitored
                detect_crashes = {'10.10.255.98':'sysUpTime.0',
                                  '10.10.255.42':'.1.3.6.1.2.1.1.3.0' }) # try to detect DUT crashes. the item passed MUST be a DUT uptime item for this to work.
e.run()
x = input('Press any key to stop') # the script stays blocked here until the user presses a key
e.stop_workers() # I stop all workers ahead of time.
'''

'''
e = dut_monitor(function='console_monitor', #the function I want to use
                interval=5, # waiting interval. Depending on how much time it takes to query all items, the actual interval between two iterations may be higher.
                seconds = 10000, # time limit for the script
                dut_list=['telnet 10.10.0.252 10002'], # devices monitored
                item_list=[('show system info','System uptime'),('show system resources','CPU utilization'), ('show system resources','Resources measurement'), ('show system temperature limits',"Current temperature"), ('show interface ether-stats 6/1',"Packets RX  256-511 octets")], # items monitored
                #item_list=[('show system temperature limits',"Current temperature")], # items monitored
                statistics = True,
                detect_crashes = 'System uptime'
                ) # try to detect DUT crashes. the item passed MUST be a DUT uptime item for this to work.


USAGE:
_____________
             |
A. Functions |
_____________|

1. snmp_monitor ##########################################################################################################################################
one such snmp_monitor worker snmpqueries one single device for a set of oids/mibs, at specific time intervals

Example:

e = dut_monitor(monitor_map = {'10.10.255.98':['sysUpTime.0','hm2DiagCpuAverageUtilization.0','hm2DiagMemoryRamFree.0'], # monitor_map allows different items to be monitored for each DUT
                               '10.10.255.42':['hmMemoryFree.0','hmCpuAverageUtilization.0','.1.3.6.1.2.1.1.3.0']},      # If monitor_map is used, dut_list and item_list have no effect
                function='snmp_monitor', #the function I want to use for monitoring
                interval=2, # waiting interval between iterations. Doesn't take into account the iteration execution delay
                seconds = 90000, # time limit for the script
                #dut_list=['15.1.1.50'], # devices monitored
                #item_list=['.1.3.6.1.4.1.248.11.22.1.8.11.2.0','.1.3.6.1.4.1.248.11.22.1.8.10.1.0','.1.3.6.1.2.1.1.3.0', 'sysUpTime.0','hm2SfpInfoPartId.1'], # items monitored
                statistics = True, # calculate min max and avg for each item monitored
                detect_crashes=['.1.3.6.1.2.1.1.3.0', 'sysUpTime.0']) # try to detect DUT crashes. The items passed must be monitored (monitor_map or item_list)
                
                
Limitations:
- Uses snmpGET so OIDs and MIBS passed must include the IID: hm2DiagMemoryRamFree.0 / .1.3.6.1.4.1.248.11.22.1.8.11.2.0
  If not, MIB/OID query fails.
  
2. console_monitor ######################################################################################################################################
e = dut_monitor(function='console_monitor', #the function I want to use
                interval=3, # waiting interval. Depending on how much time it takes to query all items, the actual interval between two iterations may be higher.
                seconds = 30, # time limit for the script
                dut_list=['telnet localhost 30000','telnet 10.10.0.252 10002'], # ser2net telnet connections of the devices monitored
                item_list=[('show system resources','CPU utilization'), ('show system resources',"Average allocated RAM")], # items monitored. List of tuples ('cli_command_that_shows_the_value', 'value')
                )
                

e = dut_monitor(function='console_monitor', #the function I want to use
                interval=2, # waiting interval between iterations. Doesn't take into account the iteration execution delay
                seconds = 10000, # time limit for the script
                dut_list=['telnet localhost 30003','telnet localhost 30000'], # devices monitored. Each device must be identified by a ser2net conenection
                item_list=[('show system temperature limits','Temperature upper limit'),('show system resources','Allocated RAM'),('show system temperature limits','Current temperature'), 
                           ('show sfp 1/1','Temperature low warning threshold  [C/F]')],# items monitored. List of tuples ('cli_command_that_shows_the_value', 'value')
                statistics = True, # calculate min max and avg for each item monitored
                detect_crashes = ['System uptime'] # try to detect DUT crashes. The items passed must be monitored (monitor_map or item_list)
                )
                
Limitations:
- for now, it can only retrieve values from 'dotted' tables such as:
!*(DRAGON)#show storm-control flow-control
Flow control................................disable
!*(DRAGON)#
so, the item monitored bust be separated by dots from its value.
- the devices in dut_list MUST be ser2net connections. Does not work with SSH, regular telnet connections or using screen on the /dev file.
______________________
                      |
B. Possible use cases |
______________________|

1. STANDALONE: only the monitor is executing and nothing else. #############################################################################################
seconds = 1000 # I want to run the monitor script for a fixed 1000 seconds
m1 = dut_monitor(function='snmp_monitor', interval=3, seconds = seconds, 
                 arg1 = 1, arg2 = 2, arg3 = 3, dut_list=['15.1.1.40' ], 
                 item_list=['.1.3.6.1.4.1.248.11.22.1.8.11.2.0','.1.3.6.1.4.1.248.11.22.1.8.10.1.0','.1.3.6.1.2.1.1.3.0'])
m1.run()
e.join_workers() # each worker will be join()ed to the main thread, so as long as there is at least one alive worker, the script will keep going.
                 # the monitor will end when all workers end (by time limit or error_count reached).

2. DEPENDANT: I use the monitor and also run some other script in the meantime. I want the monitor to stop after my other script ends.######################
seconds = 10000 # to make sure the monitor's end limit won't be reached
m2 = dut_monitor(function='snmp_monitor', interval=3, seconds = seconds, 
                 arg1 = 1, arg2 = 2, arg3 = 3, dut_list=['15.1.1.40' ], 
                 item_list=['.1.3.6.1.4.1.248.11.22.1.8.11.2.0','.1.3.6.1.4.1.248.11.22.1.8.10.1.0','.1.3.6.1.2.1.1.3.0'])
m2.run()
#
# here I run my other script that does whatever
#
#
m2.stop_workers() # I stop all workers ahead of time.

3. STANDALONE INDEFINITELY: I use the monitor but I don't know for how long. Monitor should stop at my input. #############################################
seconds = 100000 # to make sure the monitor's end limit won't be reached too soon
m3 = dut_monitor(function='snmp_monitor', interval=3, seconds = seconds, 
                 arg1 = 1, arg2 = 2, arg3 = 3, dut_list=['15.1.1.40' ], 
                 item_list=['.1.3.6.1.4.1.248.11.22.1.8.11.2.0','.1.3.6.1.4.1.248.11.22.1.8.10.1.0','.1.3.6.1.2.1.1.3.0'])
m3.run()
e = input('Press any key to stop') # the script stays blocked here until the user presses a key
m3.stop_workers() # I stop all workers ahead of time.
'''
