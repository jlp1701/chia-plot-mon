from prometheus_client import start_http_server, Summary
import random
import time
import re
import os
import glob
from prometheus_client import Counter
from prometheus_client import Gauge
from prometheus_client import Enum

### globals
scan_interval_s = 5
plot_log_dir = "./logs/plotter/*"
logs = {}
node_info = {}
g_plot_phases = {}

g_plot_phases = Gauge("plot_phases", "Plot Phases", labelnames=["device", "curr_phase"])
#g_plot_phases["2"] = Gauge("plots_phase_2", "Number of plots in Phase 2.", labelnames=["device"])
#g_plot_phases["3"] = Gauge("plots_phase_3", "Number of plots in Phase 3.", labelnames=["device"])
#g_plot_phases["4"] = Gauge("plots_phase_4", "Number of plots in Phase 4.", labelnames=["device"])
#g_plot_phases["copy"] = Gauge("plots_phase_copy", "Number of plots currently copied.", labelnames=["device"])
#g_plot_phases["fin"] = Gauge("plots_phase_fin", "Number of plots finished.", labelnames=["device"])

# Create a metric to track time spent and requests made.
# REQUEST_TIME = Summary('request_processing_seconds', 'Time spent processing request')

# # Decorate function with metric.
# @REQUEST_TIME.time()
# def process_request(t):
#     """A dummy function that takes some time."""
#     #c.inc(1.6)  # Increment by given value
#     time.sleep(t)

# if __name__ == '__main__':
#     # Start up the server to expose the metrics.
#     start_http_server(8000)
#     # Generate some requests.
#     c = Counter('my_failures', 'Description of counter')
#     g = Counter('my_gauge', 'My Description of a gauge', ['label_a', 'label_b'])
#     g.labels('a', 'b').inc()
#     while True:
#         process_request(random.random())

######################################################

# metrics to collect:
# plot_status{dir,k,file/id}=["Phase1", "Phase2", "Phase3", "Phase4", "Finished"]
# 

# read log files

def scan_plot_logs(dir_path, curr_logs):
    plot_name_regex = r"plotter_log_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.txt"
    # get all files in dir
    files = glob.glob(plot_log_dir)

    # filter out files which do not match regex and are not empty
    files = list(filter(lambda f: re.match(plot_name_regex, os.path.basename(f)), files))
    files = list(filter(lambda f: os.path.getsize(f) > 0, files))

    # for all matched plotfiles:
    for f in files:
        if f not in curr_logs:
            curr_logs[f] = {"device": "?", "k": "?", "status": "Unknown", "num_read": 0}
        # if plotfile size differs with entry in log
        if curr_logs[f]["num_read"] != os.path.getsize(f):
            # read difference
            with open(f, mode="r") as fd:
                fd.seek(curr_logs[f]["num_read"])
                lines_read = fd.readlines()
            # extract phase
            ph = extract_phase(lines_read)
            if ph != "Unknown":
                print(f"Set new status: {ph} for file: {os.path.basename(f)}")
                curr_logs[f]["status"] = ph
            curr_logs[f]["num_read"] = os.path.getsize(f)
    return curr_logs

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
    g_plot_phases.clear()
    g_plot_phases.labels("devb", "Phase 1").inc()
    for p, stats in logs.items():
        g_plot_phases.labels("dev", stats["status"]).inc()
        


if __name__ == "__main__":
    # start node exporter
    start_http_server(8000)
    try:
        while True:
            # scan plotter log dir
            print(f"scan log dir ...")
            logs = scan_plot_logs(plot_log_dir, logs)

            # generate node info
            print(f"update node stats ...")
            update_node_status(logs)

            # sleep
            print(f"sleep {scan_interval_s}s")
            time.sleep(scan_interval_s)
    except KeyboardInterrupt:
        # do exit stuff
        sys.exit()
    