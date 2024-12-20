import datetime
import subprocess
import os
import signal
import service
import requests
from collections import Counter

send_URL = "http://1.220.196.5:18001/validateDevice"
send_URL = "http://106.240.243.250:9999/validateDevice"


# 전역 변수로 cpu_serial을 저장합니다.
cpu_serial = None

def initialize_cpu_serial():
    global cpu_serial
    serial_list = []
    for _ in range(5):
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.startswith('Serial'):
                        serial_list.append(line.split(':')[1].strip())
                        break
        except FileNotFoundError:
            serial_list.append("0000000000000000")
    cpu_serial = Counter(serial_list).most_common(1)[0][0]



def receiveFromIFServer():
    url = send_URL
    data = {}
    header = {'Content-Type' : 'application/json; charset=utf-8'}
    data["serial_num"] = cpu_serial
    datas = dict(data)

    try:
        response = requests.post(url, json = datas)
    except Exception as e:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    return response.json()




def kill_process(process_path):
    try:
        subprocess.check_output(['/home/pi/Current/kill_process.sh', process_path], text=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: {e.output}")

if __name__ == "__main__":
    now = datetime.datetime.now()
    initialize_cpu_serial()
    result = receiveFromIFServer()
    print(result)
    if result["validate"] != "T":
        print("dead")
        kill_process("/home/pi/Current/main.py")
