import time
from datetime import datetime
from pathlib import Path
import argparse
import csv
import gcsfs
from i2c import get_devices

def parse_arguments(description=None):
    parser = argparse.ArgumentParser(description)
    parser.add_argument(
        "-r",
        "--poll_rate",
        help="poll rate in seconds",
        default=5.0,
        metavar='N',
        type=float
    )
    parser.add_argument(
        "-d",
        "--duration",
        help="length of run in hours",
        default=80,
        metavar='N',
        type=float
    )
    return parser.parse_args()


def log_data_to_csv(
    poll_rate,
    duration,
):
    """Log sensor data to CSV and upload to GCS
    File name will be YYYY-MM-DD-hh:mm:ss_octopi.csv
    where time stamp is the time collection begins

    Parameters
    ----------
    poll_rate: float
        poll rate in seconds
    duration: float
        run duration in hours

    Returns
    -------
    None
    """

    # Get the device
    device_list = get_devices()
    if len(device_list) == 0:
        raise IOError("No Devices Found")
    device = device_list[0]

    # Set up the CSV file
    header = ['t_stamp', 't_rel (min)', 'ORP', 'pH', 'RTD']
    csv_file = "pershing_caron_data/" + datetime.now().strftime("%Y-%m-%d-%H:%M:%S") + "_octopi.csv"
    Path(csv_file).touch(exist_ok=True)
    with open(csv_file, 'a', encoding='UTF8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)

    # check for polling time being too short, change it to the minimum timeout if too short
    if poll_rate < device.long_timeout:
        print("Polling time is shorter than timeout, setting polling time to %0.2f" % device.long_timeout)
        poll_rate = device.long_timeout

    # Start the run
    start_time = time.time()
    try:
        while True:
            print("-------press ctrl-c to stop the run")
            data = []  # will correspond to the information in header list

            for dev in device_list:
                dev.write("R")
            time.sleep(poll_rate)

            # Append timestamp and t_rel
            data.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            t_rel = (time.time() - start_time) / 60  # Relative time in minutes
            data.append(t_rel)

            # Read results from each device
            for dev in device_list:
                reading = dev.read()
                data.append(float(reading.split(": ")[-1].replace("\x00","")))
                print(reading)
            
            # Write to CSV
            with open(csv_file, 'a', encoding='UTF8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(data)

            # Kill run if over duration
            if (t_rel / 60) > duration:
                print("Uploading file...")
                fs = gcsfs.GCSFileSystem(project='production-data-infra')
                fs.put_file(csv_file, f"nf_data_lake_prod/iot/octopi/{csv_file}")
                break

    except KeyboardInterrupt:       # catches the ctrl-c command, which breaks the loop above
        print("Uploading file...")
        fs = gcsfs.GCSFileSystem(project='production-data-infra')
        fs.put_file(csv_file, f"nf_data_lake_prod/iot/octopi/{csv_file}")
        print("Continuous polling stopped")

    return


if __name__ == '__main__':
    args = parse_arguments()
    log_data_to_csv(args.poll_rate, args.duration)
