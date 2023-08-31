**LIMITATIONS**:
1. **limitation**: `parse_logfile()` goes through the logfile each time it is called, if the items it has to parse aren't already parsed.<br />
   **mitigation**: `monitor_utils()` can be instantiated using `parse_item` dictionary in `kwargs`. This will force
   `parse_logfile()` to parse both the items passed to it as argument, AND, the items from `parse_item` in the first iteration.<br />
   If used right, all the needed items will be parsed in a single iteration through the logfile, although `parse_logfile()` may be called multiple times. Please be aware that the items and their patterns from 'kwargs["parse_items"]' have priority over those passed
   directly to the 'parse_logfile()' method. For instance, an item from kwargs['parse_items'] will replace, and can not be replaced, by the same item passed directly to the function.

2. **limitation**: `parse_logfile()` uses lazy iteration when going through the logfile and parsing values. However, the parsed values are stored in memory, which might prove problematic if there are too many items to be parsed, each having too many values.<br />
   **mitigation**: none.

  
**FUTURE IDEAS**:
1. `console_monitor` can be changed to support multiple utilities as follows:
 - multiple utilities such as `telnet`, `ssh` and `ser2net`
 - each utility is a separate monitor function: `telnet_monitor` uses telnet, `ssh_monitor` uses ssh,
   `ser2net_monitor` uses telnet and ser2net utilities
 - each of these utilities is a separate class inheriting from `console_monitor`, they only implement their
   specific needs such as spawning the connections, certificate/keys handling for ssh, etc.   
