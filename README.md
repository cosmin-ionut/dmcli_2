Limitations:
1. Monitor Utils has huge limitations:
   - parse_logfile goes through the logfile each time it is called.
   - although the iteration is done in a lazy fashion, all values parsed are stored in memory.
