import serial
import queue
import threading
import time
import service
import requests
import sys
import subprocess
from collections import Counter


# 공유 큐 생성
q = queue.Queue()
#send_URL = 'http://1.220.196.5:18001/Serial'
send_URL = 'http://106.240.243.250:9999/Serial'

hostname = service.getHostName().replace("-", "")
flag = "default"
api_condition = "T" # T: 정상 , F: exception 종료

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


def run_udevadm():
    for i in range(4):
        try:
            output = subprocess.check_output(["udevadm", "info", f"--name=/dev/ttyUSB"+str(i), "--attribute-walk"])
            output_str = output.decode("utf-8")

            if 'ch341-uart' in output_str:
                print(" found 'ch341-uart':\n")
                return str(i)
            else:
                print("does not contain 'ch341-uart'")
        except subprocess.CalledProcessError as e:
            print(f"An error occurred for {device_name}: {e}")
    return


usb_num = run_udevadm()
try:
        ser = serial.Serial('/dev/ttyUSB'+usb_num, 9600) # 포트와 전송 속도에 맞게 설정
except serial.SerialException as e:
        print(f"Error opening serial port: {e}")
        exit()



def read_file(filename):
    with open(filename, 'r') as file:
        content = file.read()
        content=content.replace("\n","")
    return content

def write_file(filename, content):
    with open(filename, 'w') as file:
        file.write(content)


def logic_FlagPC(dt):
    flag = read_file("/home/pi/Current/flag_pc.txt")
    pc = int(read_file("/home/pi/Current/partCount.txt").strip())
    if abs(float(dt["M30"])) > 0.1 :
        print(flag)
        if flag == "T" :
            pc+=1
            write_file("/home/pi/Current/flag_pc.txt", "F")
            write_file("/home/pi/Current/partCount.txt", str(pc))
    else :
        if flag == "F":
            write_file("/home/pi/Current/flag_pc.txt", "T")


    dt["partCount"] = pc
    return dt

# 데이터를 넣는 함수
def read_data():
    global api_condition
    while True:

        data=""
        try:
            if ser.in_waiting != 0: # 시리얼 포트에서 데이터를 받았을 경우
                data = ser.readline().decode('utf-8', 'ignore').rstrip() # 데이터를 읽어온 후 개행 문자와 공백 문자를 제거
                print(f"Enqueued: {data}")
                if "M30:" in data:
                    q.put(data)

                    #print(f"Enqueued: {data}")
        except serial.SerialException as e:
            print(f"Serial port error: {e}")
            time.sleep(1)

        except OSError as e:
            print(f"OS Error: {e}")
            api_condition = "F"
        time.sleep(0.1)
        if api_condition == "F":
            sys.exit()

# 데이터를 빼내서 출력하는 함수
def processing():
    while q:
        item = q.get().split(",")
        result = dict(i.split(":") for i in item)
        time.sleep(0.1)

        final = logic_FlagPC(result)
        sendIFServer(final)
    if api_condition == "F":
        sys.exit()

def sendIFServer(data):
    global api_condition
    print(data)
    url = send_URL
    header = {'Content-Type' : 'application/json; charset=utf-8'}
    data["name"] = hostname
    data["cpu_serial"] = cpu_serial
    datas = data
    print(datas)
    try:
        response = requests.post(url, json = datas)
        print(response)
    except:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        api_condition = "F"
    return response.status_code


if __name__ == "__main__":
    initialize_cpu_serial()

    # 두 개의 스레드 생성
    t1 = threading.Thread(target=read_data)
    t2 = threading.Thread(target=processing)

    # 스레드 시작
    t1.start()
    t2.start()

    while True:
        time.sleep(1)
        if api_condition == "F":
            t1.join()
            t2.join()
            sys.exit()
