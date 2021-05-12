from prometheus_client import start_http_server, Summary
import time
import re
import os
import glob
import logging
import sys
import yaml
from prometheus_client import Gauge

### globals; will be overwritten by values in config file
scan_interval_s = 5.111
plot_log_dir = ""
logs = {}
node_info = {}
phases = ["Phase 1", "Phase 2", "Phase 3", "Phase 4", "Copying", "Finished"]
devices = []
t_tmpdir_dev = {}
g_plot_phases = Gauge("plot_phases", "Plot Phases", labelnames=["device", "curr_phase"])

logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',
                    handlers=[
                        logging.FileHandler("debug.log"),
                        logging.StreamHandler()],
                    level=logging.DEBUG)


# metrics to collect:
# plot_status{dir,k,file/id}=["Phase1", "Phase2", "Phase3", "Phase4", "Finished"]
# 

# read log files
def scan_plot_logs(dir_path, curr_logs):
    # plot_name_regex = r"plotter_log_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.txt"
    plot_name_regex = r"[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2}:[0-9]{2}:[0-9]{2}\.log"
    # get all files in dir
    files = glob.glob(plot_log_dir)

    # filter out files which do not match regex and are not empty
    files = list(filter(lambda f: re.match(plot_name_regex, os.path.basename(f)), files))
    files = list(filter(lambda f: os.path.getsize(f) > 0, files))

    # check for which log entry there is no more file and then remove entry
    curr_logs = dict(list(filter(lambda t: t[0] in files, curr_logs.items())))

    # for all matched plotfiles:
    for f in files:
        if f not in curr_logs:
            curr_logs[f] = {"device": None, "status": "Unknown", "num_read": 0}
        if curr_logs[f]["device"] == None:
            lines_read = []
            with open(f, mode="r") as fd:
                lines_read = fd.readlines()
            dir_plot = extract_plot_filepath(lines_read)
            if dir_plot is not None:
                if dir_plot not in t_tmpdir_dev:
                    logging.warning(f"Could not find plot dir '{dir_plot}' in table.")
                else:
                    d = t_tmpdir_dev[dir_plot]
                    logging.info(f"Set device = {d} for plot '{f}'")
                    curr_logs[f]["device"] = d
            else:
                logging.warning(f"Could not find plot tmp dir for logfile: '{f}'")
        # if plotfile size differs with entry in log
        if curr_logs[f]["num_read"] != os.path.getsize(f):
            logging.info(f"File size '{f}' differs. Reading content ...")
            # read difference
            lines_read = []
            with open(f, mode="r") as fd:
                fd.seek(curr_logs[f]["num_read"])
                lines_read = fd.readlines()
            # extract phase
            logging.info(f"Read {len(lines_read)} new lines.")
            ph = extract_phase(lines_read)
            if ph != "Unknown":
                print(f"Set new status: {ph} for file: {os.path.basename(f)}")
                curr_logs[f]["status"] = ph
                curr_logs[f]["num_read"] = os.path.getsize(f)
            else:
                logging.debug(f"Parsed Unknown phase of logfile. Current phase: {curr_logs[f]['status']}. Discarding read lines. File: '{f}'")
    return curr_logs

def extract_plot_filepath(lines_read):
    plot_dir_regex = r"Starting plotting progress into temporary dirs: (.*?) and (.*?)$"
    for l in lines_read:
        m = re.match(plot_dir_regex, l)
        if m:
            tmp_dirs = m.groups()
            print(tmp_dirs)
            if len(tmp_dirs) != 2:
                logging.warning(f"Number of tmp plot dirs is: {len(tmp_dirs)}. Should be 2.")
            if tmp_dirs[0] != tmp_dirs[1]:
                logging.warning(f"Tmp plot dirs are different: '{tmp_dirs[0]}' and '{tmp_dirs[1]}'")
            return tmp_dirs[0]
    return None

def extract_phase(new_lines):
    status = "Unknown"
    phases_regex = [(r"^Starting phase 1/4:.*", "Phase 1"),
                    (r"^Starting phase 2/4:.*", "Phase 2"),
                    (r"^Starting phase 3/4:.*", "Phase 3"),
                    (r"^Starting phase 4/4:.*", "Phase 4"),
                    (r"^Final File size:.*", "Copying"),
                    (r"^Copied final file from.*", "Finished")]
    # go through lines and check for matching phrase
    for l in new_lines:
        for pat, ph in phases_regex:
            if re.match(pat, l):
                status = ph
    return status


def update_node_status(logs):
    # raise NotImplementedError("possible device data mismatch of 'devices' and 't_tmpdir_dev' in config; solution: remove devices from config and extract all devices from t_tmpdir_dev")
    for d in devices:
        for p in phases:
            g_plot_phases.labels(d, p).set(0)
    for p, stats in logs.items():
        g_plot_phases.labels(stats["device"], stats["status"]).inc()
        


if __name__ == "__main__":
    # logging.basicConfig(format='%(asctime)s %(message)s')
    logging.debug("###########################################################")
    logging.debug(f"Application startup.")
    
    # check for yaml config file
    if not os.path.exists("./config.yaml"):
        logging.error("Can't find config file 'config.yaml' in working dir. Exiting ...")
        sys.exit(1)
    with open("config.yaml", "r") as fd:
        plot_cfg = yaml.safe_load(fd)
    
    scan_interval_s = plot_cfg["scan_interval_s"]
    plot_log_dir = plot_cfg["plot_log_dir"]
    map_dev_tmpdir = plot_cfg["map_dev_tmpdir"]

    # extract devices from map_dev_tmpdir
    devices = list(map_dev_tmpdir.keys())

    # create dict with tmpdir -> device
    t_tmpdir_dev = dict([(v, k) for k, d_list in map_dev_tmpdir.items() for v in d_list])

    # start node exporter
    logging.info(f"Starting prometheus node on 'localhost:{plot_cfg['node_port']}'")
    start_http_server(plot_cfg['node_port'])
    try:
        while True:
            # scan plotter log dir
            logging.debug(f"scan log dir {plot_log_dir}")
            logs = scan_plot_logs(plot_log_dir, logs)

            # generate node info
            logging.debug(f"update node stats ...")
            update_node_status(logs)

            # sleep
            logging.debug(f"sleep {scan_interval_s}s")
            time.sleep(scan_interval_s)
    except KeyboardInterrupt:
        # do exit stuff
        logging.info("Gracefully exiting ...")
        sys.exit()
    
