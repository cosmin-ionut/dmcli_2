from datetime import datetime, timedelta
from threading import Thread, Event
import logging
from re import search
from time import sleep
from pexpect import spawn, TIMEOUT, EOF, expect
from monitor_utils import monitor_utils
from re import compile
from os.path import dirname, realpath

class console_monitor(Thread):

    def __init__(self, profile: dict) -> None:

        Thread.__init__(self)

        self.profile = profile

        # set the endtime of the whole monitoring process 
        self.endtime = profile['start_time'] + timedelta(seconds=profile['timeout']) if profile['timeout'] else None
        # path settings
        mainDir = f"{dirname(realpath(__file__))}/.."
         
        #logfile configuration
        self.logfile_path = f"{mainDir}/logfiles/logfile_cli_{profile['dut'].replace(' ','_')}_{profile['start_time'].strftime('%d_%b_%Y_%H_%M_%S')}.log"
        self.logger = logging.getLogger(f"{profile['dut'].replace(' ','_')}_cli")
        self.logger.setLevel(logging.DEBUG)
        logfile_handler = logging.FileHandler(self.logfile_path)
        fmt = logging.Formatter('%(asctime)s | %(message)s')
        logfile_handler.setFormatter(fmt)
        self.logger.addHandler(logfile_handler)

        # other settings
        self.utility = profile['utility']
        self.item_list = list(set(profile['items'])) # can contain either OIDs or MIBs. The conversion is done to remove duplicate items
        #self.item_list = item_list
        self.iteration_number = 1 # the index of the iteration
        self.connection = False
        self.error_counter = 0
        # end-thread processing
        self.statistics = {item: compile("\\B\s\s[0-9\-\.\\\/]+") for item in profile['statistics']} if 'statistics' in profile else {}
        self.detect_crashes = {profile['detect_crashes']: compile('\d+\sdays?.*\d+.*\d+.*\d+')} if 'detect_crashes' in profile else {}
        self.check_values_change = {item: compile("\\B\s\s.*") for item in profile['check_values_change']} if 'check_values_change' in profile else {}
        # stop mechanism
        self.thread_sleep = Event()
        self.stopped = Event()   # | these two work the thread stop mechanism
        self.stop_thread = False # |
        self.daemon = True

    def spawn_cli_connection(self):

        command = self.profile['dut']
        self.logger.info(f"INFO : CLI-MONITOR : spawn_cli_connection() - Spawning new CLI connection to DUT")

        while True:

            if self.endtime:
                if not self.endtime > datetime.now():
                    self.logger.info(f"WARNING : CLI-MONITOR : spawn_cli_connection() - Thread time limit reached before spawning a connection")
                    break

            connection = spawn(command, timeout=int('10'), encoding='utf-8', codec_errors='ignore')
            index = connection.expect(['Connected.*', TIMEOUT, EOF], timeout=10)

            if index == 0:
                next_index = connection.expect([TIMEOUT, EOF], timeout=2) # if the connection is open then Timeout. If device open failure, then EOF
                if next_index != 1:
                    self.logger.info(f"INFO : CLI-MONITOR : spawn_cli_connection() - CLI connection successful")
                    self.connection = connection
                    break
            self.logger.info(f"ERROR : CLI-MONITOR : spawn_cli_connection() - Unable to open CLI connection. Code: {index}:{next_index}. Retrying in 10 seconds...")
            connection.close()
            sleep(10)

    def cli_logger(self):

        self.logger.info(f"INFO : CLI-MONITOR : cli_logger() - DUT login requested")

        if not self.connection:
            self.logger.info(f"ERROR : CLI-MONITOR : cli_logger() - CLI connection unexistent. Logging not possible.")
            return

        prompts = ['[Uu]ser(name)*:',
                   '[Pp]assword:',
                   '(Enter )*[Nn]ew [Pp]assword:',
                   'Confirm [Nn]ew [Pp]assword:|Retype:',
                   'Accessrole',
                   '.+\((Interface|Config|Factory).*\)\#', # interface config or factory and matches any cli prompt
                   '.+\#$', # enable
                   'Access denied',
                   'Wrong username or password',
                   'Press ENTER to get started',
                   '.+\>$', # pre enable
                   TIMEOUT, EOF]

        authentication_failure = 0

        # get CLI
        self.clear_cli_buffer()
        self.connection.send('\r')
        state = self.connection.expect(prompts, timeout= 5)

        # repeat until it gets to enable mode
        while state != 6:
            if authentication_failure == 3:
                self.logger.info(f"CRITICAL : CLI-MONITOR : cli_logger() - Authentication to DUT failed. Stopping the worker...")
                self.stop()
                return
            if state == 0:
                self.connection.send('admin\r')
            elif state == 1 or state == 2 or state == 3 :
                self.connection.send('private\r')
            elif state == 4:
                self.connection.send('1\r')
            elif state == 7 or state == 8:
                authentication_failure += 1
                self.logger.info(f"ERROR : CLI-MONITOR : cli_logger() - Authentication failed using username and password")
                sleep(10)
                self.connection.send('\r')
                self.connection.send('\r')
            elif state == 9:
                self.connection.send('\r')
            elif state == 10:
                self.connection.send('enable\r')
            elif state == 5:
                self.connection.send('exit\r')
                self.connection.send('exit\r')
                self.connection.send('exit\r')
                self.connection.send('enable\r')
            elif state == 11 or state == 12:
                self.logger.info(f"ERROR : CLI-MONITOR : cli_logger() - CLI connection dead.")
                self.connection.close()
                self.connection = False
                return False

            sleep(1)
            state = self.connection.expect(prompts, timeout= 2)
        self.logger.info(f"INFO : CLI-MONITOR : cli_logger() - DUT login successful. Enable reached.")
        return True

    def cli_querier(self):

        self.logger.info(50*'#' + f" Iteration number #{self.iteration_number} started " + 50*'#')

        for item in self.item_list:

            if not self.connection:
                self.logger.info(f'ITEM: {item[1]} query result: ERROR:  CLI connection dead.')
                continue # crash_detector needs the items written in the logfile for each iteration to calculate time intervals. can't use break or return

            self.connection.send('\r')

            if not self.clear_cli_buffer():
                self.logger.info(f'ITEM: {item[1]} query result: ERROR:  CLI connection dead.')
                continue

            self.connection.send(item[0] + '\r')
            index = self.connection.expect(['--More-- or \(q\)uit', '\S\#$', TIMEOUT, EOF], timeout = 3)

            while True:
                if index == 0 and item[1] in self.connection.before:
                    result = self.connection.before[self.connection.before.find(item[1]):self.connection.before.find('\n', self.connection.before.find(item[1]))]
                    self.connection.send('q\r')
                    break
                elif index == 0:
                    self.connection.send('\n\r')
                elif index == 1 or index == 2:
                    result = self.connection.before[self.connection.before.find(item[1]):self.connection.before.find('\n', self.connection.before.find(item[1]))]
                    break
                else:
                    self.logger.info(f'ITEM: {item[1]} query result: ERROR:  CLI connection dead.')
                    self.connection.close()
                    self.connection = False
                    continue

                index = self.connection.expect(['--More-- or (q)uit', '\S\#$', TIMEOUT, EOF], timeout = 5)

            try:
                result = search('\.\.(-|)[^.].*', result).group(0)[2:]
                self.logger.info(f'ITEM: {item[1]} query result:  {result.strip()}')
                self.error_counter = 0
            except Exception as e:
                self.logger.info(f'ITEM: {item[1]} query result: ERROR:  {str(e).strip()}')
                self.error_counter += 1
                if self.error_counter >= len(self.item_list)*3: # if for more than three consecutive iterations, values can not be retrieved, close the connection.
                    self.connection.close()
                    self.connection = False
                    continue
        self.logger.info(129*'#' + 3*'\n')

    def clear_cli_buffer(self):
        #self.logger.info(f"INFO : CLI-MONITOR : clear_cli_buffer() - 'before' buffer clear requested")
        index = self.connection.expect([TIMEOUT, EOF], timeout= 0.1)
        if index == 0:
            if self.connection.before:
                self.connection.expect (r'.+')  # stack overflow. No idea what this does but it works
            return True
        else:
            self.logger.info(f"ERROR : CLI-MONITOR : clear_cli_buffer() - CLI connection dead.")
            self.connection.close()
            self.connection = False
            return False

    def run(self):
        self.logger.info(f"INFO : CLI-MONITOR : run() - Thread operation started.\n\n\n")
        if not self.endtime:
            self.logger.info(f"WARNING : CLI-MONITOR : run() - A time limit for the monitoring process was not set.\n")
        while True:
            if self.endtime:
                if not self.endtime > datetime.now():
                    self.logger.info(f"INFO : CLI-MONITOR : run() - Thread finished execution. Time limit reached.")
                    break
            if self.stop_thread:
                self.logger.info(f"WARNING : CLI-MONITOR : run() - Thread stopped ahead of time due to a call to stop().")
                break
            if not self.connection:
                self.logger.info(f"ERROR : CLI-MONITOR : run() - CLI connection dead. Trying to respawn it...")
                self.spawn_cli_connection()
                if not self.cli_logger():
                    continue
            print(f'I am working. Iteration number {self.iteration_number}')
            self.cli_querier()
            self.iteration_number += 1
            self.thread_sleep.wait(timeout=self.profile['interval'])
        if self.connection:
            self.connection.close()
        self.end_thread_processing()
        self.stopped.set()

    def end_thread_processing(self):
        parse_items = {}
        parse_items.update(self.check_values_change)
        parse_items.update(self.statistics)
        parse_items.update(self.detect_crashes)
        utils = monitor_utils(parse_item = parse_items)
        utils.parse_logfile(logfile_path=self.logfile_path, worker_type='CONSOLE_MONITOR')
        if self.statistics:
            utils.generate_statistics(logfile_path=self.logfile_path, item_list = self.profile['statistics'],
                                      worker_type='CONSOLE_MONITOR')
        if self.detect_crashes:
            utils.crash_detector(logfile_path=self.logfile_path, uptime_item=self.profile['detect_crashes'],
                                 uptime_type='timestring', worker_type='CONSOLE_MONITOR')
        if self.check_values_change:
            utils.get_item_value_change(logfile_path=self.logfile_path, item_list=self.profile['check_values_change'],
                                        worker_type='CONSOLE_MONITOR')

    def stop(self):
        self.logger.info(f"INFO : CLI-MONITOR : stop() - Thread stop command received.")
        self.stop_thread = True
        self.thread_sleep.set()
