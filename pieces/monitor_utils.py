from datetime import datetime, timedelta
from re import compile, split, match
from subprocess import run, CalledProcessError
from sys import version_info
from importlib import util
from platform import system
from collections import defaultdict
from statistics import median, mean, multimode

def generate_statistics(logfile_path: str, item_list: list, pattern: str, worker_type: str=None) -> None:
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
	
        logs = f'\nINFO : {worker_type} : generate_statistics() - Started generating statistics.\n'
        ptrn = compile(pattern)
        
        # prepare the dictionary
        results_d = defaultdict(list)

        # iterate through the file and append the results to the dict
        with open(logfile_path, 'r+', encoding='utf-8') as logfile:
            for line_nr, line in enumerate(logfile, start=1):
                if not line.strip():
                    continue #if the line is empty, skip it
                for item in item_list:
                    if f'| ITEM: {item}' in line:
                        val = ptrn.search(line)
                        if val:
                            results_d[item].append(int(val.group(0)))
                            break
                        logs += f"WARNING : {worker_type} : generate_statistics() - Couldn't retrieve value of {item} from line {line_nr}\n"
                        break
            for item in results_d:
                result = f'Stats for item {item} are:\n Minimum: {min(results_d[item])}\n Maximum: {max(results_d[item])}\n Average: {mean(results_d[item])}\n ' \
                         f'Median: {median(results_d[item])}\n Most common values: {multimode(results_d[item])}\n Number of values used for the calculations: {len(results_d[item])}\n\n'
                logs += result
            logs += f"INFO : {worker_type} : generate_statistics() - Statistics generated\n"
            logfile.write(logs)

def crash_detector(logfile_path: str, uptime_pattern: str, uptime_items: list, worker_type: str = None) -> None:
        '''
        logfile_path : the path to the logfile that will be searched for crashes
        uptime_pattern : the regex pattern of the uptime value. Must match '0 days, 0:0:0' for CLI and '0:0:00:00.00' for snmp (-Oqvt)
        uptime_items : a list of items that represent DUT's uptime. Example: System uptime (CLI), sysUpTime.0 (or OID equivalent)
        worker_type : only for logging purposes.
        '''
        logs = f'\nINFO : {worker_type} : crash_detector() - Started operation.\n'
        uptimes_dict = {}
        datetime_pattern = compile('[0-9]*-[0-9]*-[0-9]*\s[0-9]*:[0-9]*:[0-9]*') # the pattern of the timestamp. Matches '2022-11-06 14:50:52'
        uptime_pattern = compile(uptime_pattern)
        # build a dictionary of {1: [logtime, uptime], iteration_number: [timedate_obj, seconds]}
        i = 1
        with open(logfile_path, 'r+', encoding='utf-8') as logfile:
            for line in logfile:                                                          # | read each line in the logfile and if any of the uptime_items passed is on that line,
                if any(f'| ITEM: {uptime_item}' in line for uptime_item in uptime_items): # | then try to retrieve the iteration timestamp and the uptime.
                    uptimes_dict[i] = []
                    try:
                        uptimes_dict[i].append(datetime.strptime(datetime_pattern.search(line).group(0), '%Y-%m-%d %H:%M:%S')) # get iteration uptime
                        line_uptime = uptime_pattern.search(line).group(0)              # | get the uptime value based on uptime_pattern        
                        uptime_parse_list = split('[\D\s]+', line_uptime)               # | split the value into a list of days hours minutes seconds
                        k = 0                                                           # |
                        for item in uptime_parse_list:                                  # | each item in list has any non-digit character removed and the list is rebuilt
                            uptime_parse_list[k] = int(match('[\d\s]+', item).group(0)) # |
                            k += 1                                                      # | the total number of seconds is then calculated
                        uptimes_dict[i].append(86400*uptime_parse_list[0] + 3600*uptime_parse_list[1] + 60*uptime_parse_list[2] + uptime_parse_list[3])
                    except:
                        uptimes_dict[i].append('error')
                    i += 1
            # compare the values
            last_successful_iteration = None
            for iteration in range(1, len(uptimes_dict)+1):
                if uptimes_dict[iteration][1] == 'error':
                    logs += f"WARNING : {worker_type} : crash_detector() - Error at value retrieval in iteration {iteration}\n"
                    continue
                if not last_successful_iteration:
                    logs += f"ERROR : {worker_type} : crash_detector() - Couldn't compare uptime values because no previous successful iteration was recorded.\n" \
                            f'This happened because during none of the iterations before this one (iteration {iteration}) could the uptime be retrieved.\n'
                    last_successful_iteration = iteration
                    continue
                true_interval = (uptimes_dict[iteration][0] - uptimes_dict[last_successful_iteration][0]).total_seconds() # timedelta between the current and the last successful iteration in timeticks
                try:
                    expected_uptime = (uptimes_dict[last_successful_iteration][1] + true_interval) - 1 # a hardcoded 1 second error interval.
                    if uptimes_dict[iteration][1] < expected_uptime:
                        logs += f"INFO : {worker_type} : crash_detector() - CRASH detected in iteration {iteration}:" \
                                f' Expected uptime is {expected_uptime} seconds and the retrieved uptime is {uptimes_dict[iteration][1]} seconds.\n' \
                                f' Last successful iteration is {last_successful_iteration}, it is possible that the crash occurred immediately after that iteration \n'
                    last_successful_iteration = iteration
                except Exception as e:
                    logs += f"ERROR : {worker_type} : crash_detector() - Couldn't compare uptime values: {e}\n"
            logs += f"INFO : {worker_type} : crash_detector() - Operation finished."
            logfile.write(logs)

# crash_detector() doesn't use the querying interval passed by the user. It iterates through the logfile and dynamically calculates the expected seconds based on the interval between two distict iterations.
# thus, it takes into account both the interval between iterations AND the time needed for an iteration to complete, plus an error of 1 seconds. 
# it is VERY dependant on the format of the logfile

def environment_check(function:str) -> tuple:
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
