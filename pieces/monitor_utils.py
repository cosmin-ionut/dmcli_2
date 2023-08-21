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

    def _write_to_file_hlp(self, logfile_path: str, mode: str, content: str) -> None:
        '''Helper method. Writes content to file. Does not return anything.'''

        with open(file=logfile_path, mode=mode, encoding='utf-8') as logfile:
            logfile.write(content)

    def parse_logfile(self, logfile_path: str, item_dict: dict, worker_type: str = 'undefined') -> None:
        """
        Parses the logfile and populates a dictionary of {item_1:[(timestamp, value), (timestamp, 'error')], item_2:[(timestamp, value). (timestamp, value)],...}
        If a value can't be retrieved based on the regex pattern provided
        :logfile_path: string path to the logfile that will be parsed
        :item_dict: a dictionary of {'item':<compiled_ptrn_obj>, 'item2':<compiled_ptrn_obj>}
        :worker_type: for logging purposes. Not mandatory
        """

        logs = f'\nINFO : {worker_type} : parse_logfile() - Checking the items to parse.\n'

        # if there are any items in self.kwargs['parse_items'] then use those plus the items passed
        items_d = self.kwargs['parse_item'] | item_dict if 'parse_item' in self.kwargs else item_dict
        
        # check whether there are any items to parse (not already parsed) and:
        #  if there aren't any, open the file in append and write the log messages at the bottom
        items_d = {item:pattern for item, pattern in items_d.items() if item not in self.parsed_items_dict}
        if not items_d:
            logs += f'WARNING : {worker_type} : parse_logfile() - Nothing to parse. The values of the supplied items have already been parsed.\n'
            self._write_to_file_hlp(logfile_path=logfile_path, mode='a+', content=logs)
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

                    result = f'Stats for item {item} are:\n Minimum: {minimum[0]} (value first recorded at {minimum[1]})\n ' \
                             f'Maximum: {maximum[0]} (value first recorded at {maximum[1]})\n Average: {average}\n ' \
                             f'Median: {med}\n Most common values: {mmode}\n Number of values used for the calculations: {length}\n\n'
                    logs += result
                except Exception as e:
                    logs += f'\nERROR : {worker_type} : generate_statistics() - Unable to generate statistics for item {item}. Error: {e}\n'
            
            logs += f"INFO : {worker_type} : generate_statistics() - Finished generating statistics for the items provided.\n"

            # iterate through the file and append the results to the dict
            self._write_to_file_hlp(logfile_path=logfile_path, mode='a+', content=logs)

    def crash_detector(self, logfile_path: str, item_dict: dict, worker_type: str = 'undefined') -> None:
            '''Checks whether a crash has occurred by comparing the expected and actual uptimes, based on the timestamps
            of the records.
            logfile_path: the path to the logfile that will be searched for crashes.
            item_dict: a dictionary of {'uptime_item':re.compile('uptime_pattern')}.
                       The pattern must match '0 days, 0:0:0' for CLI and '0:0:00:00.00' for SNMP (-Oqvt)
            worker_type: the utility used to monitor the DUT. For logging purposes only.'''

            self.parse_logfile(logfile_path=logfile_path, item_dict=item_dict, worker_type = worker_type)

            logs = f'\nINFO : {worker_type} : crash_detector() - Started operation.\n'
            
            uptime_item = str(list(item_dict.keys())[0])
            if not self.parsed_items_dict[uptime_item]:
                logs += f"ERROR : {worker_type} : crash_detector() - There are no parsed values for '{uptime_item}'. Cannot continue.\n"
                self._write_to_file_hlp(logfile_path=logfile_path, mode='a+', content=logs)
                return

            last_successful_iteration = None # an iteration which had a valid uptime value (!= 'error')
            for iteration, time_tup in enumerate(self.parsed_items_dict[uptime_item], start=1):
                # if the value for the uptime item (sysUpTime.0), could not be retrieved from the logfile, skip the iteration
                if time_tup[1] == 'error':
                    logs += f"WARNING : {worker_type} : crash_detector() - Error at value retrieval in iteration {iteration}\n"
                    continue
                # convert the uptime item value (CLI: 0 days, 0:0:0 / SNMP: 0:0:00:00.00) to seconds (pattern '[\D\s]+')
                uptime_value = [int(''.join(char for char in element if char.isdigit())) for element in split('[\D\s]+', time_tup[1])]
                uptime_value = 86400*uptime_value[0] + 3600*uptime_value[1] + 60*uptime_value[2] + uptime_value[3]
                # if no last_successful_iteration exist, record the current one and skip anything else.
                if not last_successful_iteration:
                    logs += f"ERROR : {worker_type} : crash_detector() - Couldn't compare uptime values because no " \
                             "previous successful iteration was recorded.\nThis happened because during none of the " \
                            f"iterations before this one (iteration {iteration}) could the uptime be retrieved.\n"
                    last_successful_iteration = (iteration, datetime.strptime(time_tup[0], '%Y-%m-%d %H:%M:%S'), uptime_value)
                    continue
                # true_interval is the time interval between the iterations. 
                true_interval = (datetime.strptime(time_tup[0], '%Y-%m-%d %H:%M:%S') - last_successful_iteration[1]).total_seconds()
                try:
                    # expected_uptime is the expected interval between the values of the uptime item
                    expected_uptime = (last_successful_iteration[2] + true_interval) - 1
                    # if the interval between the values of the uptime item, is lower than the interval between iterations
                    # (minus 1 second due to the fractions of second needed for processing), then a crash has occurred
                    if uptime_value < expected_uptime:
                        logs += f"INFO : {worker_type} : crash_detector() - CRASH detected in iteration {iteration}:" \
                                f' Expected uptime is {expected_uptime} seconds and the retrieved uptime is {uptime_value}' \
                                f' seconds.\nLast successful iteration is {last_successful_iteration[0]}, it is possible' \
                                 ' that the crash occurred immediately after that iteration. \n'
                    last_successful_iteration = (iteration, datetime.strptime(time_tup[0], '%Y-%m-%d %H:%M:%S'), uptime_value)
                except Exception as e:
                    logs += f"ERROR : {worker_type} : crash_detector() - Couldn't compare uptime values: {e}\n"
            logs += f"INFO : {worker_type} : crash_detector() - {len(self.parsed_items_dict[uptime_item])} iterations were checked for crashes.\n"
            logs += f"INFO : {worker_type} : crash_detector() - Operation finished.\n"
            self._write_to_file_hlp(logfile_path=logfile_path, mode='a+', content=logs)

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
    

a = monitor_utils()
a.crash_detector( logfile_path='/home/cosmin/Desktop/new_textfile.txt', item_dict={'sysUpTime.0': compile('\d+\:\d+\:\d+\:\d+')}, worker_type = 'unafined')