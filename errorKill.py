import os
import time
import subprocess

def check_port_and_kill():
    while True:
        # lsof -i 명령어를 실행하여 106.240.243.250:8888에 연결된 프로세스가 있는지 확인
        result = subprocess.run(["lsof", "-i"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout.decode()

        # 106.240.243.250:8888이 output에 없으면 client.py를 종료
        if "106.240.243.250:8888" not in output:
            print("Connection to 106.240.243.250:8888 not found. Killing client.py...")
            subprocess.run(["pkill", "-f", "client.py"])

        # 5초 대기 후 다시 체크
        time.sleep(5)

if __name__ == "__main__":
    check_port_and_kill()
