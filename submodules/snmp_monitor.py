from datetime import datetime, timedelta
from threading import Thread, Event
import logging
from monitor_utils import monitor_utils
from re import compile
from netsnmp import *
from json import load as json_load, decoder
from os.path import dirname, realpath


class snmp_monitor(Thread):
    '''
        Each thread (called snmp worker/oid_inspector worker) inspects a set of OIDs for a single IP. 
    '''

    def __init__(self, profile: dict) -> None:

        Thread.__init__(self)

        self.profile = profile

        # set the endtime of the whole monitoring process 
        self.endtime = profile['start_time'] + timedelta(seconds=profile['timeout']) if profile['timeout'] else None 
        # path settings
        mainDir = f"{dirname(realpath(__file__))}/.."
        # logfile configuration
        self.logfile_path = f"{mainDir}/logfiles/logfile_{profile['dut']}_{profile['start_time'].strftime('%d_%b_%Y_%H_%M_%S')}.log"
        self.logger = logging.getLogger(profile['dut'])
        self.logger.setLevel(logging.DEBUG)
        logfile_handler = logging.FileHandler(self.logfile_path)
        fmt = logging.Formatter('%(asctime)s | %(message)s')
        logfile_handler.setFormatter(fmt)
        self.logger.addHandler(logfile_handler)
        # import snmp settings
        try:
            with open(f"{mainDir}/config/snmp_monitor.json", 'r') as file:
                json_data = json_load(file)
        except decoder.JSONDecodeError as e:
            self.logger.info(f"CRITICAL : SNMP-MONITOR : __init__() - Failed to parse snmp_monitor.json: {e}.\n")
            self.stop()
        # other settings
        self.item_list = list(set(profile['items'])) # can contain either OIDs or MIBs. The conversion is done to remove duplicate items
        self.iteration_number = 1 # the index of the iteration
        self.utility = profile['utility']
        # stop mechanism
        self.thread_sleep = Event()
        self.stopped = Event()   # | these two work the thread stop mechanism
        self.stop_thread = False # |
        self.daemon = True
        # end thread processing
        self.statistics = {item: compile("\s\s[0-9]+\s") for item in profile['statistics']} if 'statistics' in profile else {}
        self.detect_crashes = {profile['detect_crashes']: compile("\s\s[0-9]+\s")} if 'detect_crashes' in profile else {}
        self.check_values_change = {item: compile("\s\s.+\s") for item in profile['check_values_change']} if 'check_values_change' in profile else {}
        # configure the snmp session
        snmp_settings = json_data[profile['snmp_settings']] if 'snmp_settings' in profile else json_data['default_settings']
        self.snmp_session = Session(DestHost=self.profile['dut'], **snmp_settings)

    def snmp_querier(self):
        '''
        This method snmp queries the DUT, and updates self.results with the retrieved data.
        '''
        self.logger.info(50*'#' + f" Iteration number #{self.iteration_number} started " + 50*'#')
        for item in self.item_list:
            try:
                result = str(self.snmp_session.get(VarList(item))[0], 'UTF-8')
                self.logger.info(f'ITEM: {item} query result:  {result.rstrip()}')
            except Exception as e:
                self.logger.info(f'ITEM: {item} query result: ERROR: {str(e).rstrip()}')
        self.logger.info(129*'#' + 3*'\n')

    def run(self):
        self.logger.info(f"INFO : SNMP-MONITOR : run() - Thread operation started.\n\n\n")
        if not self.endtime:
            self.logger.info(f"WARNING : SNMP-MONITOR : run() - A time limit for the monitoring process was not set.\n")
        while True:
            if self.endtime:
                if not self.endtime > datetime.now():
                    self.logger.info(f"INFO : SNMP-MONITOR : run() - Thread finished execution. Time limit reached.")
                    break
            if self.stop_thread:
                self.logger.info(f"WARNING : SNMP-MONITOR : run() - Thread stopped ahead of time due to a call to stop().")
                break
            self.snmp_querier()
            print(f'I am working. Iteration number {self.iteration_number}')
            self.iteration_number += 1
            self.thread_sleep.wait(timeout=self.profile['interval'])
        self.end_thread_processing()
        self.stopped.set()

    def end_thread_processing(self):
        parse_items = {}
        parse_items.update(self.check_values_change)
        parse_items.update(self.statistics)
        parse_items.update(self.detect_crashes)
        utils = monitor_utils(parse_item = parse_items)
        utils.parse_logfile(logfile_path=self.logfile_path, worker_type='SNMP_MONITOR')
        if self.statistics:
            utils.generate_statistics(logfile_path=self.logfile_path, item_list = self.profile['statistics'],
                                      worker_type='SNMP_MONITOR')
        if self.detect_crashes:
            utils.crash_detector(logfile_path=self.logfile_path, uptime_item=self.profile['detect_crashes'],
                                 worker_type='SNMP_MONITOR')
        if self.check_values_change:
            utils.get_item_value_change(logfile_path=self.logfile_path, item_list=self.profile['check_values_change'],
                                        worker_type='SNMP_MONITOR')

    def stop(self):
        self.logger.info(f"INFO : SNMP-MONITOR : stop() - Thread stop command received.")
        self.stop_thread = True
        self.thread_sleep.set() # this will break the wait
    # the stop mechanism of a worker, works in three steps:
    # 1. a worker is stopped by calling its stop() method. The stop method:
    #    - sets stop_thread attribute to true, which breaks the while loop ahead of time.
    #    - sets the event thread_sleep: - the run function waits for this event to be set with a timeout of self.profile['interval']. Usually
    #                                     this event is not set, the run() function waits the timeout interval, after which a new iteration will begin.
    #                                   - when the thread_sleep event is set, thread_sleep.wait() resolves and a new iteration is forced before the waiting interval
    # 2. So, stop_thread is set to True, thread_sleep is set() which forces a new iteration which will break the loop due to the condition based on stop thread.
    # 3. when run() ends, it set() the 'stopped' event. When this event is set, it tells stop_workers() that the thread really stopped and didn't hang
