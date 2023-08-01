from datetime import datetime, timedelta
from threading import Thread, Event
from subprocess import run as run_proc
import logging
from pieces.monitor_utils import generate_statistics, crash_detector

class snmp_monitor(Thread):
    '''
    Each thread (called snmp worker/oid_inspector worker) inspects a set of OIDs for a single IP. 
    '''

    def __init__(self, profile):

        Thread.__init__(self)
        
        # time settings and default values
        self.timeout = profile['timeout']
        self.interval = profile['interval']
        self.start_time = profile['start_time']
        self.endtime = self.start_time + timedelta(seconds=self.timeout) # set the endtime of the whole monitoring process 

        # logfile configuration
        self.logfile_path = f"logfile_{profile['dut']}_{self.start_time.strftime('%d_%b_%Y_%H_%M_%S')}.log"
        self.logger = logging.getLogger(profile['dut'])
        self.logger.setLevel(logging.DEBUG)
        logfile_handler = logging.FileHandler(self.logfile_path)
        fmt = logging.Formatter('%(asctime)s | %(message)s')
        logfile_handler.setFormatter(fmt)
        self.logger.addHandler(logfile_handler)
        # other settings
        self.dut_ip = profile['dut'] # the IP of the DUT
        self.function = profile['function']
        self.item_list = list(set(profile['items'])) # can contain either OIDs or MIBs. The conversion is done to remove duplicate items
        self.iteration_number = 1 # the index of the iteration
        # end-thread functionalities
        self.statistics = profile['statistics'] if 'statistics' in profile else False
        self.uptime_item = profile['detect_crashes'] if 'detect_crashes' in profile else False
        # stop mechanism
        self.thread_sleep = Event()
        self.stopped = Event()   # | these two work the thread stop mechanism
        self.stop_thread = False # |
        self.daemon = True      

    def snmp_querier(self):
        '''this method snmp queries the DUT, and updates self.results with the retrieved data.
        '''
        self.logger.info(50*'#' + f" Iteration number #{self.iteration_number} started " + 50*'#')
        for item in self.item_list:
            try:
                result = run_proc(['snmpget', '-Oqv', '-v3', '-l', 'authPriv', '-u', 'admin', '-a', 'MD5', '-A', 'privateprivate',
                             '-x', 'DES', '-X', 'privateprivate', self.dut_ip, item], capture_output=True, encoding='utf-8')
                if result.stdout.replace(" ", '') == '':
                    raise Exception(result.stderr)
                self.logger.info(f'ITEM: {item} query result:  {result.stdout.rstrip()}')
            except Exception as e:
                self.logger.info(f'ITEM: {item} query result: ERROR: {str(e).rstrip()}')
        self.logger.info(129*'#' + 3*'\n')

    def run(self):
        self.logger.info(f"INFO : SNMP-MONITOR : run() - Thread operation started.\n\n\n")
        while True:
            if not self.endtime > datetime.now():
                self.logger.info(f"INFO : SNMP-MONITOR : run() - Thread finished execution. Time limit reached.")
                break
            if self.stop_thread:
                self.logger.info(f"WARNING : SNMP-MONITOR : run() - Thread stopped ahead of time due to a call to stop().")
                break
            self.snmp_querier()
            print(f'I am working. Iteration number {self.iteration_number}')
            self.iteration_number += 1
            self.thread_sleep.wait(timeout=self.interval)
        if self.statistics:
            generate_statistics(logfile_path=self.logfile_path, item_list=self.item_list, pattern="\s\s[0-9a-zA-Z\-\.\\\/]+", worker_type='SNMP_MONITOR')
        if self.uptime_item:
            crash_detector(logfile_path=self.logfile_path, uptime_pattern='\d+\:\d+\:\d+\:\d+', uptime_item=self.uptime_item, worker_type='SNMP_MONITOR')
        self.stopped.set()
        
    def stop(self):
        self.logger.info(f"INFO : SNMP-MONITOR : stop() - Thread stop command received.")
        self.stop_thread = True
        self.thread_sleep.set() # this will break the wait
    # the stop mechanism of a worker, works in three steps:
    # 1. a worker is stopped by calling its stop() method. The stop method:
    #    - sets stop_thread attribute to true, which breaks the while loop ahead of time.
    #    - sets the event thread_sleep: - the run function waits for this event to be set with a timeout of self.interval. Usually
    #                                     this event is not set, the run() function waits the timeout interval, after which a new iteration will begin.
    #                                   - when the thread_sleep event is set, thread_sleep.wait() resolves and a new iteration is forced before the waiting interval
    # 2. So, stop_thread is set to True, thread_sleep is set() which forces a new iteration which will break the loop due to the condition based on stop thread.
    # 3. when run() ends, it set() the 'stopped' event. When this event is set, it tells stop_workers() that the thread really stopped and didn't hang
