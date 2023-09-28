from datetime import datetime
import logging
from sys import modules
from time import sleep
from pieces.monitor_utils import monitor_utils
from importlib import import_module


class dut_monitor():
    """ 
        The main DUT monitor class.
        It's purpose is to create and manage worker thread objects.
    """

    def __init__(self, monitor_map: list) -> None:
        
        # generate a start time for sync purposes and configure the logger
        self.start_time = datetime.now()
        self.logger_configurator()
        self.imported_modules = {}

        # check that the profiles are correctly passed to the monitor
        if not isinstance(monitor_map, list):
            self.dut_monitor_logger.critical(f"The profiles must be passed to dut_monitor in a list. dut_monitor process will exit",
                                              extra={'entity': "DUT-MONITOR : __init__()"})
            exit(1)
        
        # check that the environment requirements are met and perform the module imports
        #  based on the utility that the profile uses
        utils = monitor_utils()
        for utility in {profile['utility'] for profile in monitor_map}:
            self.dut_monitor_logger.info(f"Checking the environment for the required module {utility}",
                                          extra={'entity': "DUT-MONITOR : __init__()"})
            passed, message = utils.environment_check(utility = utility)
            if not passed:
                self.dut_monitor_logger.critical(f"Environment check failed with error: {message}",
                                              extra={'entity': "DUT-MONITOR : __init__()"})
                exit(1)
            self.imported_modules[utility] = import_module(f'pieces.{utility}')
            self.dut_monitor_logger.info(f"Import of the required module {utility} was successful",
                                          extra={'entity': "DUT-MONITOR : __init__()"})

        self.monitor_map = monitor_map 
        self.workers = {} # the dictionary of workers

    def profile_check(self, profile: dict) -> bool:
        """ 
        Method that checks that the mandatory parameters needed to start the monitor,
         are present in the profile passed by the user.
        """

        mandatory_params = ['dut', 'utility', 'items', 'interval', 'timeout']
        current_params = list(profile.keys())

        missing_items = list(set(mandatory_params) - set(current_params))
        
        if missing_items:
            self.dut_monitor_logger.critical(f"The mandatory monitor parameters {missing_items} are missing from the profile.",
                                              extra={'entity': "DUT-MONITOR : profile_check()"})
            return False
        return True

    def stop_workers(self, dut: str) -> None:
        '''
            Method that signals one or all worker threads to stop. The method waits for the signaled threads to terminate.
            :dut: the ip | cli of an worker, or 'all'
        '''

        if dut != 'all' and dut not in self.workers:
            self.dut_monitor_logger.error(f"There is no worker for '{dut}'", extra={'entity': "DUT-MONITOR : stop_workers()"})
            return False

        duts = list(self.workers.keys()) if dut == 'all' else [dut]

        for dut in duts:
            self.dut_monitor_logger.info(f"Now stopping {dut}'s worker", extra={'entity': "DUT-MONITOR : stop_workers()"})
            self.workers[dut].stop()
            self.dut_monitor_logger.info(f"Stop command sent to DUT {dut} {self.workers[dut].utility} worker", extra={'entity': "DUT-MONITOR : stop_workers()"})
        for dut in duts:
            if self.workers[dut].is_alive():
                self.workers[dut].stopped.wait()
            self.dut_monitor_logger.info(f"DUT {dut} {self.workers[dut].utility} worker terminated execution.", extra={'entity': "DUT-MONITOR : stop_workers()"})

    def init_worker(self, profile: dict) -> None:
        try:
            self.dut_monitor_logger.info(f"Trying to create {profile['utility']} type worker for DUT {profile['dut']}", extra={'entity': "DUT-MONITOR : init_worker()"})
            if profile['dut'] in self.workers:
                self.dut_monitor_logger.warning(f"A worker for DUT {profile['dut']} already exists. Skip the initialization process.", extra={'entity': "DUT-MONITOR : init_worker()"})
                return None
            self.workers[profile['dut']] = getattr(self.imported_modules[profile['utility']], profile['utility'])(profile)
            self.workers[profile['dut']].start()
            self.dut_monitor_logger.info(f"{profile['utility']} worker for DUT {profile['dut']} created and started", extra={'entity': "DUT-MONITOR : init_worker()"})
        except Exception as e:
            self.dut_monitor_logger.critical(f"Error: {e} occurred while trying to initialize {profile['utility']} worker for DUT {profile['dut']}", extra={'entity': "DUT-MONITOR : init_worker()"})
            
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
            
    def join_workers(self, dut: str, timeout:float = None) -> None:
        '''
            Wrapper method over Thread.join() that allows one or all worker threads to be join()ed to the calling thread.
            If used with stop_workers(), be advised that stop_workers() has its own mechanism to wait until the worker terminates. 
            :dut: the ip | cli of an worker, or 'all'
        '''
        if dut != 'all' and dut not in self.workers:
            self.dut_monitor_logger.error(f"There is no monitoring process for '{dut}'", extra={'entity': "DUT-MONITOR : join_workers()"})
            return False

        duts = list(self.workers.keys()) if dut == 'all' else [dut]

        for dut in duts:

            self.dut_monitor_logger.info(f"Now joining {self.workers[dut].utility} worker of DUT {dut}", extra={'entity': "DUT-MONITOR : join_workers()"})
            self.workers[dut].join(timeout=timeout)
            self.dut_monitor_logger.info(f"DUT {dut} {self.workers[dut].utility} worker finished its activity or the timeout expired.", 
                                         extra={'entity': "DUT-MONITOR : join_workers()"})
        return True
            
    def run(self) -> None:
        '''
        Method called to start the all the workers configured in monitor_map.
        Basically, this is the method that starts the monitor app.
        '''
        self.dut_monitor_logger.info(f"Operation started", extra={'entity': "DUT-MONITOR : run()"})
        try:
            for profile in self.monitor_map:
                if not self.profile_check(profile):
                    self.dut_monitor_logger.error(f"Profile {profile} failed the check, thus it is skipped.", extra={'entity': "DUT-MONITOR : run()"})
                    continue
                # pass the start time to all types of workers for synchronization purposes
                profile['start_time'] = self.start_time
                self.init_worker(profile=profile)
                sleep(1)
        except KeyboardInterrupt:
            self.dut_monitor_logger.critical(f"DUT Monitor closing due to KeyboardInterrupt.", extra={'entity': "DUT-MONITOR : run()"})
            self.stop_workers()
            exit(1)


e = dut_monitor(monitor_map=[{'dut':'15.1.1.10',
                              'utility':'snmp_monitor',
                              'items':['hm2LogTempMaximum.0','hm2PoeMgmtModuleDeliveredPower.1.1','hm2DiagCpuUtilization.0',
                                       'sysUpTime.0','hm2DiagMemoryRamFree.0','hm2LogTempMinimum.0'],
                              'interval':2,
                              'timeout':5,
                              #'statistics':['hm2LogTempMaximum.0','hm2PoeMgmtModuleDeliveredPower.1.1',
                              #              'hm2DiagCpuUtilization.0','hm2DiagMemoryRamFree.0','hm2LogTempMinimum.0'],
                              'check_values_change':['hm2LogTempMaximum.0','hm2PoeMgmtModuleDeliveredPower.1.1',
                                                     'hm2DiagCpuUtilization.0','hm2DiagMemoryRamFree.0','hm2LogTempMinimum.0',
                                                     'pethPsePortPowerClassifications.1.8',
                                                     'ifMauType.4.1']}])
                              #'detect_crashes':'sysUpTime.0'}])
                              
e = dut_monitor(monitor_map=[{'dut':'telnet localhost 20000',
                              'utility':'console_monitor',
                              'items':[('show system info','System Description'),('show system info','System uptime'),
                                       ('show system info','Operating hours'), ('show system info','Current temperature'),
                                       ('show system info','Current humidity'), ('show system resources','CPU utilization'),
                                       ('show system resources','Free RAM'), ('show system resources','Network CPU interface utilization average')],
                              'interval':2,
                              'timeout':30,
                              'statistics':['Current temperature','Current humidity','CPU utilization','Free RAM',
                                            'Network CPU interface utilization average'],
                              'check_values_change':['System Description','System uptime','Operating hours',
                                                     'Current temperature','Current humidity','CPU utilization',
                                                     'Free RAM','Network CPU interface utilization average'],
                              'detect_crashes':'System uptime'}])              
                
                              
e.run()
sleep(10)
e.join_workers(dut = 'all')


'''

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
