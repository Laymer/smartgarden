import crython
import time
import ConfigParser
from random import randint
import requests
import subprocess
import grovepi
import sys, os
import logging
from logging.handlers import RotatingFileHandler


pathname = os.path.dirname(sys.argv[0])

if not pathname:
    pathname = "."

# class for sensors
class HumiditySensor:
    def __init__(self, pin, threshold):
        self.pin = pin
        self.threshold = threshold


Config = ConfigParser.ConfigParser()
Config.read(pathname + '/config.ini')

# Logger
app_name= Config.get('Garden-Controller', 'app-name')
log_level= Config.get('Log', 'level')
log_file= Config.get('Log', 'file')
log_format= '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

logging.basicConfig(filename=log_file,level=logging.getLevelName(log_level))
logger = logging.getLogger(app_name)
fh = RotatingFileHandler(log_file, maxBytes=10000000, backupCount=5)
formatter = logging.Formatter(log_format)
fh.setFormatter(formatter)
fh.setLevel(logging.getLevelName(log_level))
logger.addHandler(fh)

# read sensors from config
sensors = []
for each_section in Config.sections():
    if each_section.startswith('Humidity-Sensor'):
        sensors.append(HumiditySensor(int(Config.get(each_section, 'pin')),
                                      int(Config.get(each_section, 'threshold'))))

# watering server connection
watering_url = Config.get('Watering-Server', 'url')
watering_port = Config.get('Watering-Server', 'port')

# own stuff
watering_job_scheduler = Config.get('Garden-Controller', 'watering-scheduler')
watering_job_pour = float(Config.get('Garden-Controller', 'watering-pour'))

measure_count = int(Config.get('Garden-Controller', 'measure-count'))
upper_measure_limit = int(Config.get('Garden-Controller', 'upper-measure-limit'))
lower_measure_limit = int(Config.get('Garden-Controller', 'lower-measure-limit'))


def measure_to_humidity(measure):
    return (float(measure) - lower_measure_limit) / (upper_measure_limit - lower_measure_limit) * 100


def check_sensor(sensor):
    measure_sum = 0

    for x in range(0, measure_count):
        # read sensor
        measure = grovepi.analogRead(sensor.pin)
        measure_sum += measure

    final_measure = measure_sum / measure_count
    humidity = measure_to_humidity(final_measure)

    logger.info("Pin: {}, Measure: {}, Threshold: {}".format(sensor.pin, humidity, sensor.threshold))

    if humidity <= sensor.threshold:
        return True

    return False


def start_watering_server():
    result = subprocess.Popen(["python", pathname + "/watering_server.py"])


@crython.job(expr=watering_job_scheduler)
def watering():
    job_sensors = sensors[:]

    # make sure there is a quorum
    if len(job_sensors) % 2 == 0:
        del job_sensors[randint(0, len(job_sensors) - 1)]

    # check sensors
    decisions = []
    for sensor in job_sensors:
        decisions.append(check_sensor(sensor))

    yes_count = len([e for e in decisions if e])

    if yes_count > len(job_sensors) / 2:
        logger.info('Yes! Water it!')

        try:
            requests.put('http://' + watering_url + ':' + watering_port + '/pour/' + str(watering_job_pour))
            logger.info('Send watering request.')
        except requests.exceptions.ConnectionError:
            logger.warning("No watering server! restart watering server...")
            start_watering_server()
            time.sleep(1)
            watering()

    else:
        logger.info('No! No water!')


if __name__ == '__main__':

    watering_server_available = False

    try:
        r = requests.get('http://' + watering_url + ':' + watering_port + '/status')
        if r.status_code == 200:
            watering_server_available = True

    except requests.exceptions.ConnectionError:
        pass

    if not watering_server_available:
        logger.warning( "No watering server found! Starting watering server...")
        start_watering_server()

    crython.start()

    logger.info("Garden Controller started up!")
    while True:
        time.sleep(1)
