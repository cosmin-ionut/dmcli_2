from datetime import datetime, timedelta
from re import compile, split, match
from subprocess import run, CalledProcessError
from sys import version_info
from importlib import util
from platform import system
from collections import defaultdict
from statistics import median, mean, multimode

class monitor_utils():

    def __init__(self):

        self.parsed_items_dict = defaultdict(list)


    def parse_logfile(self, logfile_path: str, item_list: list, pattern: str, worker_type: str = 'undefined') -> None:
        """
        Parses the logfile and populates a dictionary of {item_1:(timestamp, value), item_2:(timestamp, value), item_3:(timestamp, 'error')}
        If a value can't be retrieved based on the regex pattern provided
        :logfile_path: string path to the logfile that will be parsed
        :item_list: the list of items whose values will be retrieved
        :pattern: the pattern used to retrieve the value for ALL items. Separate patterns for each item are not possible
        :worker_type: for logging purposes. Not mandatory
        """

        logs = f'\nINFO : {worker_type} : parse_logfile() - Checking the items to parse.\n'
        
        # check whether there are any items to parse (not already parsed) and:
        #  if there aren't any, open the file in append and write the log messages at the bottom
        items = [item for item in item_list if item not in self.parsed_items_dict]
        if not items:
            logs += f'ERROR : {worker_type} : parse_logfile() - Nothing to parse. The values of the supplied items have already been parsed.\n'
            with open(logfile_path, 'a+', encoding='utf-8') as logfile:
                logfile.write(logs)
            return

        #  if there are, open the file in read so you can iterate through it and parse the items
        with open(logfile_path, 'r+', encoding='utf-8') as logfile:
            
            logs += f'INFO : {worker_type} : parse_logfile() - Started parsing the logfile.\n'

            ptrn = compile(pattern)

            for line_nr, line in enumerate(logfile, start=1):
                if not line.strip():
                    continue 
                for item in items:
                    if f'| ITEM: {item}' in line:
                        val = ptrn.search(line)
                        if val:
                            self.parsed_items_dict[item].append((line[:19], val.group(0)))
                            break
                        logs += f"WARNING : {worker_type} : parse_logfile() - Couldn't retrieve value of {item} from line {line_nr}\n"
                        self.parsed_items_dict[item].append((line[:19], 'error'))
                        break
            logs += f"INFO : {worker_type} : parse_logfile() - Finished parsing the logfile\n"
            logfile.write(logs)


    def generate_statistics(self, logfile_path: str, item_list: list, pattern: str, worker_type: str='undefined') -> None:
            """
            The function searches for the items, through a logfile. For each item, from every line in the logfile it is present,
            extracts its value and calculates various statistics.
            Logfile entry format:
            <TIMESTAMP> | ITEM: <item> some text here: <integral_value> none or some more text here 
            2022-11-06 15:21:00,652 | ITEM: .1.3.6.1.4.1.248.11.22.1.8.10.1.0 query result:  100 percent
            :logfile_path: path to the logfile
            :item_list: the items whose statistics will be generated
            :pattern: the regex pattern used to extract the value from each line in the logfile
                    MUST always match an integral. Ex: \s\s[0-9]+\s
            :worker_type: Optional. the worker type used to generate the logfile.
            """

            self.parse_logfile(logfile_path=logfile_path, item_list=item_list, pattern=pattern, worker_type = worker_type)

            logs = f'\nINFO : {worker_type} : generate_statistics() - Started generating statistics.\n'

            for item in item_list:

                timestamp_list = [val_tup[0] for val_tup in self.parsed_items_dict[item] if val_tup[1] != 'error']
                values_list = [int(val_tup[1]) for val_tup in self.parsed_items_dict[item] if val_tup[1] != 'error']

                # check how to use this zip if no item matches
                #timestamp_list, values_list = zip(*[(timestamp, int(value)) for timestamp, value in self.parsed_items_dict[item] if value != 'error'])

                try:
                    minimum = (min(values_list), timestamp_list[values_list.index(min(values_list))])
                    # min_value, min_timestamp = min(zip(values_list, timestamp_list), key=lambda pair: pair[0])
                    maximum = (max(values_list), timestamp_list[values_list.index(max(values_list))])
                    average = mean(values_list)
                    med = median(values_list)
                    mmode = multimode(values_list)
                    length = len(values_list)

                    result = f'Stats for item {item} are:\n Minimum: {minimum[0]} (value first recorded at {minimum[1]})\n Maximum: {maximum[0]} (value first recorded at {maximum[1]})\n Average: {average}\n ' \
                                f'Median: {med}\n Most common values: {mmode}\n Number of values used for the calculations: {length}\n\n'
                    logs += result
                except:
                    logs += f'\nERROR : {worker_type} : generate_statistics() - Unable to generate statistics for item {item}.\n'
            
            logs += f"INFO : {worker_type} : generate_statistics() - Finished generating statistics for the items provided.\n"

            # iterate through the file and append the results to the dict
            with open(logfile_path, 'a+', encoding='utf-8') as logfile:
                logfile.write(logs)

    def crash_detector(self, logfile_path: str, uptime_pattern: str, uptime_item: str, worker_type: str = 'undefined') -> None:
            '''
            logfile_path : the path to the logfile that will be searched for crashes
            uptime_pattern : the regex pattern of the uptime value. Must match '0 days, 0:0:0' for CLI and '0:0:00:00.00' for snmp (-Oqvt)
            uptime_item : the item that represent DUT's uptime.
            worker_type : only for logging purposes.
            '''

            self.parse_logfile(logfile_path=logfile_path, item_list=[uptime_item], pattern=uptime_pattern, worker_type = worker_type)

            logs = f'\nINFO : {worker_type} : crash_detector() - Started operation.\n'
    
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
            logs += f"INFO : {worker_type} : crash_detector() - Operation finished."
            with open(logfile_path, 'a+', encoding='utf-8') as logfile:
                logfile.write(logs)

    # crash_detector() iterates through the logfile and dynamically calculates the expected seconds based on the interval between two distict iterations.
    # thus, it takes into account both the interval between iterations AND the time needed for an iteration to complete, plus an error of 1 seconds. 
    # it is VERY dependant on the format of the logfile

    def environment_check(self, function:str) -> tuple:
        '''
        Checks the requirements of the app: Linux OS, python version 3.9 or newer and snmpget
        '''

        if system() != 'Linux':
            # Linux is needed because pexpect module is available on Linux only.
            # Pexpect has an alternative for Windows called wexpect but I didn't test that one
            return (False, 'Linux OS is required to run this app')

        # check python version:
        if int(version_info.major) < 3 and int(version_info.minor) < 9:
            return (False, 'Python version 3.9 or newer required to run this application')

        # check if pexpect is installed
        if function == 'console_monitor' and not util.find_spec('pexpect'):
            return (False, 'Pexpect module is needed to run this application')
        
        # check if snmpget is installed
        if function == 'snmp_monitor':
            try:
                run(['snmpget', '--h'])
            except FileNotFoundError:
                return (False, 'snmpget linux tool is required to run this application')
            except CalledProcessError:
                return (False, 'snmpget linux tool reported an error upon execution')

        return True, None