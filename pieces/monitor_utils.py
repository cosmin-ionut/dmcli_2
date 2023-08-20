from datetime import datetime, timedelta
from re import compile, split, match
from subprocess import run, CalledProcessError
from sys import version_info
from importlib import util
from platform import system
from collections import defaultdict
from statistics import median, mean, multimode

class monitor_utils():

    def __init__(self, **kwargs):
        '''
        self.kwargs is an argument use to provide additional functionality to the methods
        '''

        self.kwargs = kwargs
        self.parsed_items_dict = defaultdict(list)

    def parse_logfile(self, logfile_path: str, item_dict: dict, worker_type: str = 'undefined') -> None:
        """
        Parses the logfile and populates a dictionary of {item_1:[(timestamp, value), (timestamp, 'error')], item_2:[(timestamp, value). (timestamp, value)],...}
        If a value can't be retrieved based on the regex pattern provided
        :logfile_path: string path to the logfile that will be parsed
        :item_dict: a dictionary of {'item':<compiled_ptrn_obj>, 'item2':<compiled_ptrn_obj>}
        :worker_type: for logging purposes. Not mandatory
        """

        logs = f'\nINFO : {worker_type} : parse_logfile() - Checking the items to parse.\n'

        # if there are any items in self.kwargs['parse_items'] then use those, otherwise, use the items passed
        items_d = self.kwargs['parse_item'] if 'parse_item' in self.kwargs and self.kwargs['parse_item'] else item_dict       
        
        # check whether there are any items to parse (not already parsed) and:
        #  if there aren't any, open the file in append and write the log messages at the bottom
        items_d = {item:pattern for item, pattern in items_d.items() if item not in self.parsed_items_dict}
        if not items_d:
            logs += f'WARNING : {worker_type} : parse_logfile() - Nothing to parse. The values of the supplied items have already been parsed.\n'
            with open(logfile_path, 'a+', encoding='utf-8') as logfile:
                logfile.write(logs)
            return

        #  if there are, open the file in read so you can iterate through it and parse the items
        with open(logfile_path, 'r+', encoding='utf-8') as logfile:
            
            logs += f'INFO : {worker_type} : parse_logfile() - Started parsing the logfile.\n'

            for line_nr, line in enumerate(logfile, start=1):
                if not line.strip():
                    continue 
                for item, pattern in items_d.items():
                    if f'| ITEM: {item}' in line:
                        val = pattern.search(line)
                        if val:
                            self.parsed_items_dict[item].append((line[:19], val.group(0)))
                            break
                        logs += f"WARNING : {worker_type} : parse_logfile() - Couldn't retrieve value of {item} from line {line_nr}\n"
                        self.parsed_items_dict[item].append((line[:19], 'error'))
                        break
            logs += f"INFO : {worker_type} : parse_logfile() - Finished parsing the logfile\n"
            logfile.write(logs)


    def generate_statistics(self, logfile_path: str, item_dict: list, worker_type: str='undefined') -> None:
            """
            The method searches for the items, through a logfile. For each item, from every line in the logfile it is present,
            extracts its value and calculates various statistics.
            Logfile entry format:
            <TIMESTAMP> | ITEM: <item> some text here: <integral_value> none or some more text here 
            2022-11-06 15:21:00,652 | ITEM: .1.3.6.1.4.1.248.11.22.1.8.10.1.0 query result:  100 percent
            :logfile_path: path to the logfile
            :item_dict: a dictionary of {'item':<compiled_ptrn_obj>, 'item2':<compiled_ptrn_obj>}
                        the patterns should  match an integral. Ex: \s\s[0-9]+\s
            :worker_type: Optional. the worker type used to generate the logfile.
            """

            self.parse_logfile(logfile_path=logfile_path, item_dict=item_dict, worker_type = worker_type)

            logs = f'\nINFO : {worker_type} : generate_statistics() - Started generating statistics.\n'

            for item in item_dict:

                timestamp_list = [val_tup[0] for val_tup in self.parsed_items_dict[item] if val_tup[1] != 'error']
                try:
                    values_list = [int(val_tup[1]) for val_tup in self.parsed_items_dict[item] if val_tup[1] != 'error']
                except ValueError:
                    logs += f'\nERROR : {worker_type} : generate_statistics() - Item {item} does not have integral value. Skipping it.\n'
                    continue

                try:
                    minimum = min(zip(values_list, timestamp_list), key=lambda pair: pair[0])
                    maximum = max(zip(values_list, timestamp_list), key=lambda pair: pair[0])
                    average = mean(values_list)
                    med = median(values_list)
                    mmode = multimode(values_list)
                    length = len(values_list)

                    result = f'Stats for item {item} are:\n Minimum: {minimum[0]} (value first recorded at {minimum[1]})\n Maximum: {maximum[0]} (value first recorded at {maximum[1]})\n Average: {average}\n ' \
                                f'Median: {med}\n Most common values: {mmode}\n Number of values used for the calculations: {length}\n\n'
                    logs += result
                except Exception as e:
                    logs += f'\nERROR : {worker_type} : generate_statistics() - Unable to generate statistics for item {item}. Error: {e}\n'
            
            logs += f"INFO : {worker_type} : generate_statistics() - Finished generating statistics for the items provided.\n"

            # iterate through the file and append the results to the dict
            with open(logfile_path, 'a+', encoding='utf-8') as logfile:
                logfile.write(logs)

    def crash_detector(self, logfile_path: str, item_dict: str, worker_type: str = 'undefined') -> None:
            '''
            Checks wheter a crash has occurred by comparing the expected uptime and actual uptime, based on the timestamps when these values were retrieved.
            logfile_path : the path to the logfile that will be searched for crashes
            pattern : the regex pattern of the uptime value. Must match '0 days, 0:0:0' for CLI and '0:0:00:00.00' for snmp (-Oqvt)
            item : the item that represent DUT's uptime (sysUpTime.0 for example).
            worker_type : only for logging purposes.
            '''

            self.parse_logfile(logfile_path=logfile_path, item_dict=item_dict, worker_type = worker_type)

            logs = f'\nINFO : {worker_type} : crash_detector() - Started operation.\n'
            
            uptime_item = str(list(item_dict.keys())[0])
            if not self.parsed_items_dict[uptime_item]:
                logs += f"ERROR : {worker_type} : crash_detector() - There are no parsed values for '{uptime_item}'. Cannot continue.\n"
                with open(logfile_path, 'a+', encoding='utf-8') as logfile:
                    logfile.write(logs)
                return
    
            uptimes_dict = {}

            for iteration, time_tup in enumerate(self.parsed_items_dict[uptime_item], start=1):
                try:
                    uptime_parse_list = split('[\D\s]+', time_tup[1])
                    uptime_parse_list = [int(''.join(char for char in element if char.isdigit())) for element in uptime_parse_list]
                    uptimes_dict[iteration] = (datetime.strptime(time_tup[0], '%Y-%m-%d %H:%M:%S'), 
                                               86400*uptime_parse_list[0] + 3600*uptime_parse_list[1] + 
                                               60*uptime_parse_list[2] + uptime_parse_list[3])
                except:
                    uptimes_dict[iteration] = (datetime.strptime(time_tup[0], '%Y-%m-%d %H:%M:%S'), 'error')

            last_successful_iteration = None
            for iteration, time_tup in uptimes_dict.items():
                if time_tup[1] == 'error':
                    logs += f"WARNING : {worker_type} : crash_detector() - Error at value retrieval in iteration {iteration}\n"
                    continue
                if not last_successful_iteration:
                    logs += f"ERROR : {worker_type} : crash_detector() - Couldn't compare uptime values because no previous successful iteration was recorded.\n" \
                            f'This happened because during none of the iterations before this one (iteration {iteration}) could the uptime be retrieved.\n'
                    last_successful_iteration = iteration
                    continue
                true_interval = (time_tup[0] - uptimes_dict[last_successful_iteration][0]).total_seconds() # timedelta between the current and the last successful iteration in timeticks
                try:
                    expected_uptime = (uptimes_dict[last_successful_iteration][1] + true_interval) - 1 # a hardcoded 1 second error interval.
                    if time_tup[1] < expected_uptime:
                        logs += f"INFO : {worker_type} : crash_detector() - CRASH detected in iteration {iteration}:" \
                                f' Expected uptime is {expected_uptime} seconds and the retrieved uptime is {time_tup[1]} seconds.\n' \
                                f' Last successful iteration is {last_successful_iteration}, it is possible that the crash occurred immediately after that iteration \n'
                    last_successful_iteration = iteration
                except Exception as e:
                    logs += f"ERROR : {worker_type} : crash_detector() - Couldn't compare uptime values: {e}\n"
            logs += f"INFO : {worker_type} : crash_detector() - {len(uptimes_dict)} iterations were checked for crashes.\n"
            logs += f"INFO : {worker_type} : crash_detector() - Operation finished."
            with open(logfile_path, 'a+', encoding='utf-8') as logfile:
                logfile.write(logs)

    # crash_detector() iterates through the logfile and dynamically calculates the expected seconds based on the interval between two distict iterations.
    # thus, it takes into account both the interval between iterations AND the time needed for an iteration to complete, plus an error of 1 seconds. 
    # it is VERY dependant on the format of the logfile

    def _console_monitor_req_check_hlp(self) -> tuple:
        '''Helper method. Checks whether the requirements for 'console_monitor' utility are met or not. Returns:
        * tuple: (True, None) if requirements are met;
        * tuple: (False, 'err_msg') if requirements are not met.'''

        # check if pexpect is installed
        if not util.find_spec('pexpect'):
            return (False, 'Pexpect module is needed to use console_monitor utility')

        # check if telnet is installed
        try:
            run(['which', 'telnet'], capture_output=True, check=True)
        except (FileNotFoundError, CalledProcessError):
            return (False, 'telnet is needed to use console_monitor utility but it is not installed')         
        
        return True, None

    def _snmp_monitor_req_check_hlp(self) -> tuple:
        '''Helper method. Checks whether the requirements for 'snmp_monitor' utility are met or not. Returns:
        * tuple: (True, None) if requirements are met;
        * tuple: (False, 'err_msg') if requirements are not met.'''

        try:
            run(['snmpget', '-V'], capture_output=True, check=True)
        except (FileNotFoundError, CalledProcessError):
            return (False, 'snmpget is needed to use snmp_monitor utility but it is not installed or reported errors during version check')
        
        return True, None


    def environment_check(self, utility:str) -> tuple:
        '''Checks whether the requirements for running the app are met or not.\n
        Parms: 
        * utility: string. The utility used to monitor the device (e.g. snmp_monitor).

        Returns:
        * tuple: (True, None) if requirements are met;
        * tuple: (False, 'err_msg') if requirements are not met.'''

        d = {'console_monitor': self._console_monitor_req_check_hlp,
             'snmp_monitor': self._snmp_monitor_req_check_hlp}

        if system() != 'Linux':
            # Linux is needed because pexpect module is available on Linux only.
            # Pexpect has an alternative for Windows called wexpect but I didn't test that one
            return (False, 'Linux OS is required to run this app')

        if version_info < (3, 9):
            return (False, 'Python version 3.9 or newer required to run this application')

        rc, msg = d[utility]()
        if not rc:
            return rc, msg 

        return True, None